# Catalog ratings

A local dashboard that tracks how well the Netflix, Prime Video and Disney+ catalogs in one country are rated on IMDb (and optionally Rotten Tomatoes), and how that changes between runs.

Each run pulls the current catalogs, attaches ratings, and saves a snapshot. The dashboard shows the latest snapshot, what changed since the previous one, and how every measure has moved over time.

## Where the data comes from

| What | Source | Notes |
|---|---|---|
| Which titles are on each platform | TMDB API (watch-provider data from JustWatch) | Free key. No streaming logins needed. |
| IMDb rating and vote count | IMDb's official daily dataset | One ~8 MB download per run covers every title. |
| Rotten Tomatoes Tomatometer, Metascore | OMDb API | Optional, off by default (`ROTTEN_TOMATOES=true` plus `OMDB_API_KEY` turns it on). Free tier is 1,000 calls/day, so scores fill in over several runs (most-voted titles first) and are re-checked every 30 days. OMDb has no RT audience score. |

## Setup

You need Python 3.10+ and Node 20+.

**1. Get API keys**

- TMDB: create an account, then request a key at https://www.themoviedb.org/settings/api
- OMDb (optional): https://www.omdbapi.com/apikey.aspx

**2. Backend**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then paste your keys into .env
uvicorn app.main:app --reload --port 8000
```

**3. Frontend** (in a second terminal)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and press **Start a run**.

**Tip:** set `MAX_PAGES=3` in `backend/.env` for a quick test run first (about 60 titles per platform and type), then set it back to `0` and restart for the full catalog.

## How a run works

1. For each platform, ask TMDB for every movie and show on its subscription tier in `REGION`. Queries over TMDB's 10,000-result cap are split by release date automatically.
2. Match titles to IMDb IDs. Only titles never seen before need a lookup, so later runs are much faster than the first.
3. Download IMDb's daily ratings file and attach rating and vote count.
4. If Rotten Tomatoes is switched on, spend today's remaining OMDb budget on Rotten Tomatoes lookups.
5. Save the snapshot and a summary per platform.

## What the dashboard shows

- **Where each catalog sits:** every rated title on the 1–10 scale, with median, middle half, mean, vote-weighted mean, share rated 8+, share under 5, and spread. Changes since the last run appear next to each number.
- **Rating distribution:** share of each catalog in every half-point band.
- **What changed:** the change in mean rating, split into the part caused by existing titles being re-rated and the part caused by titles arriving or leaving (the two add up exactly), plus notable additions, departures, and titles rising or falling on IMDb.
- **Critics and audiences** (only when Rotten Tomatoes is switched on): Tomatometer average, fresh share, the critic-vs-IMDb gap, Metascore, and how much of the catalog has an RT score yet.
- **Inside a catalog:** movies vs shows, averages by genre, highest and lowest rated.
- **History:** any of the measures above plotted across all runs, plus a run log.

Titles with fewer than `MIN_VOTES` IMDb votes (default 100) are left out of the statistics so a few obscure titles can't skew them.

## API

| Method | Path | |
|---|---|---|
| GET | `/api/config` | Region, platforms, which keys are set |
| GET | `/api/status` | Progress of the current run |
| POST | `/api/runs` | Start a run (needs `X-Admin-Token` if `ADMIN_TOKEN` is set) |
| GET | `/api/runs` | Run log |
| GET | `/api/metrics?run_id=` | Full metrics for a run (latest if omitted), compared with the run before it |
| GET | `/api/history` | Summary per platform for every finished run |

Interactive docs: http://localhost:8000/docs

## Publishing on GitHub Pages (free, updated every 3 days)

`.github/workflows/update.yml` runs the pipeline on GitHub Actions every 3 days at 06:00 UTC (the 1st, 4th, 7th … of each month) and publishes the dashboard as a static site on GitHub Pages. No server is involved: `backend/export_static.py` writes the dashboard's data as JSON files, and the frontend, built with `VITE_STATIC_DATA=1`, reads those instead of calling the API. The run button is hidden; start a run from the **Actions** tab instead (**Update dashboard → Run workflow**).

The SQLite database (title-to-IMDb matches and every past run) lives as `catalog.db` on a GitHub release tagged `data`, not in git, so the repo stays small. Each run downloads it, adds a run and uploads it back. If there's no `data` release yet, the first run builds a new database, which takes about 20 minutes.

One-time setup (public repo):

1. Push this project to a new public GitHub repository.
2. **Settings → Secrets and variables → Actions → New repository secret:** `TMDB_READ_TOKEN` = your TMDB API Read Access Token.
3. **Settings → Pages → Source:** GitHub Actions.
4. Optional, to keep your local history and skip the slow first run: upload your local database first:
   `gh release create data backend/data/catalog.db --title "Dashboard database" --latest=false --notes "Used by the scheduled workflow."`
5. **Actions → Update dashboard → Run workflow.** The site appears at `https://<user>.github.io/<repo>/`.

Region and other settings for the online run are in the workflow's `env:` block. Don't delete the `data` release: it holds the history.

## Running your own server instead

- Set `ADMIN_TOKEN` so strangers can't start runs (the dashboard will ask for it).
- Run `npm run build` in `frontend/`. The backend serves `frontend/dist` automatically, so one server hosts both. Set `CORS_ORIGINS` only if the frontend lives on a different domain.
- For scheduled runs, call `POST /api/runs` from cron or a scheduled job.
- SQLite is fine for a single server. If you move to managed hosting with an ephemeral disk, point `DATA_DIR` at a persistent volume or switch the storage layer to Postgres.
- **Check the terms before going public.** IMDb's datasets are licensed for personal, non-commercial use only; TMDB requires the attribution already in the footer and has its own terms for commercial use; OMDb has its own terms too.

## Project layout

```
backend/
  app/
    main.py        FastAPI routes
    pipeline.py    One run, end to end, plus the background runner
    metrics.py     Statistics and run-to-run comparison
    db.py          SQLite schema
    config.py      Settings and platform definitions
    sources/       TMDB, IMDb dataset and OMDb clients
  export_static.py One run plus a JSON export, for GitHub Pages
.github/workflows/
  update.yml       Runs every 3 days on GitHub Actions, deployed to GitHub Pages
frontend/
  src/
    App.jsx        Layout, data loading, run polling
    components/    Latest run, History, charts (plain SVG, no chart library)
```
