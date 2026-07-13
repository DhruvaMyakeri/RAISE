# Vantage Remediation Log

**Date:** 2026-07-14 · **Branch:** `vantage-remediation` · **Scope:** every
finding from the 2026-07-13 technical audit. One entry per finding: what was
wrong, what changed, where, what proves it, residual risk.

Verification vocabulary used below:
- **tests** = offline pytest (`backend/tests`, 81 tests, CI on every push)
- **evals** = live model-behavior scoring (`backend/evals`, see EVAL_LOG.md)
- **parity diff** = mocked-provider memos captured from the pre-refactor
  pipeline and diffed against the post-refactor pipeline: identical
  decision-relevant content across all 3 categories

---

## Architecture & Design

### A1 (High) — Three divergent pipeline implementations
**Was:** `api/pipeline_runner.py`, `pipeline/run_category.py`, and
`pipeline/run_slice.py` each re-implemented the stage loop; behavior had
already drifted (the API path never called the Planner LLM).
**Fix:** single stage loop in `backend/pipeline/core.py`, driven by an
`EventEmitter` (`pipeline/events.py`); API uses `CallbackEmitter`→SSE, CLI
uses `PrintingEmitter`, tests use list capture. The three old copies are
deleted.
**Proof:** parity diff; golden pipeline regression per category
(`test_memo_golden.py`); live e2e CLI run.

### A2 (High) — ~85-line copy-pasted recommendation generator
**Was:** `report._generate_recommendation` and
`memo_json._generate_recommendation_structured` were near-identical.
**Fix:** one `agents/report.py::generate_recommendation` (structured return);
`api/memo_json.py` now contains zero LLM calls; the CLI text memo derives
from the same result.
**Proof:** parity diff (recommendation text identical under mocks); grep — no
second implementation; `recommendation_integrity` eval 6/6 live.

### A3 (Medium) — Private cross-module imports
**Was:** `api/` imported `_call_modeling_direct`, `_extract_claims_generic`,
`_load_json` from a CLI script and `_confidence_citations_valid`,
`_parse_overall_confidence` from an agent.
**Fix:** shared logic moved to owned public homes (`pipeline/core.py`,
`pipeline/claims.py`, `report.generate_recommendation`,
`explainability.parse_explanation`). No `_private` imports across the
`api`/`pipeline`/`agents` boundaries remain (tests importing privates for
white-box assertions is deliberate).
**Proof:** grep; suite green.

### A4 (Medium) — Duplicate, drift-prone claim extraction
**Was:** `retrieval._extract_claims` (field-sniffing) vs
`run_category._extract_claims_generic` (category dispatch); the runner
overwrote one with the other after the fact.
**Fix:** single `pipeline/claims.py::extract_claims`; `run_retrieval_dialogue`
now *receives* the claims dict instead of extracting its own, so the LLM
validates exactly what the modeling tool computes with.
**Proof:** `test_claims.py` (values per category, clamp, unknown-category);
parity diff on `reconciled_inputs`.

### A5 (Medium) — LLM prose parsed by regex as a data channel
**Was:** overall confidence and per-dimension scores were regex-scraped from
free text (`report.py`, `memo_json.py`).
**Fix:** structured contract — the explainability model emits a final
`===DATA=== {json}` line with per-dimension/overall confidence;
`parse_explanation()` uses the JSON as primary channel, the legacy regex
parse only as fallback; `_MarkerGate` withholds the tail from streamed UI
chunks (gated above the provider seam, so any source — including the Vultr
fallback — is gated).
**Proof:** `test_explanation.py` (tail parse, malformed-tail fallback, gate
split-marker cases); golden test asserts chunks never contain the marker;
`explainability_format` eval **12/12 live** — nemotron honored the contract
in all 3 categories.
**Residual:** the GLM fallback model may ignore the tail; the legacy parse
then applies (this is measured by the eval, not silent).

### A6 (Low) — Leaky field naming / lost branch identity
**Was:** `ModelingOutput.hosting_architecture` carried marketing/maintenance
branch values; the recommendation payload's `"hosting"` was `None` for
non-CS categories; branch-unknown flags said `hosting_architecture=` for all
categories.
**Fix:** `ModelingOutput.branch_value`; recommendation payload carries
`branch_choice: {field, value}`; flags name the true branch field.
**Proof:** tests + parity diff (flag *types* identical; text change is the
intentional correctness fix).

---

## Code Quality

