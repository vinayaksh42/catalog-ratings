"""Rating statistics for a platform's catalog, and comparisons between runs.

"Rated" titles are those with an IMDb rating and at least MIN_VOTES votes;
all rating statistics use that set so a handful of 3-vote titles can't skew them.
"""
from __future__ import annotations

import json
import sqlite3
import statistics

from .config import PLATFORMS, Settings

HIST_BINS = 18          # 1.0-1.5, 1.5-2.0, ... 9.5-10.0
DENSITY_STEPS = 91      # 1.0, 1.1, ... 10.0
LIST_SIZE = 10
MOVERS_SIZE = 5


# -- helpers --------------------------------------------------------------
def _mean(values):
    return sum(values) / len(values) if values else None


def _round(value, digits=2):
    return round(value, digits) if value is not None else None


def _percentile(sorted_values, q):
    if not sorted_values:
        return None
    pos = (len(sorted_values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def _share(count, total):
    return round(count / total, 4) if total else None


def _diff(new, old, digits=3):
    if new is None or old is None:
        return None
    return round(new - old, digits)


def platform_rows(conn: sqlite3.Connection, run_id: int, platform: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT t.id, t.title, t.year, t.media_type, t.genres, t.imdb_id,
               r.imdb_rating, r.imdb_votes, r.rt_score, r.metascore
        FROM availability a
        JOIN titles t ON t.id = a.title_id
        LEFT JOIN ratings r ON r.run_id = a.run_id AND r.title_id = a.title_id
        WHERE a.run_id = ? AND a.platform = ?
        """,
        (run_id, platform),
    ).fetchall()
    return [dict(r) for r in rows]


def rated(rows: list[dict], min_votes: int) -> list[dict]:
    return [
        r for r in rows
        if r["imdb_rating"] is not None and (r["imdb_votes"] or 0) >= min_votes
    ]


def _title_card(r: dict) -> dict:
    return {
        "title": r["title"],
        "year": r["year"],
        "media_type": r["media_type"],
        "imdb_id": r["imdb_id"],
        "imdb_rating": r["imdb_rating"],
        "imdb_votes": r["imdb_votes"],
        "rt_score": r["rt_score"],
    }


# -- summary --------------------------------------------------------------
def summarize(rows: list[dict], min_votes: int) -> dict:
    good = rated(rows, min_votes)
    values = sorted(r["imdb_rating"] for r in good)
    n = len(values)
    total_votes = sum(r["imdb_votes"] for r in good)
    rt = [r["rt_score"] for r in rows if r["rt_score"] is not None]
    meta = [r["metascore"] for r in rows if r["metascore"] is not None]
    # Critics (Tomatometer, rescaled to 0-10) minus audience (IMDb), same title.
    gaps = [r["rt_score"] / 10 - r["imdb_rating"] for r in good if r["rt_score"] is not None]
    movies = [r["imdb_rating"] for r in good if r["media_type"] == "movie"]
    shows = [r["imdb_rating"] for r in good if r["media_type"] == "tv"]

    return {
        "catalog_size": len(rows),
        "movie_count": sum(1 for r in rows if r["media_type"] == "movie"),
        "show_count": sum(1 for r in rows if r["media_type"] == "tv"),
        "rated_count": n,
        "mean": _round(_mean(values)),
        "median": _round(statistics.median(values)) if values else None,
        "weighted_mean": _round(
            sum(r["imdb_rating"] * r["imdb_votes"] for r in good) / total_votes
        ) if total_votes else None,
        "std": _round(statistics.pstdev(values)) if n > 1 else None,
        "p10": _round(_percentile(values, 0.10)),
        "p25": _round(_percentile(values, 0.25)),
        "p75": _round(_percentile(values, 0.75)),
        "p90": _round(_percentile(values, 0.90)),
        "share_8plus": _share(sum(v >= 8 for v in values), n),
        "share_below5": _share(sum(v < 5 for v in values), n),
        "movies_mean": _round(_mean(movies)),
        "shows_mean": _round(_mean(shows)),
        "rt_count": len(rt),
        "rt_coverage": _share(len(rt), len(rows)),
        "rt_mean": _round(_mean(rt), 1),
        "rt_fresh_share": _share(sum(s >= 60 for s in rt), len(rt)),
        "critic_gap": _round(_mean(gaps)),
        "metascore_mean": _round(_mean(meta), 1),
    }


def density(good: list[dict]) -> list[int]:
    """Title counts at each 0.1 step from 1.0 to 10.0 (for the strip plot)."""
    counts = [0] * DENSITY_STEPS
    for r in good:
        idx = round((r["imdb_rating"] - 1) * 10)
        counts[min(max(idx, 0), DENSITY_STEPS - 1)] += 1
    return counts


def histogram(good: list[dict]) -> list[float]:
    """Share of rated titles in each half-point bin, 1.0 to 10.0."""
    counts = [0] * HIST_BINS
    for r in good:
        idx = int((r["imdb_rating"] - 1) / 0.5)
        counts[min(max(idx, 0), HIST_BINS - 1)] += 1
    n = len(good)
    return [round(c / n, 4) if n else 0 for c in counts]


def genres(good: list[dict], min_titles: int = 15, limit: int = 12) -> list[dict]:
    buckets: dict[str, list[float]] = {}
    for r in good:
        for g in json.loads(r["genres"] or "[]"):
            buckets.setdefault(g, []).append(r["imdb_rating"])
    out = [
        {"genre": g, "count": len(v), "mean": _round(_mean(v))}
        for g, v in buckets.items()
        if len(v) >= min_titles
    ]
    out.sort(key=lambda x: -x["count"])
    return out[:limit]


def extremes(good: list[dict], list_min_votes: int) -> tuple[list[dict], list[dict]]:
    pool = [r for r in good if r["imdb_votes"] >= list_min_votes]
    top = sorted(pool, key=lambda r: (-r["imdb_rating"], -r["imdb_votes"]))[:LIST_SIZE]
    bottom = sorted(pool, key=lambda r: (r["imdb_rating"], -r["imdb_votes"]))[:LIST_SIZE]
    return [_title_card(r) for r in top], [_title_card(r) for r in bottom]


# -- comparison between two runs ------------------------------------------
def compare(prev_rows: list[dict], cur_rows: list[dict], min_votes: int, list_min_votes: int) -> dict:
    """What changed, and why the mean moved.

    The change in mean rating splits exactly into two parts:
      drift_effect   - titles that stayed on the platform got rated higher/lower
      catalog_effect - titles were added or removed
    """
    prev_ids = {r["id"] for r in prev_rows}
    cur_ids = {r["id"] for r in cur_rows}
    added_ids = cur_ids - prev_ids
    removed_ids = prev_ids - cur_ids

    prev_rated = {r["id"]: r for r in rated(prev_rows, min_votes)}
    cur_rated = {r["id"]: r for r in rated(cur_rows, min_votes)}
    prev_mean = _mean([r["imdb_rating"] for r in prev_rated.values()])
    cur_mean = _mean([r["imdb_rating"] for r in cur_rated.values()])

    stayers = cur_rated.keys() & prev_rated.keys()
    deltas = {i: cur_rated[i]["imdb_rating"] - prev_rated[i]["imdb_rating"] for i in stayers}

    total = cur_mean - prev_mean if cur_mean is not None and prev_mean is not None else None
    drift = sum(deltas.values()) / len(cur_rated) if cur_rated and total is not None else None
    catalog = total - drift if total is not None and drift is not None else None

    movers = [
        {**_title_card(cur_rated[i]), "change": round(d, 2)}
        for i, d in deltas.items()
        if cur_rated[i]["imdb_votes"] >= list_min_votes and abs(d) >= 0.05
    ]

    def notable(ids, lookup):
        rows = sorted((lookup[i] for i in ids if i in lookup), key=lambda r: -(r["imdb_votes"] or 0))
        return [_title_card(r) for r in rows[:MOVERS_SIZE]]

    def every(ids, rows):
        """All titles in ids, rated or not, most-voted first."""
        picked = sorted(
            (r for r in rows if r["id"] in ids),
            key=lambda r: (-(r["imdb_votes"] or 0), r["title"] or ""),
        )
        return [_title_card(r) for r in picked]

    return {
        "added": len(added_ids),
        "removed": len(removed_ids),
        "stayed": len(cur_ids & prev_ids),
        "added_mean": _round(_mean([cur_rated[i]["imdb_rating"] for i in added_ids if i in cur_rated])),
        "removed_mean": _round(_mean([prev_rated[i]["imdb_rating"] for i in removed_ids if i in prev_rated])),
        "mean_change": _round(total, 3),
        "drift_effect": _round(drift, 3),
        "catalog_effect": _round(catalog, 3),
        "stayer_mean_change": _round(_mean(list(deltas.values())), 3),
        "rising": sorted((m for m in movers if m["change"] > 0), key=lambda m: -m["change"])[:MOVERS_SIZE],
        "falling": sorted((m for m in movers if m["change"] < 0), key=lambda m: m["change"])[:MOVERS_SIZE],
        "added_examples": notable(added_ids, cur_rated),
        "removed_examples": notable(removed_ids, prev_rated),
        "added_titles": every(added_ids, cur_rows),
        "removed_titles": every(removed_ids, prev_rows),
    }


# -- API payloads ---------------------------------------------------------
DELTA_KEYS = (
    "catalog_size", "mean", "median", "weighted_mean", "share_8plus",
    "share_below5", "rt_mean", "rt_fresh_share", "critic_gap",
)


def platform_summary(conn, run_id: int, platform: str, settings: Settings) -> dict:
    return summarize(platform_rows(conn, run_id, platform), settings.min_votes)


def latest_done_run_id(conn) -> int | None:
    row = conn.execute("SELECT id FROM runs WHERE status = 'done' ORDER BY id DESC LIMIT 1").fetchone()
    return row["id"] if row else None


def full_metrics(conn, run_id: int, settings: Settings) -> dict | None:
    run = conn.execute("SELECT * FROM runs WHERE id = ? AND status = 'done'", (run_id,)).fetchone()
    if not run:
        return None
    prev = conn.execute(
        "SELECT * FROM runs WHERE status = 'done' AND id < ? ORDER BY id DESC LIMIT 1", (run_id,)
    ).fetchone()

    platforms = {}
    for key, cfg in PLATFORMS.items():
        rows = platform_rows(conn, run_id, key)
        good = rated(rows, settings.min_votes)
        summary = summarize(rows, settings.min_votes)
        top, bottom = extremes(good, settings.list_min_votes)
        entry = {
            "label": cfg["label"],
            "summary": summary,
            "density": density(good),
            "histogram": histogram(good),
            "genres": genres(good),
            "top": top,
            "bottom": bottom,
            "change": None,
        }
        if prev:
            prev_rows = platform_rows(conn, prev["id"], key)
            prev_summary = summarize(prev_rows, settings.min_votes)
            change = compare(prev_rows, rows, settings.min_votes, settings.list_min_votes)
            change["deltas"] = {k: _diff(summary[k], prev_summary[k], 4) for k in DELTA_KEYS}
            entry["change"] = change
        platforms[key] = entry

    return {
        "run": dict(run),
        "previous_run": dict(prev) if prev else None,
        "min_votes": settings.min_votes,
        "list_min_votes": settings.list_min_votes,
        "platforms": platforms,
    }


def history(conn) -> dict:
    runs = conn.execute(
        "SELECT id, started_at, finished_at FROM runs WHERE status = 'done' ORDER BY id"
    ).fetchall()
    summaries: dict[int, dict] = {}
    for row in conn.execute("SELECT run_id, platform, data FROM run_summaries"):
        summaries.setdefault(row["run_id"], {})[row["platform"]] = json.loads(row["data"])
    return {
        "platforms": {k: v["label"] for k, v in PLATFORMS.items()},
        "runs": [
            {"id": r["id"], "finished_at": r["finished_at"], "platforms": summaries.get(r["id"], {})}
            for r in runs
        ],
    }


def list_runs(conn, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        """
        SELECT r.*, (SELECT COUNT(DISTINCT title_id) FROM availability a WHERE a.run_id = r.id) AS titles
        FROM runs r ORDER BY r.id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
