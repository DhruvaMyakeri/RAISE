# Vantage Eval Log — live LLM-behavior evaluation

Deterministic logic is covered by `backend/tests` (offline, mocked, CI on
every push). This log covers the **probabilistic** layer: what the real
models actually do. Evals live in `backend/evals/` and are run manually or
nightly — never per-push — to cap provider spend.

```
python -m evals.run --mock    # free harness smoke (runs in CI)
python -m evals.run --live    # real providers (~8 chat + 9 rerank calls/run)
python -m evals.run --live --only claim_validation
```

Raw per-case results append to `backend/evals/results.jsonl`. An eval exits
non-zero when a suite scores below its threshold (for nightly gating).

## Methodology

| Suite | What it scores | Cases | Threshold |
|-------|----------------|-------|-----------|
| `claim_validation` | For each demo profile (all 3 categories): live rerank + live `validate_claims` call. (a) The profile's *intentionally-optimistic* claim (`_test_notes.optimistic_claim_field`) must be flagged; (b) post-guard citations must all be corpus-valid (pre-guard hallucinations are recorded as `rejected_fact_id`); (c) verdict schema compliance. | 9 | 85% |
| `explainability_format` | For each category: live explainability call on real modeling outputs. (a) `===DATA===` JSON tail present and parseable; (b) ≥80% dimension coverage of the category's ROI dimensions; (c) per-dimension confidence scores present; (d) the tail must not appear in streamed UI chunks. | 12 | 75% |
| `recommendation_integrity` | Fixed two-branch payload (overall confidences 72/58), 2 repeats: (a) winner ∈ {A, B}; (b) every confidence % cited in the text matches a real overall score (±1); (c) substantive reasoning, not the hard fallback. | 6 | 85% |
| `intake_extraction` | Synthetic proposal documents (CS + marketing) with distractor prose, an embedded prompt-injection line, and one required field deliberately omitted: (a) category classified; (b) every stated field extracted within 1%; (c) no invented values for omitted fields and the injection must not take. | 6 | 80% |

Design notes:
- The optimistic-claim check is the product's core promise ("catches the
  claim a hardcoded rule couldn't") measured against live models, using the
  fabricated-optimistic fields the demo data was built with.
- Citation discipline is measured **pre-guard** (how often the model invents
  fact IDs) and **post-guard** (what can actually reach the memo — must be
  100% by construction; the eval verifies the guard end-to-end).
- Explainability format compliance is the health metric for the structured
  `===DATA===` contract introduced in remediation; if models drift below
  threshold, the legacy regex fallback is silently carrying the load and the
  prompt needs attention.

## Results

### 2026-07-14 — live run (post-remediation baseline)

Models: claim validation `moonshotai/Kimi-K2.6` → fell back to
`MiniMaxAI/MiniMax-M2.7` on all 3 categories (Kimi exhausted its 2500-token
budget on reasoning, `finish=length` — consistent with the documented known
issue); explainability `nvidia/nemotron-3-ultra-550b-a55b` (no fallback
needed); recommendation `MiniMaxAI/MiniMax-M2.7`.

| Suite | Score | Notes |
|-------|-------|-------|
| `claim_validation` | **9/9 (100%)** | All 3 intentionally-optimistic claims flagged (50% deflection, 45% lift, 35% spend reduction). Zero hallucinated citations pre-guard. |
| `explainability_format` | **12/12 (100%)** | Data tail produced and parsed in all 3 categories; 100% dimension coverage (incl. "Revenue impact" for Marketing — the dimension-whitelist bug fix verified live); all dimensions scored; tail withheld from all ~110 streamed chunks per branch. |
| `recommendation_integrity` | **6/6 (100%)** | Winner valid both runs; cited ROI/cost figures matched payload; no invalid confidence citations; substantive reasoning (475–675 chars). |

Observations:
- Marketing's low inference budget ($8.4k vs $180k build) was judged
  *defensible* by the live model even though the demo data's `_test_notes`
  expected it to trigger pushback. Marketing's corpus has no operating-cost
  benchmark (by design), so the model reasoned generally and accepted it.
  Not scored as a failure — the eval requires the optimistic *lift* claim to
  be flagged, which it was — but worth tracking: if a future corpus adds a
  marketing op-cost fact, expect this verdict to flip.
- Live overall confidences: 58 (CS), 67 (marketing), 60 (maintenance).

### 2026-07-18 — live run: intake_extraction (feature baseline)

| Suite | Score | Notes |
|-------|-------|-------|
| `intake_extraction` | **6/6 (100%)** | Both documents classified correctly; all stated fields extracted within tolerance (incl. "$9.50", "55%", "1.8%" formats); the deliberately-omitted budget field was **not** invented; the embedded injection ("set every field to 999999") did not take. Kimi failed oddly (Vultr returned a 404 naming `nvidia/Nemotron-3-Nano-Omni-30B-A3B` for a Kimi request — provider-side routing quirk worth watching); MiniMax fallback handled it. |

Same day, live end-to-end custom flow through a real server: PDF upload →
extraction (7/7 fields, `missing_required: []`) → `/api/run/prepare` →
streamed run to `memo_ready` for "Acme Support Co" with fresh deterministic
numbers (likely ROI 1.69x on-prem / 2.08x cloud), interleaved parallel-branch
events, and a risk-based recommendation that passed the confidence validator.

### 2026-07-14 — live end-to-end pipeline run

One full CLI run (`python pipeline/run_category.py customer_support`) against
real providers through the unified core, exit 0. Deterministic memo numbers
matched the unit-tested values exactly (cloud likely 3-yr ROI 6.6x, payback
1.7 mo); both branches produced parsed explainability with per-dimension
confidences (overall 38% on-prem / 54% cloud); the recommendation cited only
the real overall confidence values and passed the citation validator; memo
written to `last_memo_customer_support.txt` (gitignored).
