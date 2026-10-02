export default function RunControl({ status, onStart, canStart }) {
  const running = status?.running;
  const pctDone = Math.round((status?.progress ?? 0) * 100);

  return (
    <div className="run-control">
      <button className="primary" onClick={onStart} disabled={running || !canStart}>
        {running ? "Run in progress" : "Start a run"}
      </button>
      {running && (
        <div className="progress" role="status" aria-live="polite">
          <div className="bar" aria-hidden="true">
            <span style={{ width: `${pctDone}%` }} />
          </div>
          <p>
            <strong>{status.step}</strong> {status.detail}
          </p>
        </div>
      )}
      {!running && status?.error && <p className="run-message error">The last run failed. {status.error}</p>}
      {!running && !status?.error && status?.step === "Finished" && (
        <p className="run-message">Run finished. {status.detail}</p>
      )}
    </div>
  );
}