### Q1 (Medium) — Hardcoded demo shortcuts in the "generic" planner
**Was:** `plan_and_clarify` force-overrode every classification to
"Customer Support AI" and hardcoded the demo product name.
**Fix:** **Decision (made autonomously per the remediation brief): the
Planner-LLM path is retired**, not repaired. Rationale: (a) the web API never
invoked it; (b) Python normalized its branch output back to deterministic
defaults regardless of what the model returned — it added latency and failure
modes without adding decisions; (c) keeping it meant maintaining a second
source of branch truth forever. `agents/planner.py`, `pipeline/run_slice.py`,
and the planner probe scripts are deleted; model constants renamed
`CLAIM_VALIDATION_MODEL*` to say what the LLM actually does. README and
ARCHITECTURE document the retirement.
**Proof:** grep (no planner references); suite green; live e2e run.

### Q2 (Medium) — Exception swallowing with no diagnostics
**Was:** `except Exception: continue` fallback loops with zero logging;
`print()` as the only diagnostic.
**Fix:** `logging` throughout (`retrieval`, `explainability`, `report`,
`rerank`, `main`); every fallback/retry logs model + cause; API logs full
tracebacks server-side. The retry-then-fallback *pattern* is kept — it is
correct — it just no longer hides why it fired.
**Proof:** live eval output shows the Kimi→MiniMax fallback logged with
`finish=length` cause (previously invisible).

### Q3 (Low) — Dead code
**Fix:** deleted `json_util.parse_json_object` (zero callers), the no-op
marker loop in explainability, `LEGACY_KIMI_ALIAS`, unused
`PLANNER`/`INTERNAL_RETRIEVAL`/`BENCHMARK_RETRIEVAL` token budgets, and the
retired planner path (Q1).
**Proof:** grep; ruff clean; suite green.

### Q4 (Low) — Committed run artifacts
**Fix:** `git rm` of `_api_run_cs.json`, `_probe_out.json`,
`api_test_*.json`, `last_memo*.txt`; `.gitignore` patterns added.

---

## Security

### S1 (High) — No auth / rate limiting on paid endpoints
**Fix:** shared bearer token (`VANTAGE_API_TOKEN`; off when unset so local
demos stay zero-config) on `/api/run`, `/api/run/stream` (also `?token=` —
EventSource cannot set headers), `/api/early-access`; slowapi per-IP limits
(`VANTAGE_RUN_RATE_LIMIT` 6/min, `VANTAGE_SIGNUP_RATE_LIMIT` 5/min).
Read-only demo-data endpoints stay open by design.
**Proof:** `test_api.py` — 401 without/with wrong token, 200 with token, SSE
query-param auth, 429 after limit.
**Residual:** a shared token is deliberate scope (per the brief); per-user
keys/accounts are a SaaS-launch decision. `NEXT_PUBLIC_API_TOKEN` ships to
the browser — it gates cost abuse, it is not a secret; noted in code.

### S2 (Medium) — CORS wildcard with credentials
**Fix:** origins from `CORS_ORIGINS` env (default: localhost dev origins),
methods/headers narrowed. **Proof:** config inspection; app boots in tests.

### S3 (Medium) — Raw exception text to clients
**Fix:** generic 500 detail; tracebacks to server log; SSE error events
sanitized. **Proof:** `test_500_detail_is_generic` asserts internal strings
never reach the response.

### S4 (Medium) — Unvalidated inline company JSON into prompts/float()
**Fix:** per-category Pydantic schemas (`api/schemas.py`) validate inline
profiles **before any LLM call**: required numerics with sane bounds,
free-text length caps. Invalid → 422 with field errors.
**Proof:** `test_api.py` validation tests assert the pipeline is never
reached on bad input.
**Residual (documented, accepted):** validated free-text fields still flow
into prompts; a hostile profile could try to steer verdict *wording*. The
citation guard bounds the damage (fabricated citations are structurally
impossible). Full prompt-injection hardening (e.g. quoting/segregating
untrusted text, output filters) is future work; noted in README +
ARCHITECTURE §6.

### S5 (Medium) — Next.js 14.2.5 known CVEs
**Fix:** upgraded to 14.2.35 (latest 14.2.x), build + typecheck verified.
**Residual (documented, intentionally skipped):** npm audit still flags the
14.x line; the full fix is Next 15/16 — a breaking major upgrade. Verified
none of the remaining advisories apply to this codebase's usage (no
`next/image`, no middleware, no `next/script`, no WebSocket upgrades, no CSP
nonces). Logged as follow-up work, not silently accepted.

### S6 — Secrets (was already correct)
`.env` never committed (verified against all git revisions). **Action
required (user):** the Vultr/NVIDIA keys in the local `.env` were exposed to
local tooling during audit/remediation sessions — rotate them at the
provider consoles when convenient. Cannot be done from this environment.

---

## Testing (was: zero automated tests)

