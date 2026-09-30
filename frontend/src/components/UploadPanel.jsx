import { useRef, useState } from "react";
import BuildProgress from "./BuildProgress";
import ConnectPanel from "./ConnectPanel";

function FilePicker({ title, hint, accept, pattern, selectedFiles, setFiles }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);
  const updateSelectedFiles = (fileList) => setFiles(
    Array.from(fileList).filter((uploadedFile) => pattern.test(uploadedFile.name)));

  return (
    <div>
      <div
        className={`dropzone ${dragging ? "dragging" : ""}`}
        onClick={() => inputRef.current.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          updateSelectedFiles(event.dataTransfer.files);
        }}
      >
        <input ref={inputRef} type="file" accept={accept} multiple hidden
          onChange={(event) => updateSelectedFiles(event.target.files)} />
        <strong>{title}</strong>
        <span className="muted">{hint}</span>
      </div>
      {selectedFiles.length > 0 && (
        <ul className="filelist">
          {selectedFiles.map((uploadedFile) => (
            <li key={uploadedFile.name}>
              {uploadedFile.name} <span className="muted">{(uploadedFile.size / 1024).toFixed(1)} KB</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function UploadPanel({ onBuildDataset, loading, buildProgress }) {
  const [sourceMode, setSourceMode] = useState("upload");
  const [tableFiles, setTableFiles] = useState([]);
  const [queryLogFiles, setQueryLogFiles] = useState([]);
  const [columnDescriptions, setColumnDescriptions] = useState("");
  const [datasetDescription, setDatasetDescription] = useState("");
  const [connectionDetails, setConnectionDetails] = useState({ url: "", schema: "", tables: "" });

  return (
    <section className="card upload">
      <div className="source-tabs" role="tablist" aria-label="Data source">
        <button type="button" role="tab" aria-selected={sourceMode === "upload"} className={sourceMode === "upload" ? "active" : ""}
          onClick={() => setSourceMode("upload")}>Upload files</button>
        <button type="button" role="tab" aria-selected={sourceMode === "connect"} className={sourceMode === "connect" ? "active" : ""}
          onClick={() => setSourceMode("connect")}>Connect database</button>
      </div>

      {sourceMode === "upload" ? (
        <>
          <h2>Tables</h2>
          <FilePicker
            title="Drop your table files here"
            hint="or click to choose · .csv, .txt, .tsv or .xlsx Excel workbook · comma, tab, | or ; separated"
            accept=".csv,.txt,.tsv,.xlsx"
            pattern={/\.(csv|txt|tsv|xlsx)$/i}
            selectedFiles={tableFiles}
            setFiles={setTableFiles}
          />
        </>
      ) : (
        <ConnectPanel onChange={setConnectionDetails} />
      )}

      <h2>
        SQL query logs <span className="muted">(optional)</span>
      </h2>
      <FilePicker
        title="Drop past SQL queries here"
        hint="a .sql or .txt file of SELECT queries separated by ; · table names must match the source"
        accept=".sql,.txt"
        pattern={/\.(sql|txt)$/i}
        selectedFiles={queryLogFiles}
        setFiles={setQueryLogFiles}
      />

      <label className="field">
        Explain unclear columns, one per line <span className="muted">(optional)</span>
        <textarea
          rows={3}
          value={columnDescriptions}
          onChange={(event) => setColumnDescriptions(event.target.value)}
          placeholder={"marks: exam score out of 100\namt: order amount in rupees"}
        />
      </label>

      <label className="field">
        What is this dataset about? <span className="muted">(optional)</span>
        <textarea
          rows={2}
          value={datasetDescription}
          onChange={(event) => setDatasetDescription(event.target.value)}
          placeholder="For example, this is a school dataset of students and their assessment scores."
        />
      </label>

      <button className="primary" disabled={(sourceMode === "upload" ? !tableFiles.length : !connectionDetails.url.trim()) || loading}
        onClick={() => onBuildDataset(sourceMode, sourceMode === "upload" ? { files: tableFiles } : connectionDetails,
          queryLogFiles, columnDescriptions, datasetDescription)}>
        {loading ? "Building the index…" : "Build index"}
      </button>
      {buildProgress && <BuildProgress progress={buildProgress} />}
    </section>
  );
}
