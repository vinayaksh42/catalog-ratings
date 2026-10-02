import { useState } from "react";
import { DivergingBar, Histogram, RatingStrip, StripAxis } from "./Charts.jsx";
import { PLATFORM_COLORS, count, num, pct, shortDate, signed, signedPoints, trend } from "../format.js";

export default function Latest({ metrics, rtEnabled }) {
  const keys = Object.keys(metrics.platforms);
  return (
    <>
      <Overview metrics={metrics} keys={keys} />
      <Distribution metrics={metrics} keys={keys} />
      <Changes metrics={metrics} keys={keys} />
      {rtEnabled && <Critics metrics={metrics} keys={keys} />}
      <Breakdown metrics={metrics} keys={keys} />
    </>
  );
}

function SectionHead({ title, children }) {
  return (
    <div className="section-head">
      <h2>{title}</h2>
      {children && <p>{children}</p>}
    </div>
  );
}

/* -- Overview: the three strips ------------------------------------------- */
function Overview({ metrics, keys }) {
  return (
    <section className="section">
      <SectionHead title="Where each catalog sits">
        Every mark is a rating on IMDb’s 1–10 scale; darker marks mean more titles at that rating. The shaded band
        holds the middle half of the catalog and the dark line is the median. Titles with fewer than{" "}
        {count(metrics.min_votes)} IMDb votes are left out.
      </SectionHead>
      <div className="strips">
        {keys.map((k) => (
          <PlatformStrip key={k} id={k} data={metrics.platforms[k]} />
        ))}
        <div className="strip-row axis-row">
          <span />
          <StripAxis />
        </div>
      </div>
    </section>
  );
}

function PlatformStrip({ id, data }) {
  const s = data.summary;
  const change = data.change;
  const color = PLATFORM_COLORS[id];

  if (!s.catalog_size) {
    return (
      <article className="strip-row" style={{ "--c": color }}>
        <div className="strip-id">
          <h3>{data.label}</h3>
        </div>
        <p className="empty">This run found no titles for {data.label}.</p>
      </article>
    );
  }

  return (
    <article className="strip-row" style={{ "--c": color }}>
      <div className="strip-id">
        <h3>{data.label}</h3>
        <p className="median">
          <span className="figure">{num(s.median)}</span>
          <span className="figure-label">median</span>
        </p>
      </div>
      <div className="strip-body">
        <RatingStrip density={data.density} summary={s} color={color} label={data.label} />
        <dl className="stat-row">
          <Stat term="Mean" value={num(s.mean, 2)} delta={change?.mean_change} />
          <Stat term="Vote-weighted mean" value={num(s.weighted_mean, 2)} delta={change?.deltas.weighted_mean} />
          <Stat term="Rated 8 or higher" value={pct(s.share_8plus, 1)} delta={change?.deltas.share_8plus} points />
          <Stat term="Rated under 5" value={pct(s.share_below5, 1)} delta={change?.deltas.share_below5} points invert />
          <Stat term="Spread (std. dev.)" value={num(s.std, 2)} />
          <Stat term="Titles rated" value={`${count(s.rated_count)} of ${count(s.catalog_size)}`} />
        </dl>
      </div>
    </article>
  );
}

function Stat({ term, value, delta, points = false, invert = false }) {
  const direction = trend(delta, points ? 0.0005 : 0.005);
  const tone = direction === "flat" ? "flat" : (direction === "up") !== invert ? "good" : "bad";
  return (
    <div>
      <dt>{term}</dt>
      <dd>
        {value}
        {delta != null && (
          <span className={`delta ${tone}`} title="Change since the previous run">
            {points ? signedPoints(delta) : signed(delta)}
          </span>
        )}
      </dd>
    </div>
  );
}

