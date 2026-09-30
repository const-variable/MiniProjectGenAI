import { useState } from "react";
import { testConnection } from "../api";

export default function ConnectPanel({ onChange }) {
  const [url, setUrl] = useState("");
  const [schema, setSchema] = useState("");
  const [tables, setTables] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  function update(next) {
    onChange({ url, schema, tables, ...next });
  }

  async function checkConnection() {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testConnection(url, schema);
      setTestResult({ ok: true, text: `Connected · ${result.count} tables · ${result.dialect}` });
    } catch (error) {
      setTestResult({ ok: false, text: error.message });
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="connect-fields">
      <label className="field">
        Connection URL
        <div className="secret-field">
          <input
            type={showPassword ? "text" : "password"}
            value={url}
            onChange={(event) => {
              setUrl(event.target.value);
              update({ url: event.target.value });
            }}
            placeholder="postgresql://readonly:password@localhost:5432/database"
            autoComplete="off"
          />
          <button type="button" className="ghost" onClick={() => setShowPassword((value) => !value)}>
            {showPassword ? "Hide" : "Show"}
          </button>
        </div>
        <span className="hint">Use a read-only database user. Examples: sqlite:///path/to/chinook.db, postgresql://readonly:pwd@localhost:5432/chinook</span>
      </label>
      <div className="connect-options">
        <label className="field">
          Schema <span className="muted">optional</span>
          <input value={schema} onChange={(event) => {
            setSchema(event.target.value);
            update({ schema: event.target.value });
          }} placeholder="public" />
        </label>
        <label className="field">
          Tables <span className="muted">optional, comma-separated</span>
          <input value={tables} onChange={(event) => {
            setTables(event.target.value);
            update({ tables: event.target.value });
          }} placeholder="orders, customers, products" />
        </label>
      </div>
      <div className="connect-actions">
        <button type="button" disabled={!url.trim() || testing} onClick={checkConnection}>
          {testing ? "Testing…" : "Test connection"}
        </button>
        {testResult && <span className={testResult.ok ? "connection-ok" : "connection-error"}>{testResult.text}</span>}
      </div>
    </div>
  );
}