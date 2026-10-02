"""OMDb client for Rotten Tomatoes (Tomatometer) and Metacritic scores.

OMDb only exposes the critics' Tomatometer, not the RT audience score.
"""
from __future__ import annotations

import threading

import requests

OMDB_URL = "https://www.omdbapi.com/"


class OMDbStop(Exception):
    """Stop calling OMDb for the rest of this run."""


class OMDbLimitReached(OMDbStop):
    pass


class OMDbAuthError(OMDbStop):
    pass


class OMDbClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._local = threading.local()

    def _session(self) -> requests.Session:
        s = getattr(self._local, "session", None)
        if s is None:
            s = requests.Session()
            s.headers["User-Agent"] = "catalog-ratings/1.0"
            self._local.session = s
        return s

    def fetch(self, imdb_id: str) -> dict:
        response = self._session().get(
            OMDB_URL, params={"i": imdb_id, "apikey": self.api_key}, timeout=20
        )
        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            raise
        error = (data.get("Error") or "").lower()
        if "limit" in error:
            raise OMDbLimitReached(
                "OMDb's daily request limit was reached; the remaining titles will be looked up on a later run."
            )
        if response.status_code == 401 or "api key" in error:
            raise OMDbAuthError("OMDb rejected the API key. Check OMDB_API_KEY in backend/.env.")
        response.raise_for_status()
        if data.get("Response") == "False":
            return {"rt": None, "meta": None}
        return parse(data)


def parse(data: dict) -> dict:
    rt = None
    for entry in data.get("Ratings", []):
        if entry.get("Source") == "Rotten Tomatoes":
            value = (entry.get("Value") or "").rstrip("%")
            rt = int(value) if value.isdigit() else None
    meta_raw = data.get("Metascore") or ""
    return {"rt": rt, "meta": int(meta_raw) if meta_raw.isdigit() else None}
