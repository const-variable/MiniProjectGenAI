import { useRef, useState } from "react";
import ConnectPanel from "./ConnectPanel";

function FilePicker({ title, hint, accept, pattern, files, setFiles }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);
  const take = (list) => setFiles(Array.from(list).filter((f) => pattern.test(f.name)));

  return (
    <div>
      <div
        className={`dropzone ${dragging ? "dragging" : ""}`}
        onClick={() => inputRef.current.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          take(e.dataTransfer.files);
        }}
      >
        <input ref={inputRef} type="file" accept={accept} multiple hidden onChange={(e) => take(e.target.files)} />
        <strong>{title}</strong>
        <span className="muted">{hint}</span>
      </div>
      {files.length > 0 && (
        <ul className="filelist">
          {files.map((f) => (
            <li key={f.name}>
              {f.name} <span className="muted">{(f.size / 1024).toFixed(1)} KB</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function UploadPanel({ onBuild, loading }) {
  const [mode, setMode] = useState("upload");
  const [files, setFiles] = useState([]);
  const [logFiles, setLogFiles] = useState([]);
  const [descriptions, setDescriptions] = useState("");
  const [connection, setConnection] = useState({ url: "", schema: "", tables: "" });

  return (
    <section className="card upload">
      <div className="source-tabs" role="tablist" aria-label="Data source">
        <button type="button" role="tab" aria-selected={mode === "upload"} className={mode === "upload" ? "active" : ""}
          onClick={() => setMode("upload")}>Upload files</button>
        <button type="button" role="tab" aria-selected={mode === "connect"} className={mode === "connect" ? "active" : ""}
          onClick={() => setMode("connect")}>Connect database</button>
      </div>

      {mode === "upload" ? (
        <>
          <h2>Tables</h2>
          <FilePicker
            title="Drop your table files here"
            hint="or click to choose · .csv, .txt, .tsv · comma, tab, | or ; separated"
            accept=".csv,.txt,.tsv"
            pattern={/\.(csv|txt|tsv)$/i}
            files={files}
            setFiles={setFiles}
          />
        </>
      ) : (
        <ConnectPanel onChange={setConnection} />
      )}

      <h2>
        2. SQL query logs <span className="muted">optional</span>
      </h2>
      <FilePicker
        title="Drop past SQL queries here"
        hint="a .sql or .txt file of SELECT queries separated by ; · table names must match the source"
        accept=".sql,.txt"
        pattern={/\.(sql|txt)$/i}
        files={logFiles}
        setFiles={setLogFiles}
      />

      <label className="field">
        Optional: explain unclear columns, one per line
        <textarea
          rows={3}
          value={descriptions}
          onChange={(e) => setDescriptions(e.target.value)}
          placeholder={"marks: exam score out of 100\namt: order amount in rupees"}
        />
      </label>

      <button className="primary" disabled={(mode === "upload" ? !files.length : !connection.url.trim()) || loading}
        onClick={() => onBuild(mode, mode === "upload" ? { files } : connection, logFiles, descriptions)}>
        {loading ? "Building the index…" : "Build index"}
      </button>
    </section>
  );
}