/* -- Distribution ----------------------------------------------------------- */
function Distribution({ metrics, keys }) {
  const series = keys
    .filter((k) => metrics.platforms[k].summary.rated_count > 0)
    .map((k) => ({
      key: k,
      label: metrics.platforms[k].label,
      color: PLATFORM_COLORS[k],
      values: metrics.platforms[k].histogram,
    }));
  if (!series.length) return null;
  return (
    <section className="section">
      <SectionHead title="Rating distribution">
        Share of each catalog in every half-point band, so catalogs of different sizes can be compared directly.
      </SectionHead>
      <Histogram series={series} />
    </section>
  );
}

/* -- Changes since the previous run ------------------------------------------ */
function Changes({ metrics, keys }) {
  if (!metrics.previous_run) {
    return (
      <section className="section">
        <SectionHead title="What changed" />
        <p className="empty">
          Comparisons start from the second run. Start another run later to see how ratings and catalogs have moved.
        </p>
      </section>
    );
  }

  const effects = keys.flatMap((k) => {
    const c = metrics.platforms[k].change;
    return c ? [c.drift_effect, c.catalog_effect] : [];
  });
  const scale = Math.max(0.05, ...effects.filter((v) => v != null).map(Math.abs));

  return (
    <section className="section">
      <SectionHead title={`What changed since ${shortDate(metrics.previous_run.finished_at)}`}>
        A platform’s mean can move for two reasons: titles already there were re-rated by IMDb users, or titles
        came and went. The two effects add up to the total change.
      </SectionHead>
      <div className="change-grid">
        {keys.map((k) => {
          const p = metrics.platforms[k];
          const c = p.change;
          if (!c || !p.summary.catalog_size) return null;
          return (
            <article key={k} className="change-col" style={{ "--c": PLATFORM_COLORS[k] }}>
              <h3>{p.label}</h3>
              <p className={`change-total ${trend(c.mean_change)}`}>
                {signed(c.mean_change, 3)}
                <span>change in mean rating</span>
              </p>
              <div className="effects">
                <p>Existing titles re-rated</p>
                <DivergingBar value={c.drift_effect} scale={scale} label="Effect of re-rating" />
                <p className="effect-value">{signed(c.drift_effect, 3)}</p>
                <p>Titles added or removed</p>
                <DivergingBar value={c.catalog_effect} scale={scale} label="Effect of catalog changes" />
                <p className="effect-value">{signed(c.catalog_effect, 3)}</p>
              </div>
              <dl className="churn">
                <div>
                  <dt>Added</dt>
                  <dd>
                    {count(c.added)} titles{c.added_mean != null && <>, averaging {num(c.added_mean, 2)}</>}
                  </dd>
                </div>
                <div>
                  <dt>Removed</dt>
                  <dd>
                    {count(c.removed)} titles{c.removed_mean != null && <>, averaging {num(c.removed_mean, 2)}</>}
                  </dd>
                </div>
              </dl>
              <TitleMini heading="Most-watched additions" items={c.added_examples} />
              <TitleMini heading="Most-watched departures" items={c.removed_examples} />
              <TitleMini heading="Rising on IMDb" items={c.rising} showChange />
              <TitleMini heading="Falling on IMDb" items={c.falling} showChange />
            </article>
          );
        })}
      </div>
    </section>
  );
}

