"""One run: pull catalogs -> match to IMDb -> attach ratings -> save a snapshot."""
from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import metrics
from .config import MEDIA_TYPES, PLATFORMS, Settings
from .db import session, utcnow
from .sources import imdb as imdb_source
from .sources import omdb as omdb_source
from .sources.tmdb import TMDBAuthError, TMDBClient, normalize

log = logging.getLogger(__name__)

MEDIA_LABELS = {"movie": "movies", "tv": "shows"}
OMDB_BATCH = 20

Report = Callable[[str, float, str], None]


class RunError(Exception):
    """A problem worth showing to the user as-is."""


class RunInProgress(Exception):
    pass


@dataclass
class Sources:
    tmdb: object                                            # TMDBClient-like
    imdb_ratings: Callable[[set[str]], dict[str, tuple[float, int]]]
    omdb_fetch: Callable[[str], dict] | None


def default_sources(settings: Settings) -> Sources:
    tmdb = TMDBClient(settings.tmdb_api_key, settings.tmdb_read_token)

    def imdb_ratings(wanted: set[str]):
        path = imdb_source.ensure_dataset(settings.data_dir)
        return imdb_source.load_ratings(path, wanted)

    omdb = omdb_source.OMDbClient(settings.omdb_api_key).fetch if settings.rt_enabled else None
    return Sources(tmdb=tmdb, imdb_ratings=imdb_ratings, omdb_fetch=omdb)


# -- the pipeline -----------------------------------------------------------
def run_pipeline(run_id: int, settings: Settings, sources: Sources, report: Report) -> str:
    notes: list[str] = []

    # 1. Catalogs ------------------------------------------------------------
    report("Reading catalogs", 0.01, "Looking up platforms on TMDB")
    genre_maps = {m: sources.tmdb.genre_map(m) for m in MEDIA_TYPES}
    titles: dict[str, dict] = {}
    availability: set[tuple[str, str]] = set()
    jobs = [(p, m) for p in PLATFORMS for m in MEDIA_TYPES]

    for i, (platform, media_type) in enumerate(jobs):
        label = f"{PLATFORMS[platform]['label']} {MEDIA_LABELS[media_type]}"
        ids = sources.tmdb.provider_ids(media_type, settings.region, PLATFORMS[platform]["provider_names"])
        if not ids:
            notes.append(f"TMDB lists no {label} for region {settings.region}.")
            continue
        base, span = 0.02 + 0.38 * i / len(jobs), 0.38 / len(jobs)

        def on_page(page, total, base=base, span=span, label=label):
            report("Reading catalogs", base + span * page / max(total, 1), f"{label}: page {page} of {total}")

        for item in sources.tmdb.discover(media_type, ids, settings.region, settings.max_pages, on_page):
            row = normalize(item, media_type, genre_maps[media_type])
            titles[row["id"]] = row
            availability.add((platform, row["id"]))

    if not availability:
        raise RunError(f"TMDB returned no titles for any platform in region {settings.region}.")

    now = utcnow()
    with session(settings.db_path) as conn:
        conn.executemany(
            """
            INSERT INTO titles (id, tmdb_id, media_type, title, year, genres, poster_path, updated_at)
            VALUES (:id, :tmdb_id, :media_type, :title, :year, :genres, :poster_path, :updated_at)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title, year = excluded.year, genres = excluded.genres,
                poster_path = excluded.poster_path, updated_at = excluded.updated_at
            """,
            [{**r, "genres": json.dumps(r["genres"]), "updated_at": now} for r in titles.values()],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO availability (run_id, platform, title_id) VALUES (?, ?, ?)",
            [(run_id, p, t) for p, t in availability],
        )
        missing = conn.execute(
            """
            SELECT id, tmdb_id, media_type FROM titles
            WHERE imdb_id IS NULL
              AND id IN (SELECT title_id FROM availability WHERE run_id = ?)
            """,
            (run_id,),
        ).fetchall()

    # 2. Match new titles to IMDb IDs (only titles never seen before) --------
    _match_imdb_ids(settings, sources, [dict(r) for r in missing], report)

    with session(settings.db_path) as conn:
        catalog = [dict(r) for r in conn.execute(
            """
            SELECT t.id, t.imdb_id FROM titles t
            WHERE t.id IN (SELECT title_id FROM availability WHERE run_id = ?)
            """,
            (run_id,),
        )]
    imdb_ids = {r["imdb_id"] for r in catalog if r["imdb_id"]}

    # 3. IMDb ratings (one daily file) ---------------------------------------
    report("Reading IMDb ratings", 0.62, "Downloading IMDb's daily ratings file")
    imdb_ratings = sources.imdb_ratings(imdb_ids)

    # 4. Rotten Tomatoes via OMDb, within the daily limit --------------------
    if sources.omdb_fetch:
        notes.extend(_refresh_rotten_tomatoes(settings, sources.omdb_fetch, imdb_ids, imdb_ratings, report))
    elif settings.rotten_tomatoes:
        notes.append("Rotten Tomatoes scores skipped: ROTTEN_TOMATOES is on but OMDB_API_KEY isn't set.")

    # 5. Snapshot ratings and store summaries --------------------------------
    report("Saving results", 0.95, "Writing this run's ratings")
    with session(settings.db_path) as conn:
        cache = {
            r["imdb_id"]: (r["rt_score"], r["metascore"])
            for r in conn.execute("SELECT imdb_id, rt_score, metascore FROM omdb_cache")
        }
        snapshot = []
        for r in catalog:
            iid = r["imdb_id"]
            rating, votes = imdb_ratings.get(iid, (None, None)) if iid else (None, None)
            rt, meta = cache.get(iid, (None, None)) if iid else (None, None)
            snapshot.append((run_id, r["id"], rating, votes, rt, meta))
        conn.executemany(
            "INSERT OR REPLACE INTO ratings (run_id, title_id, imdb_rating, imdb_votes, rt_score, metascore) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            snapshot,
        )
        for platform in PLATFORMS:
            summary = metrics.platform_summary(conn, run_id, platform, settings)
            conn.execute(
                "INSERT OR REPLACE INTO run_summaries (run_id, platform, data) VALUES (?, ?, ?)",
                (run_id, platform, json.dumps(summary)),
            )

    matched = sum(1 for r in catalog if r["imdb_id"] and r["imdb_id"] in imdb_ratings)
    notes.insert(0, f"{len(catalog):,} titles, {matched:,} with an IMDb rating.")
    return " ".join(notes)


