import { useState } from "react";

const RATING_TICKS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

/* One catalog as a barcode: a mark at each 0.1 rating step, darker where more titles sit. */
export function RatingStrip({ density, summary, color, label }) {
  const W = 1000;
  const H = 60;
  const x = (r) => ((r - 1) / 9) * W;
  const max = Math.max(1, ...density);
  const hasBand = summary.p25 != null && summary.p75 != null;

  return (
    <svg
      className="strip"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={`${label}: median ${summary.median ?? "n/a"}, middle half between ${summary.p25 ?? "n/a"} and ${summary.p75 ?? "n/a"}`}
    >
      <rect x="0" y="0" width={W} height={H} fill="var(--strip-bg)" />
      {hasBand && (
        <rect x={x(summary.p25)} y="0" width={x(summary.p75) - x(summary.p25)} height={H} fill={color} opacity="0.1" />
      )}
      {density.map((c, i) =>
        c > 0 ? (
          <rect
            key={i}
            x={x(1 + i / 10) - 3.5}
            y="8"
            width="7"
            height={H - 16}
            fill={color}
            opacity={0.14 + 0.86 * Math.sqrt(c / max)}
          />
        ) : null
      )}
      {summary.median != null && (
        <line
          x1={x(summary.median)}
          x2={x(summary.median)}
          y1="0"
          y2={H}
          stroke="var(--ink)"
          strokeWidth="2.5"
          vectorEffect="non-scaling-stroke"
        />
      )}
    </svg>
  );
}

export function StripAxis() {
  return (
    <div className="strip-axis" aria-hidden="true">
      {RATING_TICKS.map((t) => (
        <span key={t} style={{ left: `${((t - 1) / 9) * 100}%` }}>
          {t}
        </span>
      ))}
    </div>
  );
}

/* Overlaid step outlines: share of each catalog per half-point of rating. */
export function Histogram({ series }) {
  const W = 1000;
  const H = 300;
  const m = { l: 52, r: 12, t: 14, b: 34 };
  const peak = Math.max(0.05, ...series.flatMap((s) => s.values));
  const maxY = Math.ceil(peak / 0.05) * 0.05;
  const x = (r) => m.l + ((r - 1) / 9) * (W - m.l - m.r);
  const y = (s) => m.t + (1 - s / maxY) * (H - m.t - m.b);
  const gridSteps = [0, maxY / 2, maxY];

  const path = (values) => {
    let d = `M ${x(1)} ${y(0)}`;
    values.forEach((v, i) => {
      d += ` L ${x(1 + i * 0.5)} ${y(v)} L ${x(1 + (i + 1) * 0.5)} ${y(v)}`;
    });
    return `${d} L ${x(10)} ${y(0)} Z`;
  };

  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Rating distribution by platform">
        {gridSteps.map((g) => (
          <g key={g}>
            <line x1={m.l} x2={W - m.r} y1={y(g)} y2={y(g)} className="grid" />
            <text x={m.l - 10} y={y(g) + 5} className="tick" textAnchor="end">
              {Math.round(g * 100)}%
            </text>
          </g>
        ))}
        {RATING_TICKS.map((t) => (
          <text key={t} x={x(t)} y={H - 8} className="tick" textAnchor="middle">
            {t}
          </text>
        ))}
        {series.map((s) => (
          <path
            key={s.key}
            d={path(s.values)}
            fill={s.color}
            fillOpacity="0.07"
            stroke={s.color}
            strokeWidth="2.5"
            strokeLinejoin="round"
          />
        ))}
      </svg>
      <Legend series={series} />
    </figure>
  );
}

