import AnswerDetails from "./AnswerDetails";

export default function MessageBubble({ message }) {
  const { role, text, sql, isError } = message;
  return (
    <div className={`bubble ${role} ${isError ? "error" : ""}`}>
      <p className="text">{text}</p>
      {role === "assistant" && sql && <AnswerDetails message={message} />}
    </div>
  );
}
