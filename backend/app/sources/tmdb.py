"""TMDB client: platform catalogs per region, and TMDB -> IMDb ID matching.

Catalog data comes from TMDB's watch-provider data (sourced from JustWatch).
"""
from __future__ import annotations

import threading
import time
from datetime import date
from typing import Callable, Iterator

import requests

BASE_URL = "https://api.themoviedb.org/3"
API_PAGE_LIMIT = 500        # TMDB never serves beyond page 500
API_RESULT_LIMIT = 10_000   # ...which is 10,000 results per query

PageCallback = Callable[[int, int], None]


class TMDBAuthError(Exception):
    pass


class TMDBClient:
    def __init__(self, api_key: str = "", read_token: str = ""):
        if not api_key and not read_token:
            raise TMDBAuthError("Set TMDB_API_KEY or TMDB_READ_TOKEN in backend/.env.")
        self._headers = {"Accept": "application/json", "User-Agent": "catalog-ratings/1.0"}
        self._params: dict[str, str] = {}
        if read_token:
            self._headers["Authorization"] = f"Bearer {read_token}"
        else:
            self._params["api_key"] = api_key
        self._local = threading.local()

    # -- HTTP -------------------------------------------------------------
    def _session(self) -> requests.Session:
        s = getattr(self._local, "session", None)
        if s is None:
            s = requests.Session()
            s.headers.update(self._headers)
            self._local.session = s
        return s

    def _get(self, path: str, **params) -> dict | None:
        response = None
        for attempt in range(6):
            try:
                response = self._session().get(
                    BASE_URL + path, params={**self._params, **params}, timeout=30
                )
            except requests.ConnectionError:
                time.sleep(2 ** attempt)
                continue
            if response.status_code == 401:
                raise TMDBAuthError("TMDB rejected the API key. Check TMDB_API_KEY / TMDB_READ_TOKEN.")
            if response.status_code == 404:
                return None
            if response.status_code == 429 or response.status_code >= 500:
                wait = float(response.headers.get("Retry-After") or 2 ** attempt)
                time.sleep(min(wait, 30))
                continue
            response.raise_for_status()
            return response.json()
        if response is None:
            raise requests.ConnectionError(f"Could not reach TMDB for {path}")
        response.raise_for_status()
        return None

    # -- Lookups ----------------------------------------------------------
    def provider_ids(self, media_type: str, region: str, names: list[str]) -> list[int]:
        data = self._get(f"/watch/providers/{media_type}", watch_region=region) or {}
        wanted = {n.lower() for n in names}
        return sorted({
            p["provider_id"]
            for p in data.get("results", [])
            if (p.get("provider_name") or "").lower() in wanted
        })

    def genre_map(self, media_type: str) -> dict[int, str]:
        data = self._get(f"/genre/{media_type}/list") or {}
        return {g["id"]: g["name"] for g in data.get("genres", [])}

    def imdb_id(self, media_type: str, tmdb_id: int) -> str | None:
        data = self._get(f"/{media_type}/{tmdb_id}/external_ids") or {}
        return data.get("imdb_id") or None

    # -- Catalogs ---------------------------------------------------------
    def discover(
        self,
        media_type: str,
        provider_ids: list[int],
        region: str,
        max_pages: int = 0,
        on_page: PageCallback | None = None,
    ) -> Iterator[dict]:
        """Yield every subscription title on the given providers in a region."""
        base = {
            "with_watch_providers": "|".join(str(i) for i in provider_ids),
            "watch_region": region,
            "with_watch_monetization_types": "flatrate",
            "sort_by": "popularity.desc",
            "include_adult": "false",
        }
        path = f"/discover/{media_type}"
        first = self._get(path, **base, page=1)
        if not first:
            return
        if max_pages or first.get("total_results", 0) <= API_RESULT_LIMIT:
            yield from self._pages(path, base, first, max_pages, on_page)
            return

        # More than TMDB will page through in one query: split by release date.
        date_key = "primary_release_date" if media_type == "movie" else "first_air_date"
        seen: set[int] = set()
        for item in self._split(path, base, date_key, 1870, date.today().year + 1, on_page):
            if item["id"] not in seen:
                seen.add(item["id"])
                yield item

    def _split(self, path, base, date_key, start, end, on_page) -> Iterator[dict]:
        params = {**base, f"{date_key}.gte": f"{start}-01-01", f"{date_key}.lte": f"{end}-12-31"}
        first = self._get(path, **params, page=1)
        if not first or not first.get("total_results"):
            return
        if first["total_results"] > API_RESULT_LIMIT and end > start:
            mid = (start + end) // 2
            yield from self._split(path, base, date_key, start, mid, on_page)
            yield from self._split(path, base, date_key, mid + 1, end, on_page)
        else:
            yield from self._pages(path, params, first, 0, on_page)

    def _pages(self, path, params, first, max_pages, on_page) -> Iterator[dict]:
        total = min(first.get("total_pages") or 1, API_PAGE_LIMIT)
        if max_pages:
            total = min(total, max_pages)
        yield from first.get("results", [])
        if on_page:
            on_page(1, total)
        for page in range(2, total + 1):
            data = self._get(path, **params, page=page)
            if not data:
                break
            yield from data.get("results", [])
            if on_page:
                on_page(page, total)


def normalize(item: dict, media_type: str, genre_map: dict[int, str]) -> dict:
    """Turn a TMDB discover result into a row for the titles table."""
    if media_type == "movie":
        name = item.get("title") or item.get("original_title")
        released = item.get("release_date") or ""
    else:
        name = item.get("name") or item.get("original_name")
        released = item.get("first_air_date") or ""
    year = int(released[:4]) if released[:4].isdigit() else None
    return {
        "id": f"{media_type}:{item['id']}",
        "tmdb_id": item["id"],
        "media_type": media_type,
        "title": name or "Untitled",
        "year": year,
        "genres": [genre_map[g] for g in item.get("genre_ids", []) if g in genre_map],
        "poster_path": item.get("poster_path"),
    }
