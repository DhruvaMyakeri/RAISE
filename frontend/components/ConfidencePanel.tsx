import type { MemoBranch } from "@/lib/types";
import { buildProvenance } from "@/lib/provenance";
import { ConfidenceRing } from "./ConfidenceRing";
import { DimensionRow } from "./DimensionRow";

export function ConfidencePanel({
  branch,
  tag,
}: {
  branch: MemoBranch;
  tag: "A" | "B";
}) {
  const dims = branch.explainability.dimensions ?? [];
  const flags = branch.flagged_assumptions ?? [];
  const inputs = buildProvenance(branch.retrieval?.reconciled_inputs);
  const hasClaimed = inputs.some((i) => i.claimed);

  return (
    <div className={`conf-panel ${tag === "B" ? "b" : ""}`}>
      <div className="conf-head">
        <span className="tag">{tag}</span>
        <span className="name">{(branch.branch_label || branch.label || "").replace(/^Scenario [AB]\s*—\s*/, "")}</span>
        <ConfidenceRing value={branch.explainability.overall_confidence} />
      </div>

      <div className="conf-body">
        {dims.map((d, i) => (
          <DimensionRow key={i} dim={d} flags={flags} />
        ))}
      </div>

      {inputs.length ? (
        <div className="provenance">
          <div className="prov-legend">
            <span>
              <i style={{ background: "var(--real)" }} /> verified company data
            </span>
            {hasClaimed ? (
              <span>
                <i style={{ background: "var(--flagged)" }} /> claimed / flagged
              </span>
            ) : null}
          </div>
          <div className="prov-chips">
            {inputs.map((inp) => (
              <span key={inp.key} className={`prov-chip ${inp.claimed ? "claimed" : "real"}`}>
                <span className="prov-dot" />
                {inp.label} <b>{inp.value}</b>
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
