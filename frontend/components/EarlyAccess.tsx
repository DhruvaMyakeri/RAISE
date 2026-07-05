"use client";

import { useState } from "react";
import { submitEarlyAccess } from "@/lib/api";
import { IconArrow, IconCheck } from "./icons";

type State =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "registered" }
  | { kind: "already" }
  | { kind: "error"; message: string };

export function EarlyAccess() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });

  const done = state.kind === "registered" || state.kind === "already";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (state.kind === "submitting") return;
    setState({ kind: "submitting" });
    try {
      const status = await submitEarlyAccess(email.trim());
      setState({ kind: status === "registered" ? "registered" : "already" });
    } catch (err) {
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : "Something went wrong.",
      });
    }
  }

  return (
    <div className="early-access">
      <div className="ea-copy">
        <span className="ea-tag">Early access</span>
        <span className="ea-line">Want this for your company? Join the list.</span>
      </div>

      {done ? (
        <div className="ea-done">
          <IconCheck />
          {state.kind === "registered"
            ? "Thanks, we'll be in touch."
            : "You're already on the list."}
        </div>
      ) : (
        <form className="ea-form" onSubmit={handleSubmit}>
          <input
            type="email"
            required
            placeholder="you@company.com"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              if (state.kind === "error") setState({ kind: "idle" });
            }}
            disabled={state.kind === "submitting"}
            aria-label="Work email"
          />
          <button
            type="submit"
            disabled={state.kind === "submitting" || !email.trim()}
          >
            {state.kind === "submitting" ? "…" : <>Notify me <IconArrow /></>}
          </button>
        </form>
      )}

      {state.kind === "error" ? (
        <span className="ea-error">{state.message}</span>
      ) : null}
    </div>
  );
}
