import type { FlaggedAssumption } from "./types";
import { fmtUsd } from "./format";

// Input keys that represent a *claimed / projected* value (as opposed to a
// measured operating baseline). These are the inputs the retrieval layer
// scrutinizes and the modeling layer clamps. Everything else is treated as
// verified company-provided operating data.
const CLAIMED_KEYS = new Set([
  "claimed_conversion_lift_rate",
  "claimed_overall_deflection_rate",
  "claimed_tier1_deflection_rate",
  "implied_overall_deflection_rate",
  "claimed_maintenance_spend_reduction_rate",
  "annual_inference_budget_usd",
]);

// Branch-decision fields are surfaced in the scenario banner, not as inputs.
const BRANCH_FIELDS = new Set([
  "hosting_architecture",
  "data_enrichment_strategy",
  "hardware_deployment_method",
]);

export interface ProvenanceInput {
  key: string;
  label: string;
  value: string;
  claimed: boolean;
}

export function humanizeInputKey(key: string): string {
  const s = key
    .replace(/_usd$/, "")
    .replace(/_rate$/, "")
    .replace(/_/g, " ")
    .trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function formatInputValue(key: string, value: unknown): string {
  if (typeof value !== "number") return String(value);
  if (key.includes("usd")) return fmtUsd(value);
  if ((key.includes("rate") || key.includes("share")) && value <= 1) {
    return `${(value * 100).toFixed(value < 0.1 ? 1 : 0)}%`;
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

export function buildProvenance(
  reconciled: Record<string, unknown> | null | undefined
): ProvenanceInput[] {
  if (!reconciled) return [];
  const out: ProvenanceInput[] = [];
  for (const [key, value] of Object.entries(reconciled)) {
    if (BRANCH_FIELDS.has(key)) continue;
    out.push({
      key,
      label: humanizeInputKey(key),
      value: formatInputValue(key, value),
      claimed: CLAIMED_KEYS.has(key),
    });
  }
  // real data first, claimed after
  return out.sort((a, b) => Number(a.claimed) - Number(b.claimed));
}

// Keywords used to associate a flag with a Slalom dimension's reasoning text.
function flagKeywords(flag: FlaggedAssumption): string[] {
  const raw = flag.raw.toLowerCase();
  const kws: string[] = [];
  if (flag.cited_fact_id) kws.push(flag.cited_fact_id.toLowerCase());
  if (flag.type === "output_sanity_check") {
    if (raw.includes("payback")) kws.push("payback");
    if (raw.includes("roi")) kws.push("roi");
    if (raw.includes("ceiling")) kws.push("ceiling");
  } else if (flag.type === "branch_unknown") {
    kws.push("architecture", "deployment", "hosting", "unknown");
  } else {
    // input_claim
    for (const phrase of [
      "conversion lift",
      "deflection",
      "spend reduction",
      "inference",
      "operating budget",
      "operating cost",
    ]) {
      if (raw.includes(phrase)) kws.push(phrase);
    }
  }
  return kws;
}

export function linkFlagsToDimension(
  dimText: string,
  flags: FlaggedAssumption[]
): FlaggedAssumption[] {
  const lower = dimText.toLowerCase();
  return flags.filter((f) => {
    const kws = flagKeywords(f);
    return kws.some((k) => k && lower.includes(k));
  });
}

export function flagTypeLabel(type: string): string {
  if (type === "input_claim") return "input claim";
  if (type === "output_sanity_check") return "output sanity check";
  if (type === "branch_unknown") return "unresolved branch";
  return type;
}
