// Empty base = same origin (Vite proxy in dev, FastAPI serving the build in production).
// Set VITE_API_BASE if the API lives on a different host.
const BASE = import.meta.env?.VITE_API_BASE ?? "";

// Static mode (VITE_STATIC_DATA=1 at build time): read JSON files exported by
// backend/export_static.py from ./data/ instead of calling the API. Used for GitHub Pages.
export const STATIC = import.meta.env?.VITE_STATIC_DATA === "1";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body.detail) message = body.detail;
    } catch {
      /* not JSON */
    }
    const error = new Error(message);
    error.status = res.status;
    throw error;
  }
  return res.json();
}

const file = (name) => request(`./data/${name}.json`, { cache: "no-cache" });

export const api = STATIC
  ? {
      config: () => file("config"),
      runs: () => file("runs"),
      history: () => file("history"),
      metrics: () => file("metrics"),
    }
  : {
      config: () => request("/api/config"),
      status: () => request("/api/status"),
      runs: () => request("/api/runs"),
      history: () => request("/api/history"),
      metrics: (runId) => request(runId ? `/api/metrics?run_id=${runId}` : "/api/metrics"),
      startRun: (token) =>
        request("/api/runs", { method: "POST", headers: token ? { "X-Admin-Token": token } : {} }),
    };
