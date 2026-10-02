import { useState } from "react";
import { LineChart } from "./Charts.jsx";
import { PLATFORM_COLORS, count, num, pct, shortDate, when } from "../format.js";

const MEASURES = [
  { key: "mean", label: "Mean", format: (v) => num(v, 2) },
  { key: "median", label: "Median", format: (v) => num(v, 2) },
  { key: "weighted_mean", label: "Vote-weighted mean", format: (v) => num(v, 2) },
  { key: "share_8plus", label: "Rated 8 or higher", format: (v) => pct(v, 1) },
  { key: "share_below5", label: "Rated under 5", format: (v) => pct(v, 1) },
  { key: "std", label: "Spread", format: (v) => num(v, 2) },
  { key: "catalog_size", label: "Catalog size", format: (v) => count(Math.round(v)) },
  { key: "rt_mean", label: "Tomatometer average", format: (v) => `${num(v)}%`, rt: true },
  { key: "rt_fresh_share", label: "Fresh share", format: (v) => pct(v, 1), rt: true },
];

export default function History({ history, runs, rtEnabled }) {
  const [measureKey, setMeasureKey] = useState("mean");
  const measures = MEASURES.filter((m) => rtEnabled || !m.rt);
  const measure = measures.find((m) => m.key === measureKey) ?? measures[0];
  const points = history?.runs ?? [];
  const platformKeys = Object.keys(history?.platforms ?? {});

  const labels = points.map((r) => shortDate(r.finished_at));
  const series = platformKeys.map((k) => ({
    key: k,
    label: history.platforms[k],
    color: PLATFORM_COLORS[k],
    values: points.map((r) => r.platforms[k]?.[measure.key] ?? null),
  }));

  return (
    <>
      <section className="section">
        <div className="section-head">
          <h2>Over time</h2>
          <p>Each point is one finished run. Choose what to plot.</p>
        </div>
        <div className="measure-picker">
          <label htmlFor="measure">Measure</label>
          <select id="measure" value={measure.key} onChange={(e) => setMeasureKey(e.target.value)}>
            {measures.map((m) => (
              <option key={m.key} value={m.key}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
        {points.length === 0 ? (
          <p className="empty">No finished runs yet.</p>
        ) : (
          <>
            {points.length === 1 && (
              <p className="note">Only one run so far, so each line is a single point. Trends appear from the second run.</p>
            )}
            <LineChart labels={labels} series={series} format={measure.format} />
          </>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Run log</h2>
        </div>
        {runs.length === 0 ? (
          <p className="empty">Nothing has run yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="runs">
              <thead>
                <tr>
                  <th scope="col">Run</th>
                  <th scope="col">Started</th>
                  <th scope="col">Status</th>
                  <th scope="col">Titles</th>
                  <th scope="col">Notes</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td className="num">{r.id}</td>
                    <td>{when(r.started_at)}</td>
                    <td>
                      <span className={`status ${r.status}`}>{r.status === "done" ? "Finished" : r.status === "running" ? "Running" : "Failed"}</span>
                    </td>
                    <td className="num">{count(r.titles)}</td>
                    <td className="notes">{r.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
