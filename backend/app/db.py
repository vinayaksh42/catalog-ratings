"""SQLite storage. Every run is kept, so any two runs can be compared."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    status       TEXT NOT NULL,          -- running | done | failed
    region       TEXT NOT NULL,
    message      TEXT
);

-- One row per movie/show, shared across runs.
CREATE TABLE IF NOT EXISTS titles (
    id           TEXT PRIMARY KEY,       -- "movie:603", "tv:1399"
    tmdb_id      INTEGER NOT NULL,
    media_type   TEXT NOT NULL,          -- movie | tv
    title        TEXT NOT NULL,
    year         INTEGER,
    genres       TEXT,                   -- JSON list of genre names
    poster_path  TEXT,
    imdb_id      TEXT,                   -- NULL = not looked up yet, '' = TMDB has none
    updated_at   TEXT
);

-- Which titles were on which platform in a given run.
CREATE TABLE IF NOT EXISTS availability (
    run_id    INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    platform  TEXT NOT NULL,
    title_id  TEXT NOT NULL REFERENCES titles(id),
    PRIMARY KEY (run_id, platform, title_id)
);

-- Ratings as they were at the time of a run.
CREATE TABLE IF NOT EXISTS ratings (
    run_id       INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    title_id     TEXT NOT NULL REFERENCES titles(id),
    imdb_rating  REAL,
    imdb_votes   INTEGER,
    rt_score     INTEGER,               -- Tomatometer, 0-100
    metascore    INTEGER,
    PRIMARY KEY (run_id, title_id)
);

-- Latest OMDb answer per IMDb ID, refreshed gradually to respect the daily limit.
CREATE TABLE IF NOT EXISTS omdb_cache (
    imdb_id     TEXT PRIMARY KEY,
    rt_score    INTEGER,
    metascore   INTEGER,
    fetched_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS omdb_usage (
    day    TEXT PRIMARY KEY,             -- UTC date
    calls  INTEGER NOT NULL
);

-- Headline numbers per platform per run, used by the history view.
CREATE TABLE IF NOT EXISTS run_summaries (
    run_id    INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    platform  TEXT NOT NULL,
    data      TEXT NOT NULL,
    PRIMARY KEY (run_id, platform)
);

CREATE INDEX IF NOT EXISTS idx_availability_title ON availability(title_id);
CREATE INDEX IF NOT EXISTS idx_titles_imdb ON titles(imdb_id);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def session(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    with session(db_path) as conn:
        conn.executescript(SCHEMA)
        # A run still marked "running" at startup was cut off by a restart.
        conn.execute(
            "UPDATE runs SET status = 'failed', finished_at = ?, "
            "message = 'Interrupted: the server stopped during this run.' "
            "WHERE status = 'running'",
            (utcnow(),),
        )
