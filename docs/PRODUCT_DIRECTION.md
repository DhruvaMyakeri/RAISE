# Vantage Product Direction — from one-shot memo to a living business case

**Date:** 2026-07-14 · **Status:** proposal (researched, not yet built)

## The problem with today's product

Vantage currently answers one question, once: *"what would this AI project
return if we built it?"* A company asks that question per initiative, per
decision — maybe a handful of times a year. That is episodic usage, and
episodic products don't retain, don't compound, and price like reports, not
software. The gap is not more agents or more categories; it is **a reason to
come back every month**.

## What the market says (July 2026)

- Fewer than one in three AI decision-makers can tie AI value to P&L changes
  (Forrester 2026 Predictions, via [Olakai](https://olakai.ai/ai-roi/)); 74%
  of enterprises want AI revenue growth, only ~20% achieve it
  ([Deloitte State of AI 2026](https://www.deloitte.com/us/en/what-we-do/capabilities/applied-artificial-intelligence/content/state-of-ai-in-the-enterprise.html)).
- More than two-thirds of organizations still track AI ROI **manually or as
  projections**, even for production systems; analysts now push splitting
  "Trending ROI vs Realized ROI"
  ([ModelOp AI Portfolio Intelligence](https://www.modelop.com/good-decisions-series/ai-portfolio-intelligence-the-key-to-tracking-enterprise-ai-value),
  [ModelOp 2026 Governance Benchmark](https://www.globenewswire.com/news-release/2026/03/11/3253668/0/en/modelop-s-2026-ai-governance-benchmark-report-shows-explosion-of-enterprise-ai-use-cases-as-agentic-ai-adoption-surges-but-value-still-lags.html)).
- The post-deployment measurement lane is getting crowded:
  [Olakai](https://olakai.ai/) (usage/cost governance across copilots and
  agents), [Workhelix](https://www.workhelix.com/) (impact, savings,
  superusers), ModelOp (portfolio governance). **None of them owns the
  pre-deployment cited projection, and none reconciles the original business
  case against what actually happened at the assumption level.**
- In B2B buying (6+ stakeholders, 6–12 month cycles), "the vendor who hands a
  champion a pre-built business case wins disproportionately"
  ([Pod, ROI business-case guide](https://www.workwithpod.com/post/roi-business-case-templates-for-enterprise-software-purchases-a-complete-guide));
  43% of enterprise buyers weigh outcome-based pricing
  ([Monetizely 2026 pricing guide](https://www.getmonetizely.com/blogs/the-2026-guide-to-saas-ai-and-agentic-pricing-models)).

## The pivot: the AI Investment Register (a living business case)

Keep everything that makes Vantage credible — deterministic math, cited
benchmarks, guarded citations, flagged assumptions — and wrap it in a
**loop** instead of a one-shot:

```
1. PROJECT   (exists today)
   Cited, scenario-banded ROI projection; every weak input flagged.

2. COMMIT    (new, small)
   Approving a case freezes it as a baseline. Its flagged assumptions
   become an Assumption Register: testable predictions with owners and
   review dates ("deflection ≥ 35% by month 4", "inference ≤ $6k/mo").

3. RECONCILE (new, the recurring engine)
   Monthly actuals come in (CSV upload / form / API): ticket volume,
   realized deflection, actual spend. Vantage recomputes the same
   deterministic model with actuals, shows projected-vs-realized variance,
   and flips each assumption to CONFIRMED / BROKEN / PENDING — with the
   same explain-why machinery used pre-deployment.

4. REFORECAST + ALERT (new)
   A broken assumption triggers a re-run: "at the measured 22% deflection,
   likely 3-yr ROI drops from 5.7x to 2.9x; payback moves from 8 to 19
   months — here is the memo diff." That is an email a CFO opens.

5. PORTFOLIO  (new, later)
   Every AI initiative in one register: projected vs trending vs realized
   ROI, confidence-weighted, with the worst broken assumptions on top.
   This is the artifact for quarterly AI-portfolio reviews.
```

**Why this is used constantly:** it attaches to cadences that already exist —
monthly finance variance reviews, quarterly reforecasts, every new AI
proposal. The product's "job" changes from *write me a memo* to *keep me
honest about every AI bet we've made*.

**Why Vantage specifically can win it:** reconciliation is a trust product.
The incumbents meter usage and cost; Vantage's differentiator — LLMs never
compute the number, every benchmark is cited, hallucinated citations are
structurally impossible, assumptions are first-class objects — is exactly
what makes a variance verdict defensible in a board deck. And the loop feeds
a compounding moat: anonymized projected-vs-realized deltas become the
proprietary benchmark corpus ("companies like you projected 45% lift and
realized 19%") that no report-writer or generic LLM can replicate.

## Who pays

1. **AI program offices / CoEs at mid-market companies** (the register buyer):
   per-initiative + seats, ~$1–3k/mo for a portfolio of 5–20 initiatives.
2. **Consultancies and fractional CxOs** (the fastest revenue): white-label
   projections + quarterly reconciliation retainers; per-report ($99–$500)
   converting into per-client subscriptions.
3. **AI vendors' value-engineering teams**: credible third-party-grounded
   business cases for their prospects; the "we flag your own optimistic
   claims" posture is the credibility feature they cannot build themselves.
   Outcome-based pricing trends make a defensible projection→actuals audit
   trail directly monetizable here.

## What to build, in order (mapped to the current codebase)

| Step | Builds on | Size |
|------|-----------|------|
| 1. Custom company intake (form → validated profile; the schema gate in `api/schemas.py` already exists) | schemas, pipeline core | M |
| 2. Run persistence (SQLite: runs, memos, assumptions as rows — `flagged_assumptions` already parse into typed objects) | memo_json flags | M |
| 3. Baseline commit + Assumption Register UI (status lifecycle on stored flags) | 2 | M |
| 4. Actuals ingestion (CSV/form) + deterministic re-run + variance memo (reuse `modeling/*` unchanged — this is the whole point of keeping math in Python) | claims, modeling | L |
| 5. Reforecast alerts (email/Slack on assumption break) | 4 | M |
| 6. Portfolio dashboard (aggregate stored runs) | 2–5 | L |
| 7. Anonymized benchmark feedback loop (projected-vs-realized corpus facts, opt-in) | 4, corpus format | L+ |

Generalizing beyond the three categories comes *after* the loop exists —
a metric-schema-driven category definition (value driver + cost profile +
benchmark set as data, not code) replaces the per-category modules when a
design partner needs a fourth category.

## What NOT to do

- Don't add more agents or debate rounds — reasoning depth is not the
  adoption barrier; recurrence is.
- Don't build usage-metering (Olakai/Workhelix lane; requires integrations
  Vantage can't win on).
- Don't chase enterprise giants; mid-market + consultancies match the
  benchmark corpus and the sales motion.

## Fastest path to first revenue

Sell the loop before generalizing it: one consultancy or fractional-CFO
design partner, their client's real numbers hand-entered into the three
existing categories, a quarterly reconciliation retainer. Steps 1–4 above
are sufficient for that engagement.

---

*Sources: [Olakai](https://olakai.ai/), [Olakai — measuring AI ROI](https://olakai.ai/ai-roi/),
[Workhelix](https://www.workhelix.com/),
[ModelOp — AI Portfolio Intelligence](https://www.modelop.com/good-decisions-series/ai-portfolio-intelligence-the-key-to-tracking-enterprise-ai-value),
[ModelOp 2026 AI Governance Benchmark](https://www.globenewswire.com/news-release/2026/03/11/3253668/0/en/modelop-s-2026-ai-governance-benchmark-report-shows-explosion-of-enterprise-ai-use-cases-as-agentic-ai-adoption-surges-but-value-still-lags.html),
[Deloitte State of AI in the Enterprise 2026](https://www.deloitte.com/us/en/what-we-do/capabilities/applied-artificial-intelligence/content/state-of-ai-in-the-enterprise.html),
[Pod — ROI business-case templates](https://www.workwithpod.com/post/roi-business-case-templates-for-enterprise-software-purchases-a-complete-guide),
[Monetizely — 2026 SaaS/AI pricing models](https://www.getmonetizely.com/blogs/the-2026-guide-to-saas-ai-and-agentic-pricing-models).*
