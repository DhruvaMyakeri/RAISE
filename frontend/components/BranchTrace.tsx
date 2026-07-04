import type { BranchState } from "@/lib/useAgentRun";
import { fmtRoi, fmtMonths, titleize } from "@/lib/format";
import { StageShell } from "./StageShell";
import { ClaimVerdict } from "./ClaimVerdict";
import { StreamingText } from "./StreamingText";
import { IconRetrieval, IconModeling, IconExplain } from "./icons";

const SCENARIO_ORDER = ["conservative", "likely", "optimistic"];

export function BranchTrace({
  branch,
  tag,
}: {
  branch: BranchState;
  tag: string;
}) {
  const claims = branch.retrieval.claims;
  return (
    <div className="branch-group fade-up">
      <div className="branch-banner">
        <span className="branch-tag">{tag}</span>
        <span className="branch-name">{branch.label.replace(/^Scenario [AB]\s*—\s*/, "")}</span>
        <span className="branch-field">
          {titleize(branch.field)}: {branch.value.replace(/_/g, "-")}
        </span>
      </div>

      <div className="branch-stages">
        {/* Retrieval */}
        <StageShell
          icon={<IconRetrieval />}
          title="Retrieval & Claim Validation"
          subtitle="Rerank grounding → LLM judges each claim vs. benchmark evidence"
          agent="Kimi-K2.6"
          status={branch.retrieval.status}
        >
          {branch.retrieval.status !== "pending" ? (
            claims.length ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {claims.map((c, i) => (
                  <ClaimVerdict key={i} verdict={c} />
                ))}
              </div>
            ) : branch.retrieval.status === "running" ? (
              <div className="stream-placeholder">
                <span className="spinner" /> validating claims against the benchmark corpus
                <span className="dots" />
              </div>
            ) : null
          ) : null}
        </StageShell>

        {/* Modeling */}
        <StageShell
          icon={<IconModeling />}
          title="Modeling Tool"
          subtitle="Deterministic HTEC ROI — conservative / likely / optimistic"
          agent="Python"
          status={branch.modeling.status}
        >
          {branch.modeling.status !== "pending" ? (
            <div className="scenario-row">
              {SCENARIO_ORDER.map((name) => {
                const s = branch.modeling.scenarios[name];
                return (
                  <div key={name} className={`scenario-chip ${name === "likely" ? "likely" : ""}`}>
                    <div className="lbl">{name}</div>
                    <div className="roi">{s ? fmtRoi(s.roi) : "…"}</div>
                    <div className="pb">
                      {s ? `payback ${fmtMonths(s.payback_months)}` : ""}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : null}
        </StageShell>

        {/* Explainability */}
        <StageShell
          icon={<IconExplain />}
          title="Explainability"
          subtitle="Slalom ROI dimensions + confidence, streamed live"
          agent="Nemotron"
          status={branch.explainability.status}
        >
          {branch.explainability.status !== "pending" ? (
            <StreamingText
              text={branch.explainability.text}
              streaming={branch.explainability.status === "running"}
            />
          ) : null}
        </StageShell>
      </div>
    </div>
  );
}