function TitleMini({ heading, items, showChange = false }) {
  if (!items?.length) return null;
  return (
    <div className="mini">
      <h4>{heading}</h4>
      <ul>
        {items.map((t) => (
          <li key={`${t.imdb_id}-${t.title}`}>
            <TitleLink t={t} />
            <span className="num">{showChange ? signed(t.change, 1) : num(t.imdb_rating)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TitleLink({ t }) {
  const text = `${t.title}${t.year ? ` (${t.year})` : ""}`;
  return t.imdb_id ? (
    <a href={`https://www.imdb.com/title/${t.imdb_id}/`} target="_blank" rel="noreferrer">
      {text}
    </a>
  ) : (
    <span>{text}</span>
  );
}

/* -- Critics vs audience ----------------------------------------------------- */
function Critics({ metrics, keys }) {
  const anyRt = keys.some((k) => metrics.platforms[k].summary.rt_count > 0);
  return (
    <section className="section">
      <SectionHead title="Critics and audiences">
        Tomatometer scores come from OMDb. Because of OMDb’s daily request limit they fill in over several runs;
        coverage shows how far along that is. The gap compares each title’s Tomatometer (scaled to 0–10) with its
        IMDb rating, so a negative gap means critics liked it less than IMDb users did.
      </SectionHead>
      {!anyRt ? (
        <p className="empty">No Rotten Tomatoes scores yet. They’ll appear after the next run.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Platform</th>
                <th scope="col">Tomatometer average</th>
                <th scope="col">Fresh (60% or more)</th>
                <th scope="col">Critics minus IMDb</th>
                <th scope="col">Metascore average</th>
                <th scope="col">Coverage</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => {
                const s = metrics.platforms[k].summary;
                return (
                  <tr key={k} style={{ "--c": PLATFORM_COLORS[k] }}>
                    <th scope="row">
                      <span className="swatch" />
                      {metrics.platforms[k].label}
                    </th>
                    <td>{s.rt_mean == null ? "–" : `${num(s.rt_mean)}%`}</td>
                    <td>{pct(s.rt_fresh_share)}</td>
                    <td>{signed(s.critic_gap)}</td>
                    <td>{num(s.metascore_mean)}</td>
                    <td>
                      {pct(s.rt_coverage)} <span className="muted">({count(s.rt_count)} titles)</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/* -- Per-platform breakdown -------------------------------------------------- */
function Breakdown({ metrics, keys }) {
  const available = keys.filter((k) => metrics.platforms[k].summary.rated_count > 0);
  const [selected, setSelected] = useState(available[0]);
  if (!available.length) return null;
  const active = available.includes(selected) ? selected : available[0];
  const p = metrics.platforms[active];
  const s = p.summary;

  return (
    <section className="section" style={{ "--c": PLATFORM_COLORS[active] }}>
      <SectionHead title="Inside a catalog" />
      <div className="segmented" role="group" aria-label="Choose a platform">
        {available.map((k) => (
          <button
            key={k}
            aria-pressed={k === active}
            onClick={() => setSelected(k)}
            style={{ "--c": PLATFORM_COLORS[k] }}
          >
            {metrics.platforms[k].label}
          </button>
        ))}
      </div>

      <div className="breakdown">
        <div className="type-split">
          <h3>Movies and shows</h3>
          <dl>
            <div>
              <dt>Movies</dt>
              <dd>
                <span className="figure-sm">{num(s.movies_mean, 2)}</span>
                <span className="muted">{count(s.movie_count)} titles</span>
              </dd>
            </div>
            <div>
              <dt>Shows</dt>
              <dd>
                <span className="figure-sm">{num(s.shows_mean, 2)}</span>
                <span className="muted">{count(s.show_count)} titles</span>
              </dd>
            </div>
          </dl>

          <h3>By genre</h3>
          <ul className="genres">
            {p.genres.map((g) => (
              <li key={g.genre}>
                <span className="genre-name">{g.genre}</span>
                <span className="genre-bar" aria-hidden="true">
                  <span style={{ width: `${((g.mean - 1) / 9) * 100}%` }} />
                </span>
                <span className="num">{num(g.mean, 2)}</span>
                <span className="muted num">{count(g.count)}</span>
              </li>
            ))}
          </ul>
        </div>

        <RankList heading="Highest rated" items={p.top} minVotes={metrics.list_min_votes} />
        <RankList heading="Lowest rated" items={p.bottom} minVotes={metrics.list_min_votes} />
      </div>
    </section>
  );
}

function RankList({ heading, items, minVotes }) {
  return (
    <div className="rank">
      <h3>{heading}</h3>
      <p className="muted small">Titles with at least {count(minVotes)} votes</p>
      {items.length ? (
        <ol>
          {items.map((t) => (
            <li key={`${t.imdb_id}-${t.title}`}>
              <TitleLink t={t} />
              <span className="num">{num(t.imdb_rating)}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="empty">No titles meet the vote threshold yet.</p>
      )}
    </div>
  );
}
