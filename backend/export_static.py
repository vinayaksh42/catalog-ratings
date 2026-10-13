"""Run the pipeline once, then export the dashboard's data as static JSON files.

Used by the scheduled GitHub Actions workflow to publish the dashboard on GitHub Pages
without a server. Run from backend/:

    python export_static.py --out ../frontend/dist/data
    python export_static.py --out ../frontend/dist/data --skip-run   # export only
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from app import metrics
from app.config import settings
from app.db import init_db, session
from app.main import get_config
from app.pipeline import RunError, RunManager

log = logging.getLogger("export_static")


def run_once() -> bool:
    manager = RunManager(settings)
    try:
        state = manager.start()
    except RunError as exc:
        log.error("%s", exc)
        return False
    log.info("Run %s started", state["run_id"])
    manager.wait()
    state = manager.state()
    if state["error"]:
        log.error("Run %s failed: %s", state["run_id"], state["error"])
        return False
    log.info("Run %s finished: %s", state["run_id"], state["detail"])
    return True


def export(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with session(settings.db_path) as conn:
        files = {
            "config.json": get_config(),
            "runs.json": metrics.list_runs(conn),
            "history.json": metrics.history(conn),
        }
        run_id = metrics.latest_done_run_id(conn)
        if run_id is not None:
            files["metrics.json"] = metrics.full_metrics(conn, run_id, settings)
    for name, data in files.items():
        (out / name).write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    log.info("Wrote %s to %s", ", ".join(files), out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="Folder to write the JSON files into")
    parser.add_argument("--skip-run", action="store_true", help="Only export what's already in the database")
    args = parser.parse_args()

    init_db(settings.db_path)
    ok = args.skip_run or run_once()
    if ok:
        export(args.out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
