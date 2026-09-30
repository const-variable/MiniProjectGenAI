import { useState } from "react";
import { testConnection } from "../api";

export default function ConnectPanel({ onChange }) {
  const [connectionUrl, setConnectionUrl] = useState("");
  const [schemaName, setSchemaName] = useState("");
  const [selectedTableNames, setSelectedTableNames] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [testing, setTesting] = useState(false);
  const [connectionFeedback, setConnectionFeedback] = useState(null);

  function updateConnection(sourceChanges) {
    onChange({
      url: connectionUrl,
      schema: schemaName,
      tables: selectedTableNames,
      ...sourceChanges,
    });
  }

  async function checkConnection() {
    setTesting(true);
    setConnectionFeedback(null);
    try {
      const connectionStatus = await testConnection(connectionUrl, schemaName);
      setConnectionFeedback({
        ok: true,
        text: `Connected · ${connectionStatus.count} tables · ${connectionStatus.dialect}`,
      });
    } catch (error) {
      setConnectionFeedback({ ok: false, text: error.message });
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
            value={connectionUrl}
            onChange={(event) => {
              setConnectionUrl(event.target.value);
              updateConnection({ url: event.target.value });
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
          Schema <span className="muted">(optional)</span>
          <input value={schemaName} onChange={(event) => {
            setSchemaName(event.target.value);
            updateConnection({ schema: event.target.value });
          }} placeholder="public" />
        </label>
        <label className="field">
          Tables <span className="muted">(optional)</span> <span className="hint">Comma-separated</span>
          <input value={selectedTableNames} onChange={(event) => {
            setSelectedTableNames(event.target.value);
            updateConnection({ tables: event.target.value });
          }} placeholder="orders, customers, products" />
        </label>
      </div>
      <div className="connect-actions">
        <button type="button" disabled={!connectionUrl.trim() || testing} onClick={checkConnection}>
          {testing ? "Testing…" : "Test connection"}
        </button>
        {connectionFeedback && (
          <span className={connectionFeedback.ok ? "connection-ok" : "connection-error"}>
            {connectionFeedback.text}
          </span>
        )}
      </div>
    </div>
  );
}