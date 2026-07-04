import type { RunState } from "@/lib/useAgentRun";
import { StageShell } from "./StageShell";
import { BranchTrace } from "./BranchTrace";
import { StreamingText } from "./StreamingText";
import { IconPlanner, IconRecommend, IconArrow } from "./icons";

export function AgentTrace({ state }: { state: RunState }) {
  const { planner, branches, recommendation } = state;

  return (
    <div className="trace">
      {/* Planner */}
      <StageShell
        icon={<IconPlanner />}
        title="Planner"
        subtitle={
          planner.plan
            ? `${planner.plan.category} · branching on "${(planner.branchField ?? "").replace(/_/g, " ")}"`
            : "Classifying project, detecting unknowns, deciding branches"
        }
        agent="Kimi-K2.6"
        status={planner.status}
      >
        {planner.plan ? (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {planner.plan.roi_dimensions.map((d) => (
              <span key={d} className="chip" style={{ fontSize: 11 }}>
                {d}
              </span>
            ))}
            {planner.plan.missing_fields.map((f) => (
              <span
                key={f}
                className="chip"
                style={{ fontSize: 11, borderColor: "var(--flagged)", color: "var(--flagged)" }}
              >
                unknown: {f.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        ) : null}
      </StageShell>

      {branches.length ? (
        <div className="branch-split-label eyebrow" style={{ padding: "6px 2px" }}>
          Two scenarios · analyzed in parallel paths
        </div>
      ) : null}

      {branches.map((b, i) => (
        <BranchTrace key={b.id} branch={b} tag={i === 0 ? "A" : "B"} />
      ))}

      {/* Recommendation */}
      {recommendation.status !== "pending" ? (
        <StageShell
          icon={<IconRecommend />}
          title="Recommendation"
          subtitle="Weighs ROI, cost, flagged assumptions & confidence across branches"
          agent="MiniMax-M2.7"
          status={recommendation.status}
        >
          {recommendation.data ? (
            <div className="rec-card" style={{ border: "none", padding: 0, background: "none" }}>
              {recommendation.data.winner ? (
                <div className="rec-winner">
                  <IconArrow /> Recommends Scenario {recommendation.data.winner}
                </div>
              ) : null}
              <StreamingText text={recommendation.data.reasoning} streaming={false} />
              {recommendation.data.confidence_caveat ? (
                <div className="rec-caveat">{recommendation.data.confidence_caveat}</div>
              ) : null}
            </div>
          ) : recommendation.status === "running" ? (
            <div className="stream-placeholder">
              <span className="spinner" /> weighing tradeoffs between branches
              <span className="dots" />
            </div>
          ) : null}
        </StageShell>
      ) : null}
    </div>
  );
}
