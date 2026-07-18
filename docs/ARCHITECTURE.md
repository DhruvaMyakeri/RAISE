# Vantage — System Architecture (as implemented)

> **Last updated:** 2026-07-14 (post-remediation)
> This document describes the system as it actually runs. The deterministic
> modeling math is additionally locked by unit tests with independently
> hand-derived expected values — `backend/tests/test_roi_*.py` is the
> executable spec; if this document and those tests ever disagree, the tests win.

---

## 1. Pipeline Overview

There is exactly **one** implementation of the pipeline stage loop:
`backend/pipeline/core.py :: run()`. Every consumer drives it with a
different `EventEmitter` (`backend/pipeline/events.py`):

| Consumer | Entry point | Emitter |
|----------|------------|---------|
| Web API (SSE stream) | `main.py :: get_run_stream` | `CallbackEmitter` → SSE queue |
| Web API (sync JSON) | `main.py :: post_run` | `NullEmitter` |
| CLI | `pipeline/run_category.py` | `PrintingEmitter` (sequential branches for readable logs) |
| Tests | `backend/tests/test_memo_golden.py` | `CallbackEmitter` → list capture |

```
Company profile + benchmark corpus (per category)
      │
      ▼
Stage 1 — Deterministic branch construction (no LLM)
   2 scenario branches from category config (e.g. A_on_prem / B_cloud)
      │
      ├──────────────── Branch A ─────────────┬──────────── Branch B ──────
      ▼   (branches run in parallel via ThreadPoolExecutor for the API)   ▼
Stage 2 — Retrieval + claim validation (per branch)
   pipeline/claims.py extracts numeric claims (single source of truth)
   3× Vultr rerank (evidence) + 1 LLM validate_claims tool call
   Hard citation guard rejects any fact ID not actually shown to the model
      ▼
Stage 3 — Deterministic modeling (pure Python, no LLM)
   3 financial scenarios; input clamps; output-level sanity check
      ▼
Stage 4 — Explainability (streamed)
   NVIDIA nemotron (fallback Vultr GLM); prose + ===DATA=== JSON tail
   carrying per-dimension/overall confidence (tail never streamed to UI)
      │
      └───────────────────────┬────────────────────────────────────────────
                              ▼
Stage 5 — Recommendation (LLM, emit_recommendation tool call)
   Confidence citations verified against real overall scores; regenerate on mismatch
      ▼
Memo JSON (api/memo_json.py) → SSE memo_ready event / HTTP response
   CLI additionally renders the text memo via agents/report.py :: assemble_memo
```

**Hard rule (unchanged):** LLMs never compute the final ROI number. All
arithmetic runs in plain, auditable, unit-tested Python.

**Design decision — Planner LLM retired (2026-07):** an earlier iteration used
a Kimi "Planner/Orchestrator" LLM to classify the project, ask a clarifying
question, and emit scenario branches (`agents/planner.py`, `run_slice.py`).
It was removed during remediation because (a) the web API never invoked it,
(b) it force-overrode every classification to Customer Support AI and
hardcoded demo strings, and (c) Python normalized its branch output back to
the deterministic defaults regardless of what the model returned — the LLM
call added latency and failure modes without adding decisions. Branch
construction is now deterministic from category config for all categories.
The model constants were renamed `CLAIM_VALIDATION_MODEL*` to reflect what
the LLM actually does.

---

## 2. Components

### 2a. Claim extraction — `pipeline/claims.py`

`extract_claims(company, branch_value, category_key)` is the **single**
extractor of numeric claims from a company profile. Both the retrieval stage
(what the LLM validates) and the modeling stage (what the tool computes with)
consume its output, so they cannot drift. Customer Support additionally
derives `claimed_tier1_deflection_rate = min(claimed_overall / tier1_share, 0.95)`.

### 2b. Retrieval + claim validation — `agents/retrieval.py`