def _match_imdb_ids(settings: Settings, sources: Sources, missing: list[dict], report: Report) -> None:
    total = len(missing)
    report("Matching titles to IMDb", 0.40, f"{total:,} new titles to match")
    if not total:
        return
    results: list[tuple[str, str]] = []
    done = 0
    with ThreadPoolExecutor(max_workers=settings.workers) as pool:
        futures = {
            pool.submit(sources.tmdb.imdb_id, r["media_type"], r["tmdb_id"]): r["id"] for r in missing
        }
        for future in as_completed(futures):
            title_id = futures[future]
            try:
                results.append((future.result() or "", title_id))
            except TMDBAuthError:
                raise
            except Exception as exc:  # leave NULL so the next run retries it
                log.warning("IMDb ID lookup failed for %s: %s", title_id, exc)
            done += 1
            if done % 25 == 0 or done == total:
                report("Matching titles to IMDb", 0.40 + 0.2 * done / total, f"{done:,} of {total:,}")
            if len(results) >= 500:
                _save_imdb_ids(settings, results)
                results = []
    _save_imdb_ids(settings, results)


def _save_imdb_ids(settings: Settings, results: list[tuple[str, str]]) -> None:
    if results:
        with session(settings.db_path) as conn:
            conn.executemany("UPDATE titles SET imdb_id = ? WHERE id = ?", results)


