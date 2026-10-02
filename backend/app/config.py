"""Settings, loaded from environment variables (and backend/.env if present)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

# Platform key -> display label and the provider names TMDB uses for it.
# Ad-supported tiers are listed separately on TMDB, so they're included here.
PLATFORMS: dict[str, dict] = {
    "netflix": {
        "label": "Netflix",
        "provider_names": ["Netflix", "Netflix Standard with Ads", "Netflix basic with Ads"],
    },
    "prime": {
        "label": "Prime Video",
        "provider_names": ["Amazon Prime Video", "Amazon Prime Video with Ads"],
    },
    "disney": {
        "label": "Disney+",
        "provider_names": ["Disney Plus"],
    },
    "apple": {
        "label": "Apple TV",
        "provider_names": ["Apple TV"],
    },
    # HBO has no service of its own in Canada; its catalog streams on Crave.
    "crave": {
        "label": "Crave (HBO)",
        "provider_names": ["Crave"],
    },
}

MEDIA_TYPES = ("movie", "tv")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a whole number, got {raw!r}") from exc


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"{name} must be true or false, got {raw!r}")


@dataclass(frozen=True)
class Settings:
    tmdb_api_key: str = ""
    tmdb_read_token: str = ""
    omdb_api_key: str = ""
    rotten_tomatoes: bool = False
    region: str = "CA"
    data_dir: Path = BACKEND_DIR / "data"
    omdb_daily_limit: int = 1000
    rt_refresh_days: int = 30
    min_votes: int = 100
    list_min_votes: int = 1000
    max_pages: int = 0
    workers: int = 8
    admin_token: str = ""
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "catalog.db"

    @property
    def has_tmdb(self) -> bool:
        return bool(self.tmdb_api_key or self.tmdb_read_token)

    @property
    def rt_enabled(self) -> bool:
        """Rotten Tomatoes is collected and shown only when switched on and an OMDb key is set."""
        return self.rotten_tomatoes and bool(self.omdb_api_key)


def load_settings() -> Settings:
    data_dir = os.getenv("DATA_DIR", "").strip()
    origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return Settings(
        tmdb_api_key=os.getenv("TMDB_API_KEY", "").strip(),
        tmdb_read_token=os.getenv("TMDB_READ_TOKEN", "").strip(),
        omdb_api_key=os.getenv("OMDB_API_KEY", "").strip(),
        rotten_tomatoes=_bool("ROTTEN_TOMATOES", False),
        region=(os.getenv("REGION", "CA").strip() or "CA").upper(),
        data_dir=Path(data_dir) if data_dir else BACKEND_DIR / "data",
        omdb_daily_limit=_int("OMDB_DAILY_LIMIT", 1000),
        rt_refresh_days=_int("RT_REFRESH_DAYS", 30),
        min_votes=_int("MIN_VOTES", 100),
        list_min_votes=_int("LIST_MIN_VOTES", 1000),
        max_pages=_int("MAX_PAGES", 0),
        workers=max(1, _int("WORKERS", 8)),
        admin_token=os.getenv("ADMIN_TOKEN", "").strip(),
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
    )


settings = load_settings()