| Property | Value |
|----------|-------|
| Rerank model | `vultr/VultronRetrieverCore-Qwen3.5-4.5B` (`POST /v1/rerank` only — chat returns 404) |
| Claim validation model | `moonshotai/Kimi-K2.6`, fallback `MiniMaxAI/MiniMax-M2.7` |
| Claim validation budget | `max_tokens: 2500` (`CLAIM_VALIDATION` in `config/token_budgets.py`) |

Per branch:
1. **Internal rerank** (`top_n=8`) over ~15 one-sentence documents built from
   the company profile — grounding evidence for the transcript (the numeric
   extraction itself is `pipeline/claims.py`, not the reranker).
2. **Benchmark rerank** (`top_n=6`) over the corpus facts formatted as
   `"[id] claim (source: ...)"`, queried with a category-aware claim summary.
3. **Justification rerank** (`top_n=4`) back over company docs ("does the
   company provide pilots/measured results justifying the outlier claim?").
4. **LLM validation** (`validate_claims` tool, `tool_choice="required"`): the
   model judges each claim defensible/flagged with reasoning and a
   `cited_fact_id`. Claim reference notes only cite fact IDs that exist in
   *that category's* corpus; any referenced fact the reranker didn't surface
   is injected into the BENCHMARKS block so the model can genuinely see it.

**Hard citation guard (`_guard_citations`)**: any `cited_fact_id` not in the
set of facts actually shown is reset to `'none'`, recorded under
`rejected_fact_id`, and scrubbed from the reasoning text. Hallucinated
citations are structurally impossible, not just discouraged.

**Honest citations:** the memo's per-branch Citations list contains exactly
the facts genuinely cited in that branch's verdicts.

Flagged verdicts become `"assumption, not validated: ..."` strings; the
branch choice itself is always appended as
`"assumption, not validated: <branch_field>=<value> (user unknown; branch <id>)"`.

Output schema per branch:
```json
{
  "branch_id": "A_on_prem",
  "branch_field": "hosting_architecture",
  "branch_value": "on_prem",
  "reconciled_inputs": { ...numeric claims... },
  "flagged_assumptions": ["assumption, not validated: ...", ...],
  "transcript": [ ...rounds with verdicts/grounding... ],
  "citations": ["[cs_tier1_deflection] ... (source: ...)", ...]
}
```

### 2c. Modeling Tool — `modeling/roi.py`, `roi_marketing.py`, `roi_maintenance.py`

Pure deterministic Python; no LLM. Core formula (HTEC):

```
ROI_3y = (TotalValue_3y − TotalCost_3y) / TotalCost_3y
TotalCost_3y = Y1 (build + inference + integration + model-update)
             + Y2 (inference·growth + integration·1.35 + model-update·1.5)
             + Y3 (Y2 · 1.05)
payback_months = build / (monthly value − monthly Y1 ongoing cost), None if ≤ 0
```

Per-category value model and clamps:

| Category | Annual value | Scenario multiplier applied to | Clamp |
|----------|-------------|-------------------------------|-------|
| Customer Support | tickets·tier1_share·deflection·cost_per_ticket | claimed tier-1 deflection ×{0.7, 1.0, 1.15} | deflection ≤ 0.95 |
| Marketing | Δconversion·(ad_spend / $2.50 CPC)·12·AOV — CPC is a labeled modeling assumption | claimed lift ×{0.7, 1.0, 1.15} | lift ≤ 0.32 (`integrated_workflow_performance`) |
| Maintenance | spend·reduction + downtime_cost·{0.30, 0.35, 0.40} | claimed reduction ×{0.7, 1.0, 1.15} | reduction ≤ 0.18 (`mid_market_realistic_target_range`) |

Branch-dependent Y1 cost shares (all labeled modeling assumptions in code):

| Category | Branch A | Branch B |
|----------|----------|----------|
| Customer Support | on_prem: inf×0.55, integ 45%, upd 12% of build; Y2 inf ×1.03 | cloud: inf×1.35, integ 22%, upd 15%; Y2 inf ×1.08 |
| Marketing | first_party: inf×0.70, integ 20%, upd 10%; Y2 inf ×1.05 | third_party: inf×1.60, integ 45%, upd 18%; Y2 inf ×1.12 |
| Maintenance | retrofit: inf×0.80, integ 30%, upd 22%; Y2 inf ×1.10 | new_install: inf×1.30, integ 55%, upd 10%; Y2 inf ×1.04 |

**Output-level sanity check** (`modeling/sanity_check.py`), applied to the
*likely* scenario after computation:

| Check | Threshold | Basis |
|-------|-----------|-------|
| CS ROI ceiling | 5.8x | corpus `mckinsey_roi_multiple` |
| Marketing ROI ceiling | 3.2x | corpus `use_case_roi_content_drafting` |
| Maintenance ROI ceiling | 5.0x | **modeling assumption** — no published PMAI ROI-multiple benchmark exists; documented in code |
| Payback floor (all) | 6 months | corpus payback-distribution facts |

Violations append `"output sanity check: ..."` flags indicating the cost
estimate may be understated. The generic result wrapper is
`ModelingOutput(branch_id, branch_value, inputs, scenarios, flagged_assumptions)`.

Exact expected values for the three demo companies are asserted in
`backend/tests/test_roi_customer_support.py`, `test_roi_marketing.py`,
`test_roi_maintenance.py` (hand-derived, not generated from the code).

### 2d. Explainability — `agents/explainability.py`

| Property | Value |
|----------|-------|
| Primary | `nvidia/nemotron-3-ultra-550b-a55b` (NVIDIA, streaming, temp 1.0, `max_tokens/reasoning_budget 16384`) |
| Fallback | `zai-org/GLM-5.2-FP8` (Vultr, non-streaming, `max_tokens 1200`, temp 0.3), after 2 primary attempts |

**Structured-output contract:** the model writes CFO-readable prose (heading +
2-3 sentences + `Confidence: NN%` per ROI dimension, then an overall
confidence sentence), followed by one machine-readable line:

```
===DATA=== {"overall_confidence": NN, "dimensions": [{"name": "...", "confidence": NN}, ...]}
```

`parse_explanation()` reads the JSON tail as the primary channel;
a legacy regex parse of the prose is the fallback for models that ignore the
format. `_MarkerGate` sits **above** the provider seam in `explain_branch` and
withholds everything from `===DATA===` onward from streamed UI chunks, even
when the marker splits across chunks. The fallback path re-chunks its
non-streamed output through the same gate for UI parity.

The prompt uses the category's own ROI dimensions (a former whitelist bug
silently dropped "Revenue impact" from Marketing prompts).

