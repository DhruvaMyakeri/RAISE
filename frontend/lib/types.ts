// Types mirroring backend/api JSON shapes.

export interface Company {
  id: string;
  name: string;
  category: string;
  category_key: string;
}

export type FlagType =
  | "input_claim"
  | "output_sanity_check"
  | "branch_unknown";

export interface FlaggedAssumption {
  text: string;
  raw: string;
  type: FlagType;
  cited_fact_id: string | null;
}

export interface Citation {
  fact_id: string;
  claim: string;
  source: string;
}

export interface ScenarioTriple {
  conservative: number | null;
  likely: number | null;
  optimistic: number | null;
}

export interface MetricsTable {
  roi_3yr: ScenarioTriple;
  payback_months: ScenarioTriple;
  annual_value_usd: ScenarioTriple;
  total_cost_3y_usd: ScenarioTriple;
  tickets_deflected_annual?: ScenarioTriple;
  additional_conversions_annual?: ScenarioTriple;
  maintenance_savings_annual?: ScenarioTriple;
  avoided_downtime_value_annual?: ScenarioTriple;
}

export interface CostBreakdown {
  build_usd?: number;
  inference_y1_usd?: number;
  integration_y1_usd?: number;
  model_update_y1_usd?: number;
  inference_y2_usd?: number;
  integration_y2_usd?: number;
  model_update_y2_usd?: number;
}

export interface ExplainDimension {
  name: string;
  text: string;
  confidence: number | null;
}

export interface Verdict {
  claim: string;
  verdict: "defensible" | "flagged";
  reasoning: string;
  cited_fact_id?: string;
}

export interface MemoBranch {
  label: string;
  branch_id: string;
  branch_label: string;
  branch_field: string;
  branch_value: string;
  metrics: MetricsTable;
  cost_breakdown_likely: CostBreakdown;
  flagged_assumptions: FlaggedAssumption[];
  citations: Citation[];
  explainability: {
    text: string;
    overall_confidence: number | null;
    dimensions: ExplainDimension[];
  };
  retrieval: {
    reconciled_inputs: Record<string, unknown> | null;
    verdicts: Verdict[];
  };
}

export interface Recommendation {
  winner: "A" | "B" | null;
  reasoning: string;
  confidence_caveat: string;
  text: string;
}

export interface Memo {
  meta: {
    category_key: string;
    project_category: string;
    company_id: string;
    company_name: string;
    project_name: string;
    generated_at: string;
  };
  decision_framing: {
    company_name: string;
    project_name: string;
    project_description: string;
    branch_field: string;
    branch_labels: string[];
    summary: string;
  };
  plan: {
    category: string;
    roi_dimensions: string[];
    missing_fields: string[];
    clarifying_question: string;
    question_field: string;
  };
  branch_plan: {
    branching: boolean;
    branch_field: string;
    branches: Array<Record<string, unknown> & { branch_id: string; label: string }>;
  };
  branches: MemoBranch[];
  recommendation: Recommendation;
}

// ---- Source-data transparency viewer ----
export interface CompanyTestNotes {
  optimistic_claim_field?: string;
  optimistic_claim_value?: unknown;
  why_should_trigger_pushback?: string;
  unknown_trigger_field?: string;
  modeling_tool_field_mapping_notes?: string;
}

export interface CompanyProfile {
  company_id: string;
  company_name: string;
  industry?: string;
  size?: string;
  employees_total?: number;
  annual_revenue_usd?: number;
  project_category: string;
  project_description?: string;
  current_operations?: Record<string, unknown>;
  proposed_project?: Record<string, unknown>;
  unknown_fields?: Record<string, string>;
  notes?: string;
  _test_notes?: CompanyTestNotes;
  [key: string]: unknown;
}

export interface BenchmarkFact {
  id: string;
  claim: string;
  metric?: string;
  value: unknown;
  unit?: string | null;
  source: string;
  source_year?: number | null;
  applies_to?: string[];
  usage_note?: string;
  [key: string]: unknown;
}

export interface BenchmarkCorpus {
  category: string;
  honesty_note?: string;
  facts: BenchmarkFact[];
}

// ---- Streaming events ----
export type AgentEventType =
  | "planner_started"
  | "planner_result"
  | "retrieval_started"
  | "retrieval_claim"
  | "retrieval_complete"
  | "modeling_started"
  | "modeling_result"
  | "explainability_started"
  | "explainability_chunk"
  | "explainability_complete"
  | "recommendation_started"
  | "recommendation_result"
  | "memo_ready"
  | "error";

export interface AgentEvent {
  event: AgentEventType;
  data: Record<string, any>;
}
