import { useEffect, useRef, useState } from "react";
import MessageBubble from "./MessageBubble";

export default function ChatWindow({ messages, loading, suggestions, onAsk }) {
  const [text, setText] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function submit(e) {
    e.preventDefault();
    if (!text.trim() || loading) return;
    onAsk(text);
    setText("");
  }

  return (
    <section className="card chat">
      <div className="messages">
        {messages.length === 0 && (
          <div className="empty">
            <p>Ask anything about your data.</p>
            {suggestions.length > 0 && (
              <div className="chips">
                {suggestions.map((s) => (
                  <button key={s} className="chip" disabled={loading} onClick={() => onAsk(s)}>
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}
        {loading && <div className="bubble assistant thinking">Thinking…</div>}
        <div ref={bottomRef} />
      </div>

      <form className="composer" onSubmit={submit}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="e.g. Which subject has the lowest average marks?"
          disabled={loading}
        />
        <button className="primary" type="submit" disabled={loading || !text.trim()}>
          Ask
        </button>
      </form>
    </section>
  );
}
