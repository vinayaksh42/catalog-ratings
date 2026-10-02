"""IMDb ratings from IMDb's official daily dataset (free for non-commercial use).

https://developer.imdb.com/non-commercial-datasets/
One ~8 MB download per day covers every title, so no per-title requests are needed.
"""
from __future__ import annotations

import gzip
import time
from pathlib import Path

import requests

RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"


def ensure_dataset(data_dir: Path, max_age_hours: float = 20) -> Path:
    """Download the ratings file unless a recent copy is already on disk."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "title.ratings.tsv.gz"
    if path.exists() and time.time() - path.stat().st_mtime < max_age_hours * 3600:
        return path
    partial = data_dir / "title.ratings.tsv.gz.part"
    with requests.get(
        RATINGS_URL, stream=True, timeout=120, headers={"User-Agent": "catalog-ratings/1.0"}
    ) as response:
        response.raise_for_status()
        with open(partial, "wb") as f:
            for chunk in response.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    partial.replace(path)
    return path


def load_ratings(path: Path, wanted: set[str]) -> dict[str, tuple[float, int]]:
    """Return {imdb_id: (average_rating, num_votes)} for the wanted IDs."""
    found: dict[str, tuple[float, int]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        next(f, None)  # header: tconst  averageRating  numVotes
        for line in f:
            tconst, rating, votes = line.rstrip("\n").split("\t")
            if tconst in wanted:
                found[tconst] = (float(rating), int(votes))
    return found