def _refresh_rotten_tomatoes(settings, fetch, imdb_ids, imdb_ratings, report) -> list[str]:
    """Fetch OMDb data for never-seen titles first (most-voted first), then stale ones."""
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    stale_before = (now - timedelta(days=settings.rt_refresh_days)).isoformat(timespec="seconds")

    with session(settings.db_path) as conn:
        row = conn.execute("SELECT calls FROM omdb_usage WHERE day = ?", (today,)).fetchone()
        used = row["calls"] if row else 0
        fetched_at = {r["imdb_id"]: r["fetched_at"] for r in conn.execute("SELECT imdb_id, fetched_at FROM omdb_cache")}

    budget = max(settings.omdb_daily_limit - used, 0)
    votes = lambda i: imdb_ratings.get(i, (0, 0))[1]  # noqa: E731
    never = sorted((i for i in imdb_ids if i not in fetched_at), key=votes, reverse=True)
    stale = sorted((i for i in imdb_ids if i in fetched_at and fetched_at[i] < stale_before), key=fetched_at.get)
    queue = (never + stale)[:budget]

    def safe(imdb_id):
        try:
            return fetch(imdb_id)
        except Exception as exc:  # returned, not raised, so one failure doesn't sink the batch
            return exc

    fetched = 0
    stop: omdb_source.OMDbStop | None = None
    report("Looking up Rotten Tomatoes", 0.65, f"0 of {len(queue):,} (OMDb calls left today: {budget:,})")
    with ThreadPoolExecutor(max_workers=min(4, settings.workers)) as pool:
        for start in range(0, len(queue), OMDB_BATCH):
            batch = queue[start:start + OMDB_BATCH]
            stamp = utcnow()
            rows, calls = [], 0
            for imdb_id, outcome in zip(batch, pool.map(safe, batch)):
                if isinstance(outcome, omdb_source.OMDbStop):
                    stop = outcome
                    continue
                calls += 1
                if isinstance(outcome, Exception):
                    log.warning("OMDb lookup failed for %s: %s", imdb_id, outcome)
                else:
                    rows.append((imdb_id, outcome["rt"], outcome["meta"], stamp))
            with session(settings.db_path) as conn:
                conn.executemany(
                    """
                    INSERT INTO omdb_cache (imdb_id, rt_score, metascore, fetched_at) VALUES (?, ?, ?, ?)
                    ON CONFLICT(imdb_id) DO UPDATE SET
                        rt_score = excluded.rt_score, metascore = excluded.metascore, fetched_at = excluded.fetched_at
                    """,
                    rows,
                )
                conn.execute(
                    "INSERT INTO omdb_usage (day, calls) VALUES (?, ?) "
                    "ON CONFLICT(day) DO UPDATE SET calls = calls + excluded.calls",
                    (today, calls),
                )
                if isinstance(stop, omdb_source.OMDbLimitReached):
                    conn.execute(
                        "UPDATE omdb_usage SET calls = MAX(calls, ?) WHERE day = ?",
                        (settings.omdb_daily_limit, today),
                    )
            fetched += len(rows)
            done = min(start + OMDB_BATCH, len(queue))
            report("Looking up Rotten Tomatoes", 0.65 + 0.3 * done / max(len(queue), 1), f"{done:,} of {len(queue):,}")
            if stop:
                break

    notes = []
    if fetched:
        notes.append(f"Looked up {fetched:,} titles on OMDb.")
    if stop:
        notes.append(str(stop))
    waiting = len(never) + len(stale) - fetched
    if waiting > 0:
        notes.append(f"{waiting:,} titles are still waiting for a Rotten Tomatoes lookup.")
    return notes


# -- background runner --------------------------------------------------------
class RunManager:
    """Runs the pipeline in a background thread and reports progress."""

    def __init__(self, settings: Settings, sources_factory=default_sources):
        self.settings = settings
        self._sources_factory = sources_factory
        self._lock = threading.Lock()
        self._state = {"running": False, "run_id": None, "step": None, "detail": "",
                       "progress": 0.0, "error": None, "started_at": None}
        self._thread: threading.Thread | None = None

    def state(self) -> dict:
        with self._lock:
            return dict(self._state)

    def start(self) -> dict:
        with self._lock:
            if self._state["running"]:
                raise RunInProgress()
            if not self.settings.has_tmdb:
                raise RunError("Add TMDB_API_KEY or TMDB_READ_TOKEN to backend/.env, then restart the server.")
            started = utcnow()
            with session(self.settings.db_path) as conn:
                run_id = conn.execute(
                    "INSERT INTO runs (started_at, status, region) VALUES (?, 'running', ?)",
                    (started, self.settings.region),
                ).lastrowid
            self._state = {"running": True, "run_id": run_id, "step": "Starting", "detail": "",
                           "progress": 0.0, "error": None, "started_at": started}
            self._thread = threading.Thread(target=self._work, args=(run_id,), daemon=True)
            self._thread.start()
            return dict(self._state)

    def wait(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def _report(self, step: str, progress: float, detail: str = "") -> None:
        with self._lock:
            self._state.update(step=step, detail=detail,
                               progress=round(max(self._state["progress"], min(progress, 1.0)), 3))

    def _work(self, run_id: int) -> None:
        try:
            sources = self._sources_factory(self.settings)
            message = run_pipeline(run_id, self.settings, sources, self._report)
            status, error = "done", None
        except (RunError, TMDBAuthError) as exc:
            status, error = "failed", str(exc)
            message = error
        except Exception as exc:
            log.exception("Run %s failed", run_id)
            status, error = "failed", f"{type(exc).__name__}: {exc}"
            message = error
        with session(self.settings.db_path) as conn:
            conn.execute(
                "UPDATE runs SET status = ?, finished_at = ?, message = ? WHERE id = ?",
                (status, utcnow(), message, run_id),
            )
        with self._lock:
            self._state.update(
                running=False,
                step="Finished" if status == "done" else "Failed",
                detail=message,
                progress=1.0 if status == "done" else self._state["progress"],
                error=error,
            )