### 2e. Recommendation + memo — `agents/report.py`, `api/memo_json.py`

`generate_recommendation(branch_results)` is the **single** recommendation
implementation (the API and CLI both use it). Model `MiniMaxAI/MiniMax-M2.7`
(fallback Kimi), `emit_recommendation` tool call → `{winner, reasoning,
confidence_caveat, text}`.

**Confidence integrity:** the payload carries only each branch's *overall*
confidence (from the parsed explanation data tail — never per-dimension
scores). After generation, `_confidence_citations_valid()` checks every
confidence % cited in the text against the real overall scores (±1);
a mismatch triggers a corrected regenerate, then the fallback model, then a
hard fallback string built only from verified numbers.

`api/memo_json.py` assembles the JSON memo (metrics tables, parsed flags with
types `input_claim` / `output_sanity_check` / `branch_unknown`, parsed
citations, parsed explainability) and contains **no LLM calls**.
`agents/report.py :: assemble_memo` renders the CLI text memo from the same
branch results and recommendation.

---

## 3. API layer — `main.py`, `api/`

| Endpoint | Auth* | Rate limit | Purpose |
|----------|-------|-----------|---------|
| `GET /api/companies` | open | — | demo company list |
| `GET /api/companies/{id}/source` | open | — | raw profile (transparency) |
| `GET /api/benchmarks/{key}` | open | — | benchmark corpus (transparency) |
| `GET /api/intake/fields` | open | — | custom-intake field specs (form renders from this) |
| `POST /api/extract-profile` | token | 6/min | PDF/TXT upload → LLM-extracted draft (agents/intake.py) |
| `POST /api/run/prepare` | token | 6/min | validate intake values → one-time `run_id` (15-min TTL) |
| `POST /api/run` | token | `VANTAGE_RUN_RATE_LIMIT` (6/min) | sync run → memo JSON |
| `GET /api/run/stream` | token (`Authorization` or `?token=`) | 6/min | SSE progress events (`category`+`company_id`, or `run_id`) |
| `POST /api/early-access` | token | `VANTAGE_SIGNUP_RATE_LIMIT` (5/min) | email capture (JSONL, in-memory dedupe) |
| `GET /health` | open | — | health check |

