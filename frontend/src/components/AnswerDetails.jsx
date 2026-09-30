import ResultTable from "./ResultTable";

export default function AnswerDetails({ message }) {
  const { topN = [], selected = [], similar = [], sql, result, scoreKind = "distance",
    selectionReason, sqlExplanation, question, standaloneQuestion } = message;
  return (
    <details className="details">
      <summary>How this was answered</summary>
      {standaloneQuestion && standaloneQuestion !== question && (
        <p className="hint">Interpreted as: {standaloneQuestion}</p>
      )}

      <h4>1 · Similarity search → Top N tables</h4>
      <div className="chips small">
        {topN.map((t) => (
          <span key={t.name} className={`chip static ${selected.includes(t.name) ? "picked" : ""}`}>
            {t.name} <span className="score">{t.score.toFixed(2)}</span>
          </span>
        ))}
      </div>
      <p className="hint">{scoreKind === "rank" ? "Score = reciprocal rank (higher is better)." : "Score = embedding distance (lower is more similar)."}</p>

      <h4>2 · LLM table selection → Top K tables</h4>
      <div className="chips small">
        {selected.map((t) => (
          <span key={t} className="chip static picked">
            {t}
          </span>
        ))}
        {selectionReason && <p className="hint">{selectionReason}</p>}
      </div>

      {similar.length > 0 && (
        <>
          <h4>Similar past queries (from logs)</h4>
          {similar.map((q, i) => (
            <div key={i} className="example">
              <span className="muted">{q.description}</span>
              <pre className="sql small">
                <code>{q.sql}</code>
              </pre>
            </div>
          ))}
        </>
      )}

      <h4>3 · Generated SQL</h4>
      {sqlExplanation && <p className="hint">{sqlExplanation}</p>}
      <pre className="sql">
        <code>{sql}</code>
      </pre>

      <h4>4 · Result</h4>
      <ResultTable columns={result?.columns} rows={result?.rows} />
    </details>
  );
}
