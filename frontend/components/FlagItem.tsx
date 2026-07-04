import type { FlaggedAssumption } from "@/lib/types";
import { flagTypeLabel } from "@/lib/provenance";

export function FlagItem({ flag }: { flag: FlaggedAssumption }) {
  return (
    <div className={`flag-item ${flag.type}`}>
      <div className="bar" />
      <div className="fmain">
        <span className={`flag-type ${flag.type}`}>{flagTypeLabel(flag.type)}</span>
        <div className="flag-text">{flag.text}</div>
        {flag.cited_fact_id && flag.cited_fact_id !== "none" ? (
          <div className="flag-cite">cited: {flag.cited_fact_id}</div>
        ) : null}
      </div>
    </div>
  );
}