**Custom intake (`api/intake_fields.py`, `agents/intake.py`):** field specs
are the single source of truth for the frontend form, the extraction tool
schema, and profile assembly — a test asserts that filling exactly the
required intake fields always satisfies the category's Pydantic schema, so
the two can't drift. Document extraction (pypdf for PDFs, 20k-char cap)
feeds an `emit_profile` tool call that must never invent numbers the
document doesn't state (scored by the `intake_extraction` eval, including a
prompt-injection probe); the draft pre-fills the form, the **user reviews
and completes it**, and only the validated result can run — extraction
output is data on a form, never an instruction channel. Custom runs stage
the validated profile under a single-use `run_id` because EventSource
cannot POST a body.

\* Token auth activates only when `VANTAGE_API_TOKEN` is set; local demos run
open. CORS origins come from `CORS_ORIGINS` (default: localhost:3000 dev
origins — never `*`). 500 responses are generic; tracebacks go to the server
log only.

**Inline profiles:** `POST /api/run` accepts a full `company` JSON object; it
is validated by per-category Pydantic schemas (`api/schemas.py`) *before any
LLM call* — required numerics with sane bounds, free-text length caps
(prompt-injection surface reduction). Invalid input → 422 with field errors.

**SSE lifecycle:** the worker thread runs the pipeline behind a queue; the
generator polls with a 15s timeout emitting keep-alive comments. On client
disconnect (or stream end) a `CancelToken` is cancelled; the pipeline checks
it between stages and aborts via `PipelineCancelled`, so an abandoned run
stops spending provider tokens at the next stage boundary.

**SSE event vocabulary** (consumed by `frontend/lib/useAgentRun.ts`):
`planner_started`, `planner_result`, `retrieval_started`, `retrieval_claim`,
`retrieval_complete`, `modeling_started`, `modeling_result` (one per
scenario), `explainability_started`, `explainability_chunk`,
`explainability_complete`, `recommendation_started`, `recommendation_result`,
`memo_ready`, `error`. Branch events carry `branch_id`; branches may
interleave because they run in parallel.

---

## 4. Benchmark corpus — what's real, what's synthetic

### 4a. Customer Support AI (`data/benchmarks/customer_support_ai.json`)

All 9 facts are **paraphrased from real published sources**. None are
placeholder numbers; values are as reported by the listed sources (mostly
secondary citations, not independently verified primary research).

| ID | Claim (paraphrased) | Value | Source |
|----|---------------------|-------|--------|
| `mckinsey_roi_multiple` | Avg ROI ~5.8x within ~14 months of production | 5.8x | McKinsey Global AI Survey |
| `nvidia_sector_adoption` | Adoption/ROI varies by sector; retail active | qualitative | NVIDIA State of AI Report 2026 |
| `deloitte_productivity_gains` | ~66% of enterprises report productivity gains | 66% | Deloitte State of AI in the Enterprise |
| `deloitte_revenue_aspiration_gap` | 74% hope for revenue impact, ~20% achieve it | 74%/20% | Deloitte State of AI in the Enterprise |
| `sector_payback_finance` | Finance AI payback ~8 months | 8 mo | published sector surveys |
| `sector_payback_manufacturing` | Manufacturing AI payback ~12–14 months | 12–14 mo | published sector surveys |
| `cs_tier1_deflection` | CS chatbots resolve ~68% of Tier-1 tickets | 68% | chatbot resolution benchmarks |
| `htec_true_op_cost` | True op cost often 3–5x initial build | 3–5x | HTEC AI cost/ROI framework |
| `htec_roi_formula` | ROI = (TBV − TC)/TC; costs scale non-linearly Y2+ | formula | HTEC AI cost/ROI framework |

