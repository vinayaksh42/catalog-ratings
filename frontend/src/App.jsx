import { useCallback, useEffect, useState } from "react";
import { STATIC, api } from "./api.js";
import { regionName, when } from "./format.js";
import RunControl from "./components/RunControl.jsx";
import Latest from "./components/Latest.jsx";
import History from "./components/History.jsx";

const TOKEN_KEY = "catalog-ratings-admin-token";

export default function App() {
  const [config, setConfig] = useState(null);
  const [status, setStatus] = useState(null);
  const [metrics, setMetrics] = useState(undefined); // undefined = loading, null = no runs
  const [history, setHistory] = useState(null);
  const [runs, setRuns] = useState([]);
  const [view, setView] = useState("latest");
  const [error, setError] = useState(null);

  const loadData = useCallback(async () => {
    try {
      const [m, h, r] = await Promise.all([
        api.metrics().catch((e) => (e.status === 404 ? null : Promise.reject(e))),
        api.history(),
        api.runs(),
      ]);
      setMetrics(m);
      setHistory(h);
      setRuns(r);
      setError(null);
    } catch (e) {
      setError(
        STATIC
          ? `Couldn’t load the dashboard data: ${e.message}.`
          : `Couldn’t load data from the API: ${e.message}. Is the backend running on port 8000?`,
      );
    }
  }, []);

  useEffect(() => {
    api.config().then(setConfig).catch(() => {});
    if (!STATIC) api.status().then(setStatus).catch(() => {});
    loadData();
  }, [loadData]);

  // Poll progress while a run is going; reload everything when it ends.
  useEffect(() => {
    if (!status?.running) return undefined;
    const timer = setInterval(async () => {
      try {
        const next = await api.status();
        setStatus(next);
        if (!next.running) loadData();
      } catch {
        /* keep polling */
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [status?.running, loadData]);

  async function startRun() {
    setError(null);
    try {
      setStatus(await api.startRun(sessionStorage.getItem(TOKEN_KEY)));
    } catch (e) {
      if (e.status === 401) {
        const token = window.prompt("Enter the admin token to start a run");
        if (token) {
          sessionStorage.setItem(TOKEN_KEY, token);
          return startRun();
        }
        return undefined;
      }
      setError(e.message);
    }
    return undefined;
  }

  const region = config ? regionName(config.region) : "your region";
  const platformNames = config ? Object.values(config.platforms) : ["Netflix", "Prime Video", "Disney+"];
  const nameList = `${platformNames.slice(0, -1).join(", ")} and ${platformNames.at(-1)}`;
  const rtEnabled = Boolean(config?.rotten_tomatoes);

  return (
    <div className="app">
      <header className="masthead">
        <div className="title-block">
          <h1>Catalog ratings</h1>
          <p className="lede">
            How well the {nameList} catalogs in {region} are rated on IMDb{rtEnabled && " and Rotten Tomatoes"}, and how that shifts
            from one run to the next.
          </p>
          {metrics && <p className="as-of">Showing run {metrics.run.id}, finished {when(metrics.run.finished_at)}</p>}
        </div>
        {STATIC ? (
          <p className="run-message">Updated weekly.</p>
        ) : (
          <RunControl status={status} onStart={startRun} canStart={config?.tmdb_configured !== false} />
        )}
      </header>

      {!STATIC && config && !config.tmdb_configured && (
        <p className="notice">Add TMDB_API_KEY to backend/.env and restart the backend to start collecting data.</p>
      )}
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}

      <nav className="views" aria-label="Views">
        <button aria-pressed={view === "latest"} onClick={() => setView("latest")}>
          Latest run
        </button>
        <button aria-pressed={view === "history"} onClick={() => setView("history")}>
          History
        </button>
      </nav>

      <main>
        {view === "latest" &&
          (metrics === undefined ? (
            <p className="empty">Loading…</p>
          ) : metrics === null ? (
            <section className="section first-run">
              <h2>No runs yet</h2>
              <p>
                A run collects the current catalogs from TMDB, matches every title to IMDb, and records its ratings.
                The first one takes longest because every title has to be matched once; later runs only match new
                arrivals.
              </p>
            </section>
          ) : (
            <Latest metrics={metrics} rtEnabled={rtEnabled} />
          ))}
        {view === "history" && <History history={history} runs={runs} rtEnabled={rtEnabled} />}
      </main>

      <footer className="footer">
        <p>
          Catalog data from TMDB (via JustWatch). This product uses the TMDB API but is not endorsed or certified by
          TMDB. Ratings from IMDb’s non-commercial datasets{rtEnabled && " and from OMDb"}.
        </p>
      </footer>
    </div>
  );
}