/* Multi-series line chart over runs, with a hover readout. */
export function LineChart({ labels, series, format }) {
  const [hover, setHover] = useState(null);
  const W = 1000;
  const H = 320;
  const m = { l: 64, r: 24, t: 16, b: 38 };
  const values = series.flatMap((s) => s.values).filter((v) => v != null);
  if (!values.length) return <p className="empty">No data for this measure yet.</p>;

  let lo = Math.min(...values);
  let hi = Math.max(...values);
  const pad = hi === lo ? Math.abs(hi) * 0.05 || 1 : (hi - lo) * 0.15;
  lo -= pad;
  hi += pad;

  const n = labels.length;
  const innerW = W - m.l - m.r;
  const x = (i) => (n === 1 ? m.l + innerW / 2 : m.l + (i / (n - 1)) * innerW);
  const y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
  const ticks = [0, 1, 2, 3].map((k) => lo + ((hi - lo) * (k + 0.5)) / 4);
  const labelEvery = Math.max(1, Math.ceil(n / 8));

  const segments = (vals) => {
    const parts = [];
    let current = "";
    vals.forEach((v, i) => {
      if (v == null) {
        if (current) parts.push(current);
        current = "";
      } else {
        current += `${current ? " L" : "M"} ${x(i)} ${y(v)}`;
      }
    });
    if (current) parts.push(current);
    return parts;
  };

  const slot = n > 1 ? innerW / (n - 1) : innerW;

  return (
    <figure className="chart line-chart" onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="History of the selected measure by platform">
        {ticks.map((t, k) => (
          <g key={k}>
            <line x1={m.l} x2={W - m.r} y1={y(t)} y2={y(t)} className="grid" />
            <text x={m.l - 10} y={y(t) + 5} className="tick" textAnchor="end">
              {format(t)}
            </text>
          </g>
        ))}
        {labels.map((l, i) =>
          i % labelEvery === 0 || i === n - 1 ? (
            <text
              key={i}
              x={x(i)}
              y={H - 10}
              className="tick"
              textAnchor={n > 1 && i === n - 1 ? "end" : n > 1 && i === 0 ? "start" : "middle"}
            >
              {l}
            </text>
          ) : null
        )}
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={m.t} y2={H - m.b} className="hover-line" />}
        {series.map((s) => (
          <g key={s.key}>
            {segments(s.values).map((d, k) => (
              <path key={k} d={d} fill="none" stroke={s.color} strokeWidth="2.5" strokeLinejoin="round" />
            ))}
            {s.values.map((v, i) =>
              v == null ? null : (
                <circle key={i} cx={x(i)} cy={y(v)} r={hover === i ? 6 : 4} fill="var(--surface)" stroke={s.color} strokeWidth="2.5" />
              )
            )}
          </g>
        ))}
        {labels.map((_, i) => (
          <rect
            key={i}
            x={x(i) - slot / 2}
            y={m.t}
            width={slot}
            height={H - m.t - m.b}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
          />
        ))}
      </svg>
      {hover != null && (
        <div
          className="readout"
          style={{ left: `${(x(hover) / W) * 100}%` }}
          data-side={x(hover) > W * 0.65 ? "left" : "right"}
        >
          <p className="readout-title">{labels[hover]}</p>
          {series.map((s) => (
            <p key={s.key}>
              <span className="swatch" style={{ background: s.color }} />
              {s.label} <strong>{s.values[hover] == null ? "–" : format(s.values[hover])}</strong>
            </p>
          ))}
        </div>
      )}
      <Legend series={series} />
    </figure>
  );
}

export function Legend({ series }) {
  return (
    <figcaption className="legend">
      {series.map((s) => (
        <span key={s.key}>
          <span className="swatch" style={{ background: s.color }} />
          {s.label}
        </span>
      ))}
    </figcaption>
  );
}

/* Horizontal bar that diverges from zero, for the drift / catalog split. */
export function DivergingBar({ value, scale, label }) {
  const width = value == null ? 0 : Math.min(Math.abs(value) / scale, 1) * 50;
  const dir = value == null || value === 0 ? "flat" : value > 0 ? "up" : "down";
  return (
    <div className="diverging" aria-label={label}>
      <span className="axis" />
      <span className={`fill ${dir}`} style={dir === "up" ? { left: "50%", width: `${width}%` } : { right: "50%", width: `${width}%` }} />
    </div>
  );
}
