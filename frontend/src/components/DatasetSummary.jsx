import { useState } from "react";
import { getPreview } from "../api";
import ResultTable from "./ResultTable";

export default function DatasetSummary({ sessionId, summary, tables, queryLogs, source, relationships = [] }) {
  const [tablePreviews, setTablePreviews] = useState(null);
  const [showPreview, setShowPreview] = useState(false);

  async function toggleTablePreview() {
    if (!tablePreviews) {
      try {
        const previewPayload = await getPreview(sessionId);
        setTablePreviews(previewPayload.tables);
      } catch {
        setTablePreviews([]);
      }
    }
    setShowPreview((previewVisible) => !previewVisible);
  }

  return (
    <aside className="card summary">
      <h2>Dataset overview</h2>
      {source && <p className="source-badge">{source.kind} · {source.dialect} · {source.name}</p>}
      <p className="text">{summary}</p>
      <p className="muted">
        Vector index: {tables.length} table summar{tables.length === 1 ? "y" : "ies"} + {queryLogs} past quer
        {queryLogs === 1 ? "y" : "ies"}
      </p>

      {relationships.length > 0 && (
        <section className="relationships">
          <h3>Relationships</h3>
          <ul>{relationships.map((relation) => {
            const key = `${relation.table_a}.${relation.column_a}-${relation.table_b}.${relation.column_b}`;
            return <li key={key}>{relation.table_a}.{relation.column_a} → {relation.table_b}.{relation.column_b}</li>;
          })}</ul>
        </section>
      )}

      {tables.map((table) => (
        <details key={table.name} className="table-info">
          <summary>
            <strong>{table.name}</strong> <span className="muted">{table.rows.toLocaleString()} rows</span>
          </summary>
          <p className="table-summary">{table.summary}</p>
          {table.example_questions?.length > 0 && (
            <details className="question-examples">
              <summary>Example questions</summary>
              <ul>{table.example_questions.map((question) => <li key={question}>{question}</li>)}</ul>
            </details>
          )}
          <ul className="columns">
            {table.columns.map((column) => (
              <li key={column.name}>
                <span>{column.name}</span>
                <span className={`tag ${column.type}`}>{column.type}</span>
              </li>
            ))}
          </ul>
        </details>
      ))}

      <button className="ghost" onClick={toggleTablePreview}>
        {showPreview ? "Hide data preview" : "Show data preview"}
      </button>
      {showPreview &&
        (tablePreviews || []).map((tablePreview) => (
          <div key={tablePreview.name}>
            <h3 className="preview-title">{tablePreview.name}</h3>
            <ResultTable columns={tablePreview.columns} rows={tablePreview.rows} />
          </div>
        ))}
    </aside>
  );
}
