import { useState } from "react";
import { askQuestion, connectDatabase, deleteSession, getBuildProgress, getSuggestions, uploadFiles } from "./api";
import UploadPanel from "./components/UploadPanel";
import DatasetSummary from "./components/DatasetSummary";
import ChatWindow from "./components/ChatWindow";

export default function App() {
  const [session, setSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [buildProgress, setBuildProgress] = useState(null);

  async function buildDataset(sourceMode, sourceDetails, logFiles, descriptions, datasetDescription) {
    setError("");
    setLoading(true);
    const progressId = crypto.randomUUID();
    const buildStartedAt = Date.now();
    setBuildProgress({ stage: null, done: 0, total: 0, buildStartedAt, stageStartedAt: buildStartedAt });
    // The build request only returns when finished, so poll its progress alongside it.
    const progressTimer = setInterval(() => {
      getBuildProgress(progressId)
        .then((latestProgress) => setBuildProgress((previousProgress) => previousProgress && {
          ...latestProgress,
          buildStartedAt,
          stageStartedAt: previousProgress.stage === latestProgress.stage
            ? previousProgress.stageStartedAt : Date.now(),
        }))
        .catch(() => {});
    }, 1000);
    try {
      const sessionPayload = sourceMode === "upload"
        ? await uploadFiles(sourceDetails.files, logFiles, descriptions, datasetDescription, progressId)
        : await connectDatabase(sourceDetails.url, sourceDetails.schema, sourceDetails.tables,
          logFiles, descriptions, datasetDescription, progressId);
      setSession(sessionPayload);
      setMessages([]);
      getSuggestions(sessionPayload.session_id)
        .then((suggestionPayload) => setSuggestions(suggestionPayload.questions || []))
        .catch(() => setSuggestions([]));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      clearInterval(progressTimer);
      setBuildProgress(null);
      setLoading(false);
    }
  }

  async function askDatasetQuestion(question) {
    const askedQuestion = question.trim();
    if (!askedQuestion || loading || !session) return;
    setMessages((previousMessages) => [...previousMessages, { role: "user", text: askedQuestion }]);
    setLoading(true);
    setError("");
    try {
      const answerPayload = await askQuestion(session.session_id, askedQuestion);
      setMessages((previousMessages) => [
        ...previousMessages,
        {
          role: "assistant",
          text: answerPayload.answer,
          sql: answerPayload.sql,
          candidateTables: answerPayload.top_n_tables,
          selectedTables: answerPayload.selected_tables,
          similarQueries: answerPayload.similar_queries,
          queryResult: answerPayload.result,
          error: answerPayload.error,
          selectionReason: answerPayload.selection_reason,
          sqlExplanation: answerPayload.sql_explanation,
          scoreKind: answerPayload.score_kind,
          question: askedQuestion,
          standaloneQuestion: answerPayload.standalone_question,
        },
      ]);
    } catch (requestError) {
      if (requestError.status === 404) {
        setSession(null);
        setError("Your session expired. Please build the dataset again.");
      } else {
        setMessages((previousMessages) => [...previousMessages, {
          role: "assistant", text: `Something went wrong: ${requestError.message}`, isError: true,
        }]);
      }
    } finally {
      setLoading(false);
    }
  }

  function startNewDataset() {
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
          <button className="ghost" onClick={startNewDataset}>
            New dataset
          </button>
        )}
      </header>

      {error && <div className="alert">{error}</div>}

      {!session ? (
        <UploadPanel onBuildDataset={buildDataset} loading={loading} buildProgress={buildProgress} />
      ) : (
        <main className="workspace">
          <DatasetSummary
            sessionId={session.session_id}
            summary={session.summary}
            tables={session.tables}
            queryLogs={session.query_logs}
            source={session.source}
            relationships={session.relationships || []}
          />
          <ChatWindow messages={messages} loading={loading} suggestions={suggestions} onAsk={askDatasetQuestion} />
        </main>
      )}
    </div>
  );
}
