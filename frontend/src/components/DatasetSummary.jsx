import { useState } from "react";
import { getPreview } from "../api";
import ResultTable from "./ResultTable";

export default function DatasetSummary({ sessionId, summary, tables, queryLogs, source }) {
  const [preview, setPreview] = useState(null);
  const [showPreview, setShowPreview] = useState(false);

  async function togglePreview() {
    if (!preview) {
      try {
        const r = await getPreview(sessionId);
        setPreview(r.tables);
      } catch {
        setPreview([]);
      }
    }
    setShowPreview((v) => !v);
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

      {tables.map((t) => (
        <details key={t.name} className="table-info">
          <summary>
            <strong>{t.name}</strong> <span className="muted">{t.rows.toLocaleString()} rows</span>
          </summary>
          <p className="table-summary">{t.summary}</p>
          <ul className="columns">
            {t.columns.map((c) => (
              <li key={c.name}>
                <span>{c.name}</span>
                <span className={`tag ${c.type}`}>{c.type}</span>
              </li>
            ))}
          </ul>
        </details>
      ))}

      <button className="ghost" onClick={togglePreview}>
        {showPreview ? "Hide data preview" : "Show data preview"}
      </button>
      {showPreview &&
        (preview || []).map((t) => (
          <div key={t.name}>
            <h3 className="preview-title">{t.name}</h3>
            <ResultTable columns={t.columns} rows={t.rows} />
          </div>
        ))}
    </aside>
  );
}
