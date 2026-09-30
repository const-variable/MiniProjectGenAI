import { useState } from "react";
import { askQuestion, connectDatabase, deleteSession, getSuggestions, uploadFiles } from "./api";
import UploadPanel from "./components/UploadPanel";
import DatasetSummary from "./components/DatasetSummary";
import ChatWindow from "./components/ChatWindow";

export default function App() {
  const [session, setSession] = useState(null); // { session_id, summary, tables }
  const [messages, setMessages] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleBuild(mode, payload, logFiles, descriptions) {
    setError("");
    setLoading(true);
    try {
      const data = mode === "upload"
        ? await uploadFiles(payload.files, logFiles, descriptions)
        : await connectDatabase(payload.url, payload.schema, payload.tables, logFiles, descriptions);
      setSession(data);
      setMessages([]);
      getSuggestions(data.session_id)
        .then((r) => setSuggestions(r.questions || []))
        .catch(() => setSuggestions([]));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleAsk(question) {
    const q = question.trim();
    if (!q || loading || !session) return;
    setMessages((m) => [...m, { role: "user", text: q }]);
    setLoading(true);
    setError("");
    try {
      const r = await askQuestion(session.session_id, q);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: r.answer,
          sql: r.sql,
          topN: r.top_n_tables,
          selected: r.selected_tables,
          similar: r.similar_queries,
          result: r.result,
          error: r.error,
        },
      ]);
    } catch (e) {
      if (e.status === 404) {
        setSession(null);
        setError("Your session expired. Please build the dataset again.");
      } else {
        setMessages((m) => [...m, { role: "assistant", text: `Something went wrong: ${e.message}`, isError: true }]);
      }
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    if (session) deleteSession(session.session_id).catch(() => {});
    setSession(null);
    setMessages([]);
    setSuggestions([]);
    setError("");
  }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Table RAG</h1>
          <p className="muted">Upload a table. Ask questions in plain English.</p>
        </div>
        {session && (
          <button className="ghost" onClick={reset}>
            New dataset
          </button>
        )}
      </header>

      {error && <div className="alert">{error}</div>}

      {!session ? (
        <UploadPanel onBuild={handleBuild} loading={loading} />
      ) : (
        <main className="workspace">
          <DatasetSummary
            sessionId={session.session_id}
            summary={session.summary}
            tables={session.tables}
            queryLogs={session.query_logs}
            source={session.source}
          />
          <ChatWindow messages={messages} loading={loading} suggestions={suggestions} onAsk={handleAsk} />
        </main>
      )}
    </div>
  );
}
