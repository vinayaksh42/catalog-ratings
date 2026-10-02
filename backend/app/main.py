"""FastAPI app. Run with:  uvicorn app.main:app --reload --port 8000  (from backend/)"""
from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import metrics
from .config import PLATFORMS, settings
from .db import init_db, session
from .pipeline import RunError, RunInProgress, RunManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

manager = RunManager(settings)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db(settings.db_path)
    yield


app = FastAPI(title="Catalog ratings API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if settings.admin_token and not (
        x_admin_token and secrets.compare_digest(x_admin_token, settings.admin_token)
    ):
        raise HTTPException(status_code=401, detail="Starting a run needs the admin token.")


@app.get("/api/config")
def get_config():
    return {
        "region": settings.region,
        "platforms": {k: v["label"] for k, v in PLATFORMS.items()},
        "tmdb_configured": settings.has_tmdb,
        "omdb_configured": bool(settings.omdb_api_key),
        "rotten_tomatoes": settings.rt_enabled,
        "min_votes": settings.min_votes,
        "admin_required": bool(settings.admin_token),
    }


@app.get("/api/status")
def get_status():
    return manager.state()


@app.post("/api/runs", dependencies=[Depends(require_admin)])
def start_run():
    try:
        return manager.start()
    except RunInProgress:
        raise HTTPException(status_code=409, detail="A run is already in progress.")
    except RunError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/runs")
def get_runs():
    with session(settings.db_path) as conn:
        return metrics.list_runs(conn)


@app.get("/api/metrics")
def get_metrics(run_id: int | None = None):
    with session(settings.db_path) as conn:
        if run_id is None:
            run_id = metrics.latest_done_run_id(conn)
            if run_id is None:
                raise HTTPException(status_code=404, detail="No finished runs yet.")
        data = metrics.full_metrics(conn, run_id, settings)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} doesn't exist or didn't finish.")
    return data


@app.get("/api/history")
def get_history():
    with session(settings.db_path) as conn:
        return metrics.history(conn)


# Serve the built frontend (npm run build) from the same server, if present.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
