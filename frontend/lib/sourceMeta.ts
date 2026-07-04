import type { BenchmarkCorpus, CompanyProfile, CompanyTestNotes } from "./types";

// ---------------------------------------------------------------------------
// Source-tier classification.
// The stored corpus files carry a `source` string but no explicit tier field,
// so we classify for display from the publisher name. This is a presentation
// aid only — the backend returns the raw data unchanged.
//   Tier 1 = major analyst / research firms (McKinsey, Deloitte, Gartner,
//            NVIDIA, Aberdeen, Siemens).
//   Tier 2 = specialist market-research firms (Persistence Market Research,
//            IoT Analytics, Ditstek, Factory AI, Zebracat).
//   Tier 3 = frameworks / cross-source syntheses (HTEC, consensus, standards).
// ---------------------------------------------------------------------------
const TIER1 = [
  "mckinsey",
  "deloitte",
  "gartner",
  "nvidia",
  "aberdeen",
  "siemens",
];
const TIER2 = [
  "persistence market research",
  "iot analytics",
  "ditstek",
  "factory ai",
  "zebracat",
];

export function sourceTier(source: string): 1 | 2 | 3 {
  const s = (source || "").toLowerCase();
  if (TIER1.some((k) => s.includes(k))) return 1;
  if (TIER2.some((k) => s.includes(k))) return 2;
  return 3;
}

export const TIER_LEGEND: Record<1 | 2 | 3, string> = {
  1: "Tier 1 — major analyst firms (McKinsey, Deloitte, Gartner, NVIDIA…)",
  2: "Tier 2 — specialist market-research firms",
  3: "Tier 3 — frameworks & cross-source consensus",
};

// Every corpus file's honesty_note states these are paraphrased published
// figures, not original primary research — i.e. secondary citations.
export function citationType(corpus: BenchmarkCorpus): "primary" | "secondary" {
  const note = (corpus.honesty_note || "").toLowerCase();
  if (note.includes("primary dataset") || note.includes("secondary")) {
    return "secondary";
  }
  return "secondary";
}

// ---------------------------------------------------------------------------
// Load-bearing fact IDs: facts wired into the modeling clamps and the
// output-level sanity check (see backend/modeling/sanity_check.py,
// roi_marketing.py, roi_maintenance.py). These act as ceilings / thresholds
// rather than general narrative context.
// ---------------------------------------------------------------------------
export const LOAD_BEARING_FACTS: Record<string, string[]> = {
  customer_support: [
    "cs_tier1_deflection",
    "mckinsey_roi_multiple",
    "htec_true_op_cost",
    "htec_roi_formula",
    "sector_payback_finance",
  ],
  marketing: [
    "integrated_workflow_performance",
    "realistic_marketing_roi_range",
    "use_case_roi_content_drafting",
    "payback_period_bifurcation",
  ],
  maintenance: [
    "mid_market_realistic_target_range",
    "mid_market_savings_reality",
    "mid_market_implementation_tco",
    "adopter_payback_distribution",
    "average_cross_facility_payback",
  ],
};

export function isLoadBearing(categoryKey: string, factId: string): boolean {
  return (LOAD_BEARING_FACTS[categoryKey] ?? []).includes(factId);
}

// ---------------------------------------------------------------------------
// Fallback highlight metadata for profiles that predate the _test_notes
// convention (Meridian). Values are display-only and describe the claim that
// the retrieval layer scrutinizes against the corpus.
// ---------------------------------------------------------------------------
const FALLBACK_TEST_NOTES: Record<string, CompanyTestNotes> = {
  "meridian-retail-support": {
    optimistic_claim_field: "claimed_tier1_deflection_rate",
    why_should_trigger_pushback:
      "A 50% Tier-1 deflection claim is scrutinized against the ~68% routine-intent benchmark (cs_tier1_deflection); applied across all Tier-1 volume it implies an overall rate near the top of the 20–35% common band, so it is treated as an unvalidated assumption absent a measured pilot.",
    unknown_trigger_field: "hosting_architecture",
  },
};

export function resolveTestNotes(profile: CompanyProfile): CompanyTestNotes {
  if (profile._test_notes && Object.keys(profile._test_notes).length) {
    return profile._test_notes;
  }
  const fb = FALLBACK_TEST_NOTES[profile.company_id];
  if (fb) return fb;
  const unknownField = profile.unknown_fields
    ? Object.keys(profile.unknown_fields)[0]
    : undefined;
  return { unknown_trigger_field: unknownField };
}

// ---------------------------------------------------------------------------
// Value formatting for benchmark facts (values are heterogeneous: scalars,
// {min,max} ranges, and nested objects).
// ---------------------------------------------------------------------------
function fmtLeaf(v: unknown, unit?: string | null): string {
  if (typeof v !== "number") return String(v);
  const u = (unit || "").toLowerCase();
  if (u.includes("fraction")) return `${+(v * 100).toFixed(1)}%`;
  if (u === "x" || u.startsWith("x")) return `${v}x`;
  if (u.includes("month")) return `${v} mo`;
  if (u.includes("usd")) return `$${v.toLocaleString()}`;
  return v.toLocaleString();
}

function humanizeKey(k: string): string {
  return k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export interface ValueRow {
  label?: string;
  text: string;
}

export function formatFactValue(
  value: unknown,
  unit?: string | null
): ValueRow[] {
  if (value == null) return [{ text: "contextual — no single figure" }];
  if (typeof value !== "object") {
    return [{ text: fmtLeaf(value, unit) }];
  }
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj);
  if (
    keys.length === 2 &&
    keys.includes("min") &&
    keys.includes("max") &&
    typeof obj.min !== "object" &&
    typeof obj.max !== "object"
  ) {
    return [{ text: `${fmtLeaf(obj.min, unit)} – ${fmtLeaf(obj.max, unit)}` }];
  }
  const rows: ValueRow[] = [];
  for (const [k, v] of Object.entries(obj)) {
    if (v && typeof v === "object") {
      const sub = v as Record<string, unknown>;
      if ("min" in sub && "max" in sub) {
        rows.push({
          label: humanizeKey(k),
          text: `${fmtLeaf(sub.min, unit)} – ${fmtLeaf(sub.max, unit)}`,
        });
        continue;
      }
      rows.push({ label: humanizeKey(k), text: JSON.stringify(v) });
    } else {
      rows.push({ label: humanizeKey(k), text: fmtLeaf(v, unit) });
    }
  }
  return rows;
}