### 4b. Marketing AI (`data/benchmarks/marketing_ai.json`)

Key facts used by clamping/sanity logic: `realistic_marketing_roi_range`
(20-25% lift), `integrated_workflow_performance` (32% ceiling),
`use_case_roi_content_drafting` (~3.2x, sanity ceiling) plus three more
McKinsey use-case ROI figures for reference context.

### 4c. Predictive Maintenance AI (`data/benchmarks/predictive_maintenance_ai.json`)

Key facts: `mid_market_realistic_target_range` (11-18% spend / 30-40%
downtime reduction), `mid_market_savings_reality`,
`enterprise_downtime_cost_reduction`.

### 4d. Synthetic company profiles

| File | Category | Intentionally-optimistic claim | Intentionally-unknown field |
|------|----------|-------------------------------|-----------------------------|
| `meridian_support.json` | Customer Support | 50% deflection (vs 20-35% typical) | `hosting_architecture` |
| `novavita_marketing.json` | Marketing | 45% lift (vs 32% ceiling) | `data_enrichment_strategy` |
| `apex_maintenance.json` | Maintenance | 35% spend reduction (vs 11-18%) | `hardware_deployment_method` |

All company profiles are **fully fabricated** demo data. Raw benchmark
research is archived in `data/benchmarks/_research_raw/` for provenance.

---

## 5. Verification

| Layer | Mechanism |
|-------|-----------|
| Modeling math | `backend/tests/test_roi_*.py` — hand-derived expected values per category/scenario, clamp and payback edge cases |
| Sanity check | `test_sanity_check.py` — every ceiling/floor boundary |
| Citation guard, confidence validators, flag/citation parsers | `test_guards.py` |
| Claim extraction | `test_claims.py` |
| Explanation contract (JSON tail, legacy fallback, stream gate) | `test_explanation.py` |
| Full pipeline (mocked providers) | `test_memo_golden.py` — memo structure, deterministic numbers, event sequence, chunk gating, per category |
| API (auth/422/429/500/SSE) | `test_api.py` |
| Live model behavior | `backend/evals/` — scored against real providers, run manually/nightly (see `docs/EVAL_LOG.md`) |

CI (`.github/workflows/ci.yml`): ruff + pytest (offline) + frontend
typecheck/build on every push.

---

## 6. Known limitations / open issues

1. **NVIDIA rate limits:** the free-tier nemotron endpoint rate-limits under
   load; parallel branches make two concurrent explainability calls. The
   Vultr GLM fallback works but produces lower-quality prose and may ignore
   the `===DATA===` contract (the legacy regex parse then applies).
2. **Reasoning-token overhead:** Kimi/MiniMax consume budget in an invisible
   `reasoning` field; all structured outputs therefore use
   `tool_choice="required"`. Kimi often exhausts the claim-validation budget
   and falls back to MiniMax — both produce equivalent verdict quality.
3. **Secondary citations:** benchmark facts are paraphrased from articles
   citing the primary reports, not the reports themselves.
4. **No adoption/change-management modeling:** costs and benefits assume
   successful deployment.
5. **Single validation pass:** the "Internal ⇄ Benchmark dialogue" is rerank
   retrieval + one LLM validation call, not multi-turn debate.
6. **Prompt-injection surface:** inline company free-text fields are
   length-capped but still flow into prompts; a hostile profile could try to
   steer verdicts. The citation guard bounds the damage (it cannot fabricate
   citations); treat verdict wording on untrusted profiles accordingly.
