import { useEffect, useRef, useState } from "react";
import MessageBubble from "./MessageBubble";

export default function ChatWindow({ messages, loading, suggestions, onAsk }) {
  const [questionText, setQuestionText] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function submitQuestion(event) {
    event.preventDefault();
    if (!questionText.trim() || loading) return;
    onAsk(questionText);
    setQuestionText("");
  }

  return (
    <section className="card chat">
      <div className="messages">
        {messages.length === 0 && (
          <div className="empty">
            <p>Ask anything about your data.</p>
            {suggestions.length > 0 && (
              <div className="chips">
                {suggestions.map((suggestedQuestion) => (
                  <button key={suggestedQuestion} className="chip" disabled={loading} onClick={() => onAsk(suggestedQuestion)}>
                    {suggestedQuestion}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((message, messageIndex) => (
          <MessageBubble key={messageIndex} message={message} />
        ))}
        {loading && <div className="bubble assistant thinking">Thinking…</div>}
        <div ref={bottomRef} />
      </div>

      <form className="composer" onSubmit={submitQuestion}>
        <input
          value={questionText}
          onChange={(event) => setQuestionText(event.target.value)}
          placeholder="e.g. Which subject has the lowest average marks?"
          disabled={loading}
        />
        <button className="primary" type="submit" disabled={loading || !questionText.trim()}>
          Ask
        </button>
      </form>
    </section>
  );
}