### T1 (Critical) — Money math and trust mechanisms untested
**Fix:** 81 offline tests:
- `test_roi_customer_support/marketing/maintenance.py` — exact expected
  values **hand-derived independently from the documented formulas** (not
  generated from the code), all scenarios, clamps, payback-None, flag merge.
  The hand-derivation matched the implementation exactly on first run — the
  audit's feared latent formula bug does not exist.
- `test_sanity_check.py` — every ceiling/floor boundary.
- `test_guards.py` — citation guard (hallucination rejection + scrubbing),
  confidence validators, flag/citation parsers.
- `test_claims.py`, `test_explanation.py`, `test_memo_golden.py` (full
  mocked pipeline per category: structure, numbers, event sequence,
  chunk gating), `test_api.py`.
**Plus** the live eval suite for probabilistic behavior (EVAL_LOG.md):
baseline run scored **27/27** across claim validation, explainability format,
and recommendation integrity.

---

## Performance

### P1 (Medium) — Sequential independent branches
**Fix:** branches A/B run in a `ThreadPoolExecutor(2)` for the API (results
collected in branch order); CLI stays sequential for readable logs.
Wall-clock roughly halves per run.
**Proof:** golden test passes with parallel path; live e2e run.

### P2 (Medium) — SSE worker never cancelled; blocking q.get
**Fix:** `CancelToken` checked between pipeline stages
(`PipelineCancelled`); SSE generator polls the queue with a 15s timeout,
emits keep-alive comments, and cancels the token in `finally` on client
disconnect — an abandoned run stops spending tokens at the next stage
boundary.
**Residual:** cancellation is cooperative at stage granularity; an in-flight
provider call completes before the check. Bounded and accepted.

### P3 (Low) — New TLS handshake per rerank call
**Fix:** module-level pooled `httpx.Client` + retry-with-backoff on
429/5xx/transport errors (`llm/rerank.py`).

---

## Dependencies / DX / Ops

### D1 (Medium) — Unpinned deps, no lockfile
**Fix:** `requirements.txt` pinned to the verified working set;
`requirements-dev.txt` (pytest, ruff).

### D2 (Medium) — No CI, no linter, no logging
**Fix:** `.github/workflows/ci.yml` — ruff + pytest + eval-harness smoke
(mocked) on the backend; `tsc --noEmit` + `next build` on the frontend, on
every push/PR. `ruff` configured in `pyproject.toml`, backend clean.
Logging: see Q2.

---

## Documentation

### DOC1 (Low) — Docs contradicted the code; naming drift
**Fix:** ARCHITECTURE.md rewritten to describe the unified pipeline as it
runs (its stale sections claimed FastAPI/frontend "not started" and
documented the retired planner as live); README pipeline description, models
table, structure, setup, API, and limitations corrected; testing/evals
section added; `FULL_PRROJECT_STATUS.md` → `PROJECT_STATUS.md` with
Praxis→Vantage naming fixed and historical docs marked historical;
`.env.example` documents all new variables. Product name is **Vantage**
everywhere (repo directory name RAISE refers to the hackathon and is
untouched).

---

## Fixed along the way (found during remediation, not in the audit)

- **Marketing explainability lost "Revenue impact":** the prompt filtered
  dimensions through a CS-only whitelist, silently dropping Marketing's
  Revenue dimension. Fixed; verified live (eval shows 100% coverage incl.
  Revenue impact).
- **Early-access dedupe was O(n) per signup** (re-read the whole file):
  in-memory set loaded once; email length cap added.
- `config/__init__.py` re-exports updated to the new constant names.

## Intentionally not done (with reasoning)

1. **Next 15/16 major upgrade** — breaking; remaining advisories don't apply
   to current usage (S5). Follow-up.
2. **Full prompt-injection hardening** — residual risk documented (S4);
   bounded by the citation guard and length caps.
3. **Accounts / per-user API keys / persistence** — explicitly out of scope
   per the brief; the product-direction doc (PRODUCT_DIRECTION.md) covers
   where persistence should go next.
4. **asyncio rewrite of the backend** — thread-level parallelism (P1) captures
   the win; a full async migration isn't warranted before real concurrency.
5. **Key rotation** — requires provider-console access only the owner has (S6).

## Verification summary

| Gate | Result |
|------|--------|
| Offline tests | 81/81 pass (`python -m pytest backend/tests`) |
| Lint | ruff clean |
| Frontend | `tsc --noEmit` + `next build` pass on 14.2.35 |
| Refactor parity | pre/post mocked memos identical (all 3 categories) |
| Live evals | 27/27 (EVAL_LOG.md, 2026-07-14) |
| Live e2e | full CLI pipeline run against real providers (customer_support) |
