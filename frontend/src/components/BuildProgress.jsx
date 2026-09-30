function formatDuration(seconds) {
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))} s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} min ${Math.round(seconds % 60)} s`;
}

export default function BuildProgress({ progress }) {
  const { stage, done, total, buildStartedAt, stageStartedAt } = progress;
  const now = Date.now();
  const countsItems = total > 1;
  const percentDone = countsItems ? Math.round((done / total) * 100) : null;

  // Linear estimate from this stage's pace; summaries run in parallel, so it settles after a few tables.
  let timeLeft = "Estimating time left…";
  if (countsItems && done >= total) timeLeft = "Almost done";
  else if (countsItems && done > 0) {
    const secondsPerItem = (now - stageStartedAt) / 1000 / done;
    timeLeft = `About ${formatDuration(secondsPerItem * (total - done))} left`;
  }

  return (
    <div className="build-progress" role="status" aria-live="polite">
      <div className="build-progress-header">
        <strong>{stage || "Preparing the data source"}</strong>
        {countsItems && <span className="muted">{done} of {total} tables</span>}
      </div>
      <div className={`progress-track ${countsItems ? "" : "indeterminate"}`}>
        <div className="progress-fill" style={countsItems ? { width: `${percentDone}%` } : undefined} />
      </div>
      <span className="hint">
        {countsItems ? `${timeLeft} · ` : ""}{formatDuration((now - buildStartedAt) / 1000)} elapsed
      </span>
    </div>
  );
}
