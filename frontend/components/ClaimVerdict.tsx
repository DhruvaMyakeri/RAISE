import type { Verdict } from "@/lib/types";
import { IconCheck, IconFlag } from "./icons";

export function ClaimVerdict({ verdict }: { verdict: Verdict }) {
  const flagged = verdict.verdict === "flagged";
  const cls = flagged ? "flagged" : "defensible";
  return (
    <div className={`claim ${cls}`}>
      <div className="claim-badge">{flagged ? <IconFlag /> : <IconCheck />}</div>
      <div className="claim-main">
        <div className="claim-title">
          <span>{verdict.claim}</span>
          <span className={`verdict-pill ${cls}`}>{verdict.verdict}</span>
        </div>
        {verdict.reasoning ? (
          <div className="claim-reason">{verdict.reasoning}</div>
        ) : null}
        {verdict.cited_fact_id && verdict.cited_fact_id !== "none" ? (
          <div className="claim-ref">ref: {verdict.cited_fact_id}</div>
        ) : null}
      </div>
    </div>
  );
}
