import { renderBold } from "@/lib/format";

export function StreamingText({
  text,
  streaming,
}: {
  text: string;
  streaming: boolean;
}) {
  if (!text && streaming) {
    return (
      <div className="stream-placeholder">
        <span className="spinner" /> waiting for the model to reason
        <span className="dots" />
      </div>
    );
  }
  const parts = renderBold(text);
  return (
    <div className="stream">
      {parts.map((p, i) =>
        p.b ? <strong key={i}>{p.t}</strong> : <span key={i}>{p.t}</span>
      )}
      {streaming ? <span className="caret" /> : null}
    </div>
  );
}
