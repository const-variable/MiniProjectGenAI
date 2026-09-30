import ResultTable from "./ResultTable";

export default function AnswerDetails({ message }) {
  const { candidateTables = [], selectedTables = [], similarQueries = [], sql, queryResult,
    scoreKind = "distance", selectionReason, sqlExplanation, question, standaloneQuestion } = message;
  return (
    <details className="details">
      <summary>How this was answered</summary>
      {standaloneQuestion && standaloneQuestion !== question && (
        <p className="hint">Interpreted as: {standaloneQuestion}</p>
      )}

      <h4>1 · Similarity search → Top N tables</h4>
      <div className="chips small">
        {candidateTables.map((candidateTable) => (
          <span key={candidateTable.name} className={`chip static ${selectedTables.includes(candidateTable.name) ? "picked" : ""}`}>
            {candidateTable.name} <span className="score">{candidateTable.score.toFixed(2)}</span>
          </span>
        ))}
      </div>
      <p className="hint">{scoreKind === "rank" ? "Score = reciprocal rank (higher is better)." : "Score = embedding distance (lower is more similar)."}</p>

      <h4>2 · LLM table selection → Top K tables</h4>
      <div className="chips small">
        {selectedTables.map((tableName) => (
          <span key={tableName} className="chip static picked">
            {tableName}
          </span>
        ))}
        {selectionReason && <p className="hint">{selectionReason}</p>}
      </div>

      {similarQueries.length > 0 && (
        <>
          <h4>Similar past queries (from logs)</h4>
          {similarQueries.map((query, queryIndex) => (
            <div key={queryIndex} className="example">
              <span className="muted">{query.description}</span>
              <pre className="sql small">
                <code>{query.sql}</code>
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
      <ResultTable columns={queryResult?.columns} rows={queryResult?.rows} />
    </details>
  );
}
