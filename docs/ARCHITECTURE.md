   # RAISE — System Architecture (as implemented)

   > **Last updated:** 2026-07-04
   > **Scope:** Customer Support AI vertical slice only.
   > This document describes the system as it actually runs, not the original
   > project-plan.md aspirations. Deviations from the plan are noted inline.

   ---

   ## 1. Pipeline Overview

   Entry point: `backend/pipeline/run_slice.py → run()`

   A single invocation loads one company profile and one benchmark corpus file,
   then executes six stages in order. Stages 2–5 run independently **per
   scenario branch** (max 2), then stage 6 merges both branches into one memo.

   ```
   ┌─────────────────────────────────────────────────────────┐
   │  Stage 1 — Planner  (plan_and_clarify)                  │
   │  Classify project, detect unknowns, ask one question    │
   │                                                         │
   │  Stage 1b — Planner  (branch_on_unknown)                │
   │  User answer is "unknown" → emit 2 architecture         │
   │  branches: A_on_prem, B_cloud                           │
   └───────────────┬─────────────────────┬───────────────────┘
                  │ Branch A            │ Branch B
                  ▼                     ▼
   ┌───────────────────────┐ ┌───────────────────────┐
   │ Stage 2 — Retrieval   │ │ Stage 2 — Retrieval   │
   │ (run_retrieval_       │ │ (run_retrieval_       │
   │  dialogue)            │ │  dialogue)            │
   │ 3 rerank calls per    │ │ 3 rerank calls per    │
   │ branch + LLM claim    │ │ branch + LLM claim    │
   │ validation            │ │ validation            │
   └──────────┬────────────┘ └──────────┬────────────┘
            ▼                         ▼
   ┌───────────────────────┐ ┌───────────────────────┐
   │ Stage 3 — Modeling    │ │ Stage 3 — Modeling    │
   │ Tool via Planner      │ │ Tool via Planner      │
   │ tool call             │ │ tool call             │
   │ (deterministic Python)│ │ (deterministic Python)│
   └──────────┬────────────┘ └──────────┬────────────┘
            ▼                         ▼
   ┌───────────────────────┐ ┌───────────────────────┐
   │ Stage 4 —             │ │ Stage 4 —             │
   │ Explainability Agent  │ │ Explainability Agent  │
   │ (NVIDIA or Vultr      │ │ (NVIDIA or Vultr      │
   │  fallback)            │ │  fallback)            │
   └──────────┬────────────┘ └──────────┬────────────┘
            │                         │
            └────────────┬────────────┘
                           ▼
   ┌─────────────────────────────────────────────────────────┐
   │ Stage 5 — Report Agent                                  │
   │ Merge both branches into one side-by-side memo          │
   │ (Python template + LLM-generated recommendation)        │
   └─────────────────────────────────────────────────────────┘
   ```

   **Files touched per stage:**

   | Stage | File | Entry function |
   |-------|------|---------------|
   | 1 | `backend/agents/planner.py` | `plan_and_clarify(company)` |
   | 1b | `backend/agents/planner.py` | `branch_on_unknown(plan, user_answer)` |
   | 2 | `backend/agents/retrieval.py` | `run_retrieval_dialogue(...)` |
   | 3 | `backend/agents/planner.py` + `backend/modeling/roi.py` | `call_modeling_tool_via_planner(...)` → `modeling_tool_from_args(args)` |
   | 4 | `backend/agents/explainability.py` | `explain_branch(...)` |
   | 5 | `backend/agents/report.py` | `assemble_memo(...)` |

   Supporting modules:

   | File | Purpose |
   |------|---------|
   | `backend/llm/clients.py` | OpenAI-SDK wrappers for Vultr and NVIDIA |
   | `backend/llm/rerank.py` | VultronRetriever `/v1/rerank` HTTP client (httpx) |
   | `backend/config/models.py` | Canonical model catalog IDs |
   | `backend/config/token_budgets.py` | Per-agent `max_tokens` constants |
   | `backend/agents/json_util.py` | `message_text()` (content vs reasoning extraction), `parse_json_object()` |

   ---

   ## 2. Each Agent / Component

   ### 2a. Planner / Orchestrator

   | Property | Value |
   |----------|-------|
   | **Model** | `moonshotai/Kimi-K2.6` (Vultr) |
   | **Fallback model** | `MiniMaxAI/MiniMax-M2.7` (Vultr) |
   | **Provider** | Vultr Serverless Inference (`https://api.vultrinference.com/v1`) |
   | **Token budget** | `max_tokens: 1000` |
   | **Temperature** | 0.2 |

   **Fallback trigger:** any exception on the primary model (network, 404, empty
   tool call). The code iterates `[PLANNER_MODEL, PLANNER_MODEL_FALLBACK]` in
   `_call_planner_for_tool()`.

   **Deviation from plan:** project-plan.md originally specified
   `kimi-k2-instruct`. That string is not in the live Vultr catalog and silently
   routes to MiniMax-M2.7. Code now uses the real catalog IDs exclusively.

   The Planner is invoked **three** times per pipeline run:

   #### Call 1 — `plan_and_clarify`

   **Input:** a user-role message containing the project category, description,
   and `unknown_fields` JSON from the company profile (not the full profile — it
   was trimmed to reduce token usage and avoid the model spending its budget on
   reasoning about irrelevant fields).

   **Prompt (verbatim from code):**
   ```
   You are the Planner/Orchestrator for an AI ROI agent. Call emit_plan.
   project_category='Customer Support AI'
   project_description='Deploy an AI Tier-1 support assistant ...'
   unknown_fields={"hosting_architecture": "unknown"}
   Rules: classify into one of 3 categories; list relevant ROI dimensions;
   any field with value unknown goes in missing_fields; ask one
   clarifying_question for the top missing field.
   ```

   **Output:** structured tool-call arguments from the `emit_plan` function tool
   (enforced via `tool_choice="required"`):

   ```json
   {
   "category": "Customer Support AI",
   "roi_dimensions": ["Cost impact", "Quality impact", ...],
   "missing_fields": ["hosting_architecture"],
   "clarifying_question": "On-prem or cloud?",
   "question_field": "hosting_architecture"
   }
   ```

   **Post-processing in Python:** the model's `roi_dimensions` output is
   discarded and replaced with the hardcoded `ROI_DIMENSIONS_CS` list (5 Slalom
   dimensions relevant to Customer Support AI). The `missing_fields` list is
   merged with any fields whose value is literally `"unknown"` in the company
   profile's `unknown_fields` map. If `hosting_architecture` is missing and the
   model didn't generate a `clarifying_question`, a hardcoded fallback question
   is injected.

   #### Call 2 — `branch_on_unknown`

   **Input:** the prior plan JSON + the user answer string `"unknown"`.

   **Prompt (verbatim from code):**
   ```
   You are the Planner/Orchestrator. The user answered a clarifying question.
   Prior plan: { ... }
   User answer: 'unknown'

   If the answer indicates uncertainty, call emit_branches with exactly 2
   options: on_prem (Scenario A) and cloud (Scenario B). Hard cap: 2 branches.
   ```

   **Output:** structured `emit_branches` tool-call arguments:

   ```json
   {
   "branching": true,
   "branch_field": "hosting_architecture",
   "branches": [
      {"branch_id": "A_on_prem", "label": "Scenario A — On-prem", "hosting_architecture": "on_prem"},
      {"branch_id": "B_cloud",   "label": "Scenario B — Cloud",   "hosting_architecture": "cloud"}
   ]
   }
   ```

   **Post-processing:** branch IDs and labels are normalized to the hardcoded
   defaults (`A_on_prem`, `B_cloud`) regardless of what the model returns, to
   guarantee consistent memo formatting. If the model returns fewer than 2
   branches, the full default set is used.

   #### Call 3 — `call_modeling_tool_via_planner` (once per branch)

   **Input:** system-role message instructing a single tool call + user-role
   message with the branch JSON, reconciled numeric inputs, and flagged
   assumptions.

   **Prompt (verbatim from code):**
   ```
   System: You are the Planner. Call run_modeling_tool exactly once with the
   reconciled numeric inputs. Do not compute ROI yourself.

   User: Branch: {"branch_id": "A_on_prem", ...}
   Reconciled inputs: {"annual_ticket_volume": 480000, ...}
   Flagged assumptions: ["assumption, not validated: ..."]
   Call run_modeling_tool with branch_id, hosting_architecture, and all
   numeric fields. Include flagged_assumptions.
   ```

   **Output:** `run_modeling_tool` tool-call arguments. Python overrides
   `branch_id` and `hosting_architecture` from the orchestrator's own branch
   record (not the model's arguments) for safety. Then `modeling_tool_from_args`
   executes the deterministic computation.

   **Why tool calls, not content?** Kimi-K2.6 and MiniMax-M2.7 both have an
   invisible `reasoning` field that consumes the token budget before `content`
   is populated. Using `tool_choice="required"` forces the model to emit
   structured arguments in the tool call, which is reliably populated even when
   `content` is empty.

   ---

   ### 2b. Internal Retrieval + Benchmark Retrieval

   | Property | Value |
   |----------|-------|
   | **Rerank model** | `vultr/VultronRetrieverCore-Qwen3.5-4.5B` (both agents) |
   | **Provider** | Vultr Serverless Inference |
   | **API route** | `POST /v1/rerank` (NOT `/v1/chat/completions`) |
   | **Rerank token budget** | N/A — rerank is not a generation endpoint |
   | **Claim validation model** | `moonshotai/Kimi-K2.6` (primary), `MiniMaxAI/MiniMax-M2.7` (fallback) |
   | **Claim validation budget** | `max_tokens: 2500` |

   The retrieval stage has two sub-steps: (1) rerank calls to retrieve relevant
   evidence, and (2) an LLM call to validate company claims against that evidence.
   See **§3 Retrieval Layer** below for full mechanism.

   ---

   ### 2c. Modeling Tool

   | Property | Value |
   |----------|-------|
   | **Model** | None — pure deterministic Python |
   | **Files** | `backend/modeling/roi.py` (CS), `roi_marketing.py`, `roi_maintenance.py` |
   | **Entry** | `modeling_tool_from_args(args)`, `marketing_modeling_from_args(args)`, `maintenance_modeling_from_args(args)` |

   See **§4 Modeling Tool — Full Math** below.

   ---

   ### 2d. Explainability Agent

   | Property | Value |
   |----------|-------|
   | **Model (primary)** | `nvidia/nemotron-3-ultra-550b-a55b` (NVIDIA) |
   | **Model (fallback)** | `zai-org/GLM-5.2-FP8` (Vultr) |
   | **Provider (primary)** | NVIDIA build.nvidia.com (`https://integrate.api.nvidia.com/v1`) |
   | **Provider (fallback)** | Vultr Serverless Inference |
   | **Token budget (primary)** | `max_tokens: 16384`, `reasoning_budget: 16384` |
   | **Token budget (fallback)** | `max_tokens: 1200` |
   | **Temperature** | primary: 1.0 (NVIDIA required), fallback: 0.3 |

   **Fallback trigger:** the NVIDIA free-tier rate-limits at ~32 concurrent
   requests (`ResourceExhausted`). The agent retries once after a 5-second
   sleep; on second failure it falls back to GLM-5.2-FP8 on Vultr with a
   printed warning.

   **Input (both primary and fallback receive the same prompt):**
   ```
   You are the Explainability Agent for an AI ROI memo.
   Break down which inputs drove which parts of the projection.
   Use ONLY these Slalom ROI dimensions: [Cost impact, Quality impact,
   Speed to value, Process impact, Technology impact].
   Assign a confidence score (0–100) based on how much input was real company
   data vs flagged-as-assumption from the retrieval dialogue.
   Do NOT recompute ROI numbers — use the Modeling Tool outputs as given.
   Be concise and CFO-readable. Cite flagged assumptions explicitly.

   FORMAT CONSTRAINT: For each Slalom dimension, write at most 2-3 sentences
   covering: (a) which inputs drove the number, (b) any flagged assumptions
   affecting it, and (c) the confidence score. End with a 1-sentence overall
   confidence summary. Total output must not exceed 1500 characters. Do NOT
   use markdown tables — use a short heading per dimension followed by prose.

   Branch: { ... }
   Real numeric fields from company data: [...]
   Flagged assumptions: [...]
   Modeling outputs (deterministic): { ... }
   Retrieval dialogue summary: [...]  (truncated to 3000 chars)
   ```

   **Output:** free-text prose with one heading per Slalom dimension (no tables).
   Pasted directly into the memo. If output exceeds 3000 characters despite the
   prompt constraint, `report.py` truncates at the last complete sentence
   boundary and appends a brevity note.

   **Deviation from plan:** project-plan.md described streaming into a live
   agent-trace UI. The current implementation streams but only collects the
   `content` chunks into a string; no UI exists yet.

   The fallback path adds a system-role message (`"Output ONLY the
   explainability section for the CFO memo. No planning notes or instruction
   restatement."`) and applies heuristic preamble-stripping when the Vultr model
   leaks chain-of-thought into `content`.

   ---

   ### 2e. Report Agent

   | Property | Value |
   |----------|-------|
   | **Model (recommendation)** | `MiniMaxAI/MiniMax-M2.7` (primary), `MiniMaxAI/MiniMax-M2.7` (fallback: same model retried, then `moonshotai/Kimi-K2.6`) |
   | **Provider** | Vultr Serverless Inference |
   | **Token budget** | `max_tokens: 2000` |
   | **Temperature** | 0.3 |

   **Deviation from plan:** project-plan.md listed `Nemotron-3-Nano-Omni` or
   `MiniMax-M2.7` as options. Nemotron-3-Nano-Omni was tested but its reasoning
   overhead consumed the entire token budget, leaving the memo body empty or
   truncated. MiniMax-M2.7 is used instead.

   **Actual implementation:** the Report Agent is a **hybrid Python template +
   LLM-generated recommendation**. The numbers tables, cost breakdowns, flagged
   assumptions, and citations are assembled entirely in Python from the Modeling
   Tool outputs (`_scenario_block()`). The recommendation paragraph is generated
   by an LLM call using the `emit_recommendation` tool (`tool_choice="required"`).

   The `emit_recommendation` tool returns structured output:
   ```json
   {
   "winner": "A" | "B",
   "reasoning": "2-4 sentence CFO-readable recommendation...",
   "confidence_caveat": "1 sentence caveat..."
   }
   ```

   The LLM receives both branches' full modeling outputs (all 3 scenarios per
   branch) and flagged assumptions. It reasons about tradeoffs — not just
   "higher ROI wins" but whether the higher-ROI branch carries proportionally
   more risk from flagged assumptions.

   **Confidence integrity (overall-only, verified):** for confidence, the
   recommendation call receives **only each branch's overall confidence score**,
   parsed from the explainability text (`_parse_overall_confidence()` reads the
   final "Overall confidence: N" summary). Per-dimension scores are deliberately
   withheld, because previously the payload passed a 500-char explainability
   excerpt that contained only the per-dimension scores — the model would then
   cite a dimension figure (e.g. Cost-impact 70% vs 55%) as if it were the
   overall confidence, mismatching the true overall values. The prompt instructs
   the model to cite only the provided overall values and label them "overall
   confidence." After generation, `_confidence_citations_valid()` extracts any
   confidence percentage cited in the reasoning and verifies it matches a real
   overall score (±1); a mismatch triggers a regenerate (a strict correction on
   retry, then the fallback model). If a branch's overall confidence has no
   parseable number, no confidence figure is treated as valid to cite and the
   model is steered to speak qualitatively for that branch.

   **Fallback:** if the primary model (`MiniMaxAI/MiniMax-M2.7`) fails to produce
   a valid `emit_recommendation` tool call, the code retries with
   `moonshotai/Kimi-K2.6` as fallback. If both fail, a hard-fallback string
   noting the LLM recommendation was unavailable is used.

   **Input to `assemble_memo()`:** company dict, plan dict, branch_plan dict,
   and a list of branch_results (each containing `branch`, `retrieval`,
   `modeling`, `explanation`).

   **Output:** a single plain-text markdown memo string with Scenario A vs
   Scenario B side by side.

   ---

   ## 3. Retrieval Layer — Real Architecture

   ### What the plan said

   Project-plan.md §3a describes "two agents run as a dialogue, not a silent
   handoff" — Internal Retrieval Agent and Benchmark Retrieval Agent exchanging
   pushbacks.

   ### What is actually built

   VultronRetriever models **do not support** `/v1/chat/completions`. They only
   expose a `/v1/rerank` endpoint (confirmed: chat returns 404, rerank returns
   200). The "dialogue" is implemented as **three rerank calls for evidence
   retrieval** followed by an **LLM call for claim validation**.

   #### Step-by-step mechanism (per branch)

   **Step 1 — Internal Retrieval (Round 0):**
   `rerank()` is called with `model=vultr/VultronRetrieverCore-Qwen3.5-4.5B`,
   query = extraction prompt, documents = 15 strings constructed from the
   company profile (one sentence per field). `top_n=8`. The rerank scores rank
   which company fields are most relevant to the extraction query. The actual
   numeric claim extraction is done by `_extract_claims()` in Python — it reads
   directly from the company profile JSON, not from the rerank output. The
   rerank output provides **grounding evidence** (which documents were most
   relevant) for the transcript.

   **Step 2 — Benchmark Retrieval (Round 1):**
   `rerank()` is called with the same model, query = a natural-language claim
   summary (category-aware — e.g. "Company claims 50% deflection..." for CS,
   "Company claims 45% conversion lift..." for Marketing AI, "Company claims 35%
   maintenance reduction..." for Maintenance AI), documents = the benchmark
   facts formatted as `"[id] claim text (source: ...)"`. `top_n=6`.

   **Step 3 — Justification Retrieval:**
   `rerank()` is called a third time against the company docs with a
   category-aware justification query (e.g. "Does the company documentation
   justify an optimistic deflection rate / conversion lift / maintenance spend
   reduction?"). `top_n=4`.

   **Step 4 — LLM Claim Validation (`_llm_validate_claims`):**
   An LLM call (`moonshotai/Kimi-K2.6`, fallback `MiniMaxAI/MiniMax-M2.7`) with
   `tool_choice="required"` judges each company claim against the retrieved
   evidence. The model receives:
   - Top benchmark facts from Step 2 (with their cited ranges/figures)
   - Company justification documents from Step 3 (to look for pilot data,
   measured results, or validated evidence)
   - The specific claims to validate (category-aware: deflection rate for CS,
   conversion lift for Marketing AI, spend reduction for Maintenance AI, plus
   inference budget for all categories) with reference context

   The model calls the `validate_claims` tool, returning structured output:
   ```json
   {
   "verdicts": [
      {
         "claim": "Deflection: 50% overall (implied tier1=83.3%)",
         "verdict": "flagged",
         "reasoning": "The company's implied Tier-1 deflection rate of 83.3% significantly exceeds the benchmark of ~68%...",
         "cited_fact_id": "cs_tier1_deflection"
      },
      {
         "claim": "Inference budget: $48K vs build $380K",
         "verdict": "flagged",
         "reasoning": "HTEC benchmark indicates true operating cost is typically 3-5x the build estimate...",
         "cited_fact_id": "htec_true_op_cost"
      }
   ]
   }
   ```

   The LLM reasons about whether each claim is **defensible** or should be
   **flagged**, weighing both the benchmark fit AND any justification evidence
   from company docs. If the company provides pilot data or measured results
   justifying an outlier claim, the LLM may rule it defensible. If not, it flags
   the claim with specific reasoning and a benchmark citation.

   **Category-correct reference context (no cross-category fact leakage):**
   The reference notes appended to each claim (built by
   `_build_claim_descriptions()`) only cite benchmark fact IDs that actually
   exist in *that category's* corpus. This matters most for the universal
   "operating budget vs build cost" claim: Customer Support AI cites
   `htec_true_op_cost` (op cost 3–5× build), Predictive Maintenance AI cites
   `mid_market_implementation_tco` (recurring op cost 15–25% of build), and
   Marketing AI — which has **no** operating-cost benchmark — instructs the
   model to reason generally and cite `'none'`. Previously `htec_true_op_cost`
   was injected for every category, so on non-CS corpora one branch would admit
   the fact was missing while the other hallucinated dollar figures — a
   scenario-to-scenario contradiction. Any fact referenced in a claim note that
   the reranker did not already surface is injected into the BENCHMARKS block so
   the model can genuinely see and cite it.

   **Hard citation guard (`_guard_citations`):** after the tool call, every
   `cited_fact_id` the model returns is checked against the set of fact IDs
   actually shown to it (retrieved + injected benchmark docs + claim-note
   references). Any citation the model invented that was **not** in that set is
   rejected: it is reset to `'none'`, recorded under `rejected_fact_id`, and
   scrubbed from the reasoning text so it can never surface in the memo. This
   guarantees the model can only cite evidence it was actually given.

   **Honest per-branch citations:** the memo's Citations list is built from the
   fact IDs *genuinely cited* in that branch's verdicts (resolved back to their
   full corpus entries), not a fixed top-N of retrieved docs. As a result every
   `(ref: fact_id)` marker in a branch's flagged assumptions has a matching
   entry in that branch's Citations list, and vice versa.

   **Token budget:** `max_tokens: 2500` (dedicated `CLAIM_VALIDATION` budget in
   `token_budgets.py`). This is higher than the Planner's 1000-token budget
   because the prompt includes benchmark context and the model needs room for
   reasoning before emitting the tool call. Kimi-K2.6 often hits the token
   ceiling due to reasoning overhead; MiniMax-M2.7 serves as a reliable
   fallback for this task.

   **Post-processing:** verdicts with `"verdict": "flagged"` are converted to
   `"assumption, not validated: ..."` strings and passed downstream. The hosting
   architecture branch is always appended as an additional flagged assumption.

   **Hard cap:** no further rounds after this single validation pass.

   **Output schema:**
   ```json
   {
   "branch_id": "A_on_prem",
   "hosting_architecture": "on_prem",
   "reconciled_inputs": { ... numeric claims ... },
   "flagged_assumptions": ["assumption, not validated: ...", ...],
   "transcript": [ ... round-by-round records with verdicts ... ],
   "citations": ["[cs_tier1_deflection] ...", ...]
   }
   ```

   ---

   ## 4. Modeling Tool — Full Math

   ### 4a. Customer Support AI — Value & Cost Math

   File: `backend/modeling/roi.py`

   ### Core formula (HTEC)

   ```
   ROI = (Total Business Value − Total Cost) / Total Cost
   ```

   where:

   ```
   Total Business Value (3yr) = annual_value × 3
   Total Cost (3yr)           = year1_cost + year2_cost + year3_cost
   ```

   ### Value calculation

   ```
   effective_deflection = claimed_tier1_deflection_rate × scenario_multiplier
   effective_deflection = clamp(effective_deflection, 0.0, 0.95)

   tier1_tickets        = annual_ticket_volume × tier1_ticket_share
   tickets_deflected    = tier1_tickets × effective_deflection
   annual_value         = tickets_deflected × cost_per_ticket_usd
   ```

   **Scenario multipliers** (`_DEFLECTION_MULT`):

   | Scenario | Multiplier applied to claimed Tier-1 deflection |
   |----------|------------------------------------------------|
   | Conservative | 0.70 |
   | Likely | 1.00 |
   | Optimistic | 1.15 |

   ### Cost calculation — hosting-dependent base profile

   `_hosting_cost_profile(hosting, build, inference)` returns Year 1 costs:

   | Component | On-prem formula | Cloud formula |
   |-----------|----------------|---------------|
   | Build (one-time) | `build` | `build` |
   | Inference Y1 | `inference × 0.55` | `inference × 1.35` |
   | Integration Y1 | `build × 0.45` | `build × 0.22` |
   | Model-update Y1 | `build × 0.12` | `build × 0.15` |

   ```
   year1_cost = build + inference_y1 + integration_y1 + model_update_y1
   ```

   ### Year 2+ non-linear scaling (HTEC)

   Integration and model-update costs scale non-linearly. Inference grows by a
   fixed percentage:

   ```
   inference_y2     = inference_y1 × 1.08  (cloud)
                  = inference_y1 × 1.03  (on-prem)
   integration_y2   = integration_y1 × 1.35     (_Y2_INTEGRATION_SCALE)
   model_update_y2  = model_update_y1 × 1.50    (_Y2_MODEL_UPDATE_SCALE)

   year2_cost = inference_y2 + integration_y2 + model_update_y2
   year3_cost = year2_cost × 1.05              (mild growth, no rebuild)
   ```

   ### Payback calculation

   ```
   monthly_value   = annual_value / 12
   monthly_ongoing = (inference_y1 + integration_y1 + model_update_y1) / 12
   monthly_net     = monthly_value − monthly_ongoing

   if monthly_net > 0:
      payback_months = build / monthly_net
   else:
      payback_months = null  (project never pays back)
   ```

   ### How scenario branching changes inputs

   The `hosting_architecture` field (`"on_prem"` or `"cloud"`) selects which
   column of the hosting-cost-profile table is used. All other inputs (ticket
   volume, cost per ticket, deflection rate, build cost, inference budget) are
   identical between branches — the branches differ only in how costs are
   distributed.

   ---

   ### 4b. Marketing AI — Value & Cost Math

   File: `backend/modeling/roi_marketing.py`

   **Core formula** is unchanged (HTEC): `ROI = (TBV − TC) / TC`.

   #### Value calculation

   ```
   effective_conversion_lift = claimed_conversion_lift_rate × scenario_multiplier
   effective_conversion_lift = clamp(effective_conversion_lift, 0.0, 0.32)
                              ↑ 32% cap from integrated_workflow_performance benchmark

   baseline_conversion_rate = current_conversion_rate (e.g. 0.021)
   new_rate         = baseline_rate × (1 + effective_lift)
   additional_rate  = new_rate − baseline_rate

   monthly_traffic  = monthly_ad_spend_usd / _ASSUMED_CPC_USD ($2.50)
                      ↑ MODELING ASSUMPTION — not company-provided

   additional_conversions_monthly = additional_rate × monthly_traffic
   annual_value     = additional_conversions_monthly × 12 × average_order_value_usd
   ```

   **Scenario multipliers** (same as CS): conservative=0.70, likely=1.00, optimistic=1.15.

   #### Branch-dependent cost profile: `_data_strategy_cost_profile`

   Branch field: `data_enrichment_strategy` ("first_party_only" vs "third_party_enrichment")

   | Component | First-party formula | Third-party formula |
   |-----------|--------------------|--------------------|
   | Build (one-time) | `build` | `build` |
   | Inference Y1 | `inference × 0.70` | `inference × 1.60` |
   | Integration Y1 | `build × 0.20` | `build × 0.45` |
   | Model-update Y1 | `build × 0.10` | `build × 0.18` |

   **MODELING ASSUMPTIONS** (all percentage splits above are author estimates):
   - First-party-only has lower costs because no third-party data vendor licensing
     or API connector fees. Integration is simpler (internal data only).
   - Third-party enrichment requires data broker licensing, privacy compliance,
     and external API mapping — driving higher inference and integration costs.

   #### Y2+ non-linear scaling

   ```
   inference_y2    = inference_y1 × 1.12  (third_party — vendor price increases)
                   = inference_y1 × 1.05  (first_party)
   integration_y2  = integration_y1 × 1.35  (_Y2_INTEGRATION_SCALE)
   model_update_y2 = model_update_y1 × 1.50 (_Y2_MODEL_UPDATE_SCALE)
   year3_cost      = year2_cost × 1.05
   ```

   #### Payback

   Same formula as CS: `payback_months = build / monthly_net` where
   `monthly_net = (annual_value/12) − (ongoing_y1/12)`.

   ---

   ### 4c. Predictive Maintenance AI — Value & Cost Math

   File: `backend/modeling/roi_maintenance.py`

   **Core formula** is unchanged (HTEC): `ROI = (TBV − TC) / TC`.

   #### Value calculation (two additive components)

   ```
   effective_spend_reduction = claimed_maintenance_spend_reduction_rate × scenario_multiplier
   effective_spend_reduction = clamp(effective_spend_reduction, 0.0, 0.18)
                               ↑ 18% cap from mid_market_realistic_target_range benchmark

   maintenance_savings = current_annual_maintenance_spend_usd × effective_spend_reduction

   downtime_reduction = scenario-dependent fixed rates:
     conservative = 0.30, likely = 0.35, optimistic = 0.40
     ↑ From mid_market_realistic_target_range (30-40% on critical assets)
     ↑ This is a SEPARATE metric from maintenance spend reduction

   avoided_downtime_value = annual_downtime_cost_usd × downtime_reduction

   annual_value = maintenance_savings + avoided_downtime_value
   ```

   **Scenario multipliers** (same as CS): conservative=0.70, likely=1.00, optimistic=1.15.

   #### Branch-dependent cost profile: `_hardware_deployment_cost_profile`

   Branch field: `hardware_deployment_method` ("retrofit" vs "new_install")

   | Component | Retrofit formula | New-install formula |
   |-----------|-----------------|-------------------|
   | Build (one-time) | `build` | `build` |
   | Inference Y1 | `inference × 0.80` | `inference × 1.30` |
   | Integration Y1 | `build × 0.30` | `build × 0.55` |
   | Model-update Y1 | `build × 0.22` | `build × 0.10` |

   **MODELING ASSUMPTIONS** (all percentage splits above are author estimates):
   - Retrofit is cheaper upfront (bolt-on adapters, reuse existing telemetry
     boards) but has higher ongoing calibration cost due to sensor drift on
     legacy hardware — hence higher model_update percentage.
   - New install is more expensive upfront (full sensor suite + smart nodes)
     but produces higher-quality data with less drift — hence lower model_update
     but higher integration cost.

   #### Y2+ non-linear scaling

   ```
   inference_y2    = inference_y1 × 1.04  (new_install — stable hardware)
                   = inference_y1 × 1.10  (retrofit — sensor drift compensation)
   integration_y2  = integration_y1 × 1.35  (_Y2_INTEGRATION_SCALE)
   model_update_y2 = model_update_y1 × 1.50 (_Y2_MODEL_UPDATE_SCALE)
   year3_cost      = year2_cost × 1.05
   ```

   #### Payback

   Same formula as CS.

   ---

   ### 4d. Category Dispatch

   File: `backend/pipeline/run_category.py`

   The pipeline selects the correct modeling function based on `project_category`:
   - `"Customer Support AI"` → `modeling_tool_from_args()` in `roi.py`
   - `"Marketing AI"` → `marketing_modeling_from_args()` in `roi_marketing.py`
   - `"Predictive Maintenance AI"` → `maintenance_modeling_from_args()` in `roi_maintenance.py`

   The original `run_slice.py` remains intact for CS regression testing. The new
   `run_category.py` handles all three categories with deterministic branch
   construction (no Planner LLM needed for branching in the new categories).

   ---

   ### 4e. Modeling Assumptions — Transparency Flag

   The following assumptions were made by the system author, NOT derived from
   researched benchmarks. They are modeling design decisions and should be labeled
   as such for transparency:

   | Assumption | Value | Used in | Rationale |
   |------------|-------|---------|-----------|
   | Assumed CPC (cost-per-click) | $2.50 | Marketing AI — implied traffic calculation | Industry average for DTC health/supplements in paid social+search. Company does not provide traffic volume. |
   | First-party inference scale | 0.70× | Marketing AI — `_data_strategy_cost_profile` | Lower data processing volume when only internal data is used. |
   | Third-party inference scale | 1.60× | Marketing AI — `_data_strategy_cost_profile` | Vendor data licensing fees + higher processing volume. |
   | First-party integration % | 20% of build | Marketing AI — `_data_strategy_cost_profile` | Simpler pipeline, no external API connectors. |
   | Third-party integration % | 45% of build | Marketing AI — `_data_strategy_cost_profile` | Data broker APIs, privacy compliance, mapping. |
   | Retrofit inference scale | 0.80× | Maintenance AI — `_hardware_deployment_cost_profile` | Fewer sensors, less data volume with bolt-on hardware. |
   | New-install inference scale | 1.30× | Maintenance AI — `_hardware_deployment_cost_profile` | Full sensor suite generates higher data volume. |
   | Retrofit integration % | 30% of build | Maintenance AI — `_hardware_deployment_cost_profile` | Adapter work, custom wiring on legacy equipment. |
   | New-install integration % | 55% of build | Maintenance AI — `_hardware_deployment_cost_profile` | Full hardware + software setup from scratch. |
   | Retrofit model-update % | 22% of build | Maintenance AI — `_hardware_deployment_cost_profile` | Frequent recalibration needed for sensor drift. |
   | New-install model-update % | 10% of build | Maintenance AI — `_hardware_deployment_cost_profile` | Stable sensors, less calibration required. |
   | Downtime reduction rates | 30/35/40% | Maintenance AI — per-scenario | Based on benchmark range (30-40%), assigned to scenario ladder. |

   ---

   ### 4f. Output-Level Sanity Check

   File: `backend/modeling/sanity_check.py`

   **Purpose:** after computing ROI and payback for each scenario, this module
   compares outputs against benchmark-sourced realistic ceilings. Violations
   produce NEW flagged assumptions (prefixed `"output sanity check:"`) that are
   **distinct from input-claim flags** from the retrieval layer.

   These flags indicate that the overall projection exceeds defensible boundaries
   even after input clamping — signaling that the cost estimate itself may be
   unrealistic relative to the company's operational scale.

   #### Thresholds

   | Category | ROI ceiling | Source | Type |
   |----------|-------------|--------|------|
   | Customer Support AI | 5.8x | `mckinsey_roi_multiple`: "~5.8x within ~14 months" | **Corpus-cited** (industry average) |
   | Marketing AI | 3.2x | `use_case_roi_content_drafting`: "~3.2x ROI" (highest of 4 use cases) | **Corpus-cited** (upper bound of measured range) |
   | Predictive Maintenance AI | 5.0x | No published ROI-multiple benchmark exists | **Modeling assumption** |
   | All categories (payback) | 6 months min | `sector_payback_manufacturing` (12-14mo), `adopter_payback_distribution` (75% >1yr) | **Corpus-cited** (cross-source floor) |

   **Predictive Maintenance AI ceiling rationale (modeling assumption, not
   benchmark-derived):** No published PMAI ROI-multiple benchmark exists in the
   corpus. The 5.0x ceiling is derived from conservative reasoning:
   `adopter_payback_distribution` shows 75% of organizations take >1 year for
   full return; `mid_market_savings_reality` limits the value numerator to
   11-18% spend reduction. A 5.0x 3-year ROI implies ~2.7x annual
   value-to-cost ratio, which is aggressive given these constraints.

   #### Flag message format

   ```
   output sanity check: Computed 3-year ROI (X.Xx) exceeds the benchmark-realistic
   ceiling (Y.Yx) even after input-claim clamping. This suggests the implementation
   cost estimate may be understated relative to the company's operational scale —
   recommend validating the cost estimate before relying on this projection.
   ```

   #### Integration

   The sanity check runs inside `run_modeling_tool()`, `run_marketing_modeling_tool()`,
   and `run_maintenance_modeling_tool()` — appending output flags to the existing
   `flagged_assumptions` list. These flow into the memo's "Flagged assumptions"
   section and are visible to the Explainability and Report agents.

   ---

   ## 5. Benchmark Corpus — What's Real, What's Mock

   ### 5a. Customer Support AI (`data/benchmarks/customer_support_ai.json`)

   All 9 facts are **paraphrased from real published sources** listed in
   project-plan.md §5A. None are placeholder/mock numbers. The specific numeric
   values cited are taken from the sources listed; they are not independently
   verified primary research.

   | ID | Claim (paraphrased) | Value | Source | Status |
   |----|---------------------|-------|--------|--------|
   | `mckinsey_roi_multiple` | Avg ROI ~5.8x within ~14 months of production | 5.8x | McKinsey Global AI Survey | Real published figure |
   | `nvidia_sector_adoption` | AI adoption/ROI varies by sector; retail is active | (qualitative) | NVIDIA State of AI Report 2026 | Real published context |
   | `deloitte_productivity_gains` | ~66% of enterprises report productivity gains | 66% | Deloitte State of AI in the Enterprise | Real published figure |
   | `deloitte_revenue_aspiration_gap` | 74% hope for revenue impact, only ~20% achieve it | 74%/20% | Deloitte State of AI in the Enterprise | Real published figure |
   | `sector_payback_finance` | Finance AI payback ~8 months | 8 months | Sector payback timelines (published surveys) | Real published figure |
   | `sector_payback_manufacturing` | Manufacturing AI payback ~12–14 months | 12–14 months | Sector payback timelines (published surveys) | Real published figure |
   | `cs_tier1_deflection` | CS chatbots resolve ~68% of Tier-1 tickets | 68% | Customer service chatbot resolution benchmarks | Real published figure |
   | `htec_true_op_cost` | True op cost is often 3–5x initial build | 3–5x | HTEC AI cost / ROI framework | Real published framework |
   | `htec_roi_formula` | ROI = (TBV − TC) / TC; costs scale non-linearly Y2+ | formula | HTEC AI cost / ROI framework | Real published framework |

   The `range_typical` field on `cs_tier1_deflection` (overall deflection sanity
   band of 20–35%) is provided to the LLM claim validator as reference context
   — the LLM uses it as a benchmark range for reasoning, not as a hardcoded
   threshold.

   ### 5b. Marketing AI (`data/benchmarks/marketing_ai.json`)

   10 facts paraphrased from published sources (McKinsey, industry analysis).
   Key facts used by the Modeling Tool's clamping logic:

   | ID | Used for | Value | Source |
   |----|----------|-------|--------|
   | `realistic_marketing_roi_range` | Clamping conversion lift ceiling | 20-25% campaign lift | Cross-Source Analyst Consensus |
   | `integrated_workflow_performance` | Absolute lift ceiling | 32% for deep integrations | Industry analysis |
   | `use_case_roi_content_drafting` | Output sanity-check ROI ceiling + validation context | ~3.2x ROI | McKinsey |
   | `use_case_roi_personalization` | Reference context | ~2.7x ROI | McKinsey |
   | `use_case_roi_audience_targeting` | Reference context | ~2.4x ROI | McKinsey |
   | `use_case_roi_ad_copy_optimization` | Reference context | ~2.3x ROI | McKinsey |

   ### 5c. Predictive Maintenance AI (`data/benchmarks/predictive_maintenance_ai.json`)

   10 facts paraphrased from published sources (McKinsey, Persistence Market
   Research, IoT Analytics). Key facts used by the Modeling Tool:

   | ID | Used for | Value | Source |
   |----|----------|-------|--------|
   | `mid_market_realistic_target_range` | Clamping spend reduction + downtime reduction | 11-18% spend / 30-40% downtime | Cross-Source Industrial Consensus |
   | `mid_market_savings_reality` | Claim validation reference | 11-18% realistic | Persistence Market Research |
   | `enterprise_downtime_cost_reduction` | Validation context | 30-50% on enterprise assets | McKinsey / Persistence Market Research |

   ### 5d. Synthetic company profiles

   | File | Category | Key claim | Trigger |
   |------|----------|-----------|---------|
   | `data/companies/meridian_support.json` | Customer Support AI | 50% deflection (vs 20-35% benchmark) | `hosting_architecture: "unknown"` |
   | `data/companies/novavita_marketing.json` | Marketing AI | 45% conversion lift (vs 20-25% benchmark) | `data_enrichment_strategy: "unknown"` |
   | `data/companies/apex_maintenance.json` | Predictive Maintenance AI | 35% spend reduction (vs 11-18% benchmark) | `hardware_deployment_method: "unknown"` |

   All company profiles are **fully fabricated** synthetic data for demo purposes.

   ---

   ## 6. Scenario Branching Logic

   ### Trigger condition

   In `plan_and_clarify()`, if the company profile contains any field in
   `unknown_fields` whose value matches `"unknown"`, `"i don't know"`, or
   `"not decided"` (case-insensitive), that field is added to `missing_fields`.
   The Planner generates a `clarifying_question` for the top missing field.

   In the current vertical slice, the user answer is hardcoded to `"unknown"`
   in `run_slice.py` (line 70). This triggers `branch_on_unknown()`.

   ### Branch generation

   **Customer Support AI (via `run_slice.py`):** The Planner is asked to call
   `emit_branches` (tool call). Python normalizes the output to exactly 2
   branches with hardcoded IDs:
   - `A_on_prem` → `"hosting_architecture": "on_prem"`
   - `B_cloud` → `"hosting_architecture": "cloud"`

   **Marketing AI and Predictive Maintenance AI (via `run_category.py`):**
   Branches are constructed deterministically from the category config without
   a Planner LLM call:
   - Marketing AI: `A_first_party_only` / `B_third_party_enrichment` (field: `data_enrichment_strategy`)
   - Maintenance AI: `A_retrofit` / `B_new_install` (field: `hardware_deployment_method`)

   **Hard cap:** `branches["branches"][:2]` — the list is truncated to 2
   entries even if the model returns more.

   ### Per-branch independent execution

   For each branch, stages 2–4 run independently:
   1. `run_retrieval_dialogue()` — receives `hosting_architecture` as a parameter
   2. `call_modeling_tool_via_planner()` — receives the branch dict (with `hosting_architecture`)
   3. `explain_branch()` — receives the branch, retrieval output, and modeling output

   ### Merge into one memo

   `assemble_memo()` receives the full list of `branch_results` and iterates
   over `branch_results[:2]`, generating one scenario section per branch.
   The recommendation paragraph is generated by an LLM call
   (`emit_recommendation` tool) that receives both branches' full modeling
   outputs, flagged assumptions, and explainability excerpts, and reasons about
   the tradeoffs.

   ### Bounded output

   2 architecture branches × 3 financial scenarios = 6 numbers max per metric.
   This is the "bounded output" constraint from project-plan.md §3a to avoid
   the "wall of numbers" risk.

   ---

   ## 7. Known Limitations / Open Issues

   1. **NVIDIA rate limits:** the free-tier `nvidia/nemotron-3-ultra-550b-a55b`
      endpoint enforces a low concurrent-request cap (~32). The pipeline runs
      two Explainability calls sequentially (one per branch), but even this can
      hit the limit if other users are on the shared endpoint. The fallback to
      GLM-5.2-FP8 works but produces lower-quality output that sometimes leaks
      chain-of-thought reasoning into the memo body.

   2. **Kimi-K2.6 reasoning overhead:** both Kimi and MiniMax models consume
      tokens in an invisible `reasoning` field before populating `content`.
      All structured outputs must use `tool_choice="required"` to land in
      function-call arguments reliably. The `message_text()` helper in
      `json_util.py` falls back to reading `reasoning` if `content` is empty,
      but this path produces unstable output for structured data. For claim
      validation specifically, Kimi-K2.6 often exhausts its 2500-token budget
      on reasoning before completing the tool call; MiniMax-M2.7 serves as a
      reliable fallback for this task.

   3. **Multi-category pipeline:** `run_category.py` supports all three
      categories (Customer Support AI, Marketing AI, Predictive Maintenance AI)
      with deterministic branch construction and category-specific claim
      extraction. The original `run_slice.py` is preserved for CS regression.

   4. **`kimi-k2-instruct` alias drift:** the original project-plan.md
      specifies `kimi-k2-instruct` as the Planner model. This alias does not
      exist in the live Vultr catalog and silently routes to MiniMax-M2.7.
      Code uses the real catalog ID `moonshotai/Kimi-K2.6` and a hard-fail
      check was added in the smoke test to catch future alias drift.

   5. **VultronRetriever token budgets unused:** `INTERNAL_RETRIEVAL` and
      `BENCHMARK_RETRIEVAL` token budgets (800 each) are defined in
      `token_budgets.py` but never passed to the rerank endpoint (rerank
      does not accept `max_tokens`). They exist only for documentation /
      future use if the models gain chat support.

   6. **Claim validation model preference:** the `_llm_validate_claims` function
      in `retrieval.py` tries Kimi-K2.6 first but in practice falls back to
      MiniMax-M2.7 because Kimi's reasoning overhead exhausts the 2500-token
      budget before completing the `validate_claims` tool call. Both models
      produce equivalent verdict quality, but Kimi is less token-efficient for
      this specific task.

   7. **Retrieval is not a full LLM-to-LLM dialogue:** the "Internal ⇄
      Benchmark" exchange described in project-plan.md is implemented as rerank
      calls for evidence retrieval + a single LLM validation call, not as two
      LLMs debating back and forth. The intent (grounded pushback with
      reasoned judgment) is preserved, but the mechanism differs.

   8. **Explainability length safeguard:** the Explainability Agent prompt now
      constrains output to 2-3 sentences per Slalom dimension (no tables) and
      a 1500-character target. If the model still produces output exceeding
      3000 characters, `report.py` truncates at the last complete sentence
      boundary and appends "[additional detail omitted for brevity]" rather
      than cutting mid-sentence. With the current NVIDIA Nemotron model this
      safeguard has not triggered — both branches produce ~1800-1950 characters
      naturally — but it exists as a safety net for longer fallback model output.

   ---

   ## 8. What's Not Built Yet

   | Component | Status |
   |-----------|--------|
   | **Frontend** (Next.js — input flow, live agent trace, memo output) | Not started (only a `.gitkeep` placeholder exists in `/frontend`) |
   | **FastAPI backend** | Not started (no `main.py`, no routes — pipeline runs as a CLI script) |
   | **Additional synthetic company profiles** (plan calls for 2–3 per category) | Only 1 per category exists |
   | **Dynamic user input** (clarifying question → real user answer) | User answer is hardcoded to `"unknown"` |
   | **Live agent-trace streaming to frontend** | Not started |
   | **Vultr vector store / RAG chat** | Not used — retrieval is rerank-only |
   | **Planner LLM for new categories** | New categories use deterministic branch construction in `run_category.py` (no Planner LLM call for branching); CS still uses Planner via `run_slice.py` |
