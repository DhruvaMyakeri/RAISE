# Vantage — Full Project Status
### RAISE Summit Hackathon 2026 — Vultr Track
**As of:** July 4, 2026

> **Historical snapshot (hackathon, 2026-07-04).** Kept for context. For current
> architecture see ARCHITECTURE.md; for post-hackathon changes see REMEDIATION_LOG.md.

---

## 1. The Problem

Enterprises are spending heavily on AI initiatives but can rarely answer a
simple question with confidence: *"How much did this AI project actually
return, or how much will it return if we build it?"*

This is not a manufactured pain point — it's well-documented:

- Only ~20% of organizations report actually achieving the revenue growth
  they expect from AI, versus ~74% who hope to (Deloitte, State of AI in
  the Enterprise)
- Only 6% of enterprises are "high performers" who can attribute a
  meaningful bottom-line impact to their AI investments, despite ~88%
  having deployed AI somewhere (McKinsey, State of AI in 2025)
- 30% of generative AI projects are abandoned after proof-of-concept,
  often due to unclear business value (Gartner)
- Lack of clarity on AI's ROI is cited as a top adoption challenge by
  ~30% of enterprises (NVIDIA State of AI Report 2026)

Existing tools in this space (Pay-i, Olakai, Workhelix, Larridin,
Agentplace, TFSF Ventures) largely measure ROI **after** AI is already
deployed, or are static calculators/questionnaires used **before**
deployment. None combine document-grounded retrieval, cited industry
benchmarks, and visible multi-step reasoning in one agentic system.

---

## 2. What We Built

An agentic, multi-step system that takes a company's proposed AI project
and produces a cited, scenario-based ROI projection — grounding every
number in either the company's own data or a real, sourced industry
benchmark, and explicitly flagging assumptions that don't hold up.

**North star:** not "replaces a consultancy" (overclaim) — more precisely,
**accelerates and grounds the first stage of a consultancy engagement**:
the discovery-and-benchmarking work that normally takes weeks, compressed
to minutes, with the reasoning shown rather than hidden.

### Who it's for
Mid-size enterprises (not startups, not enterprise giants) with an
**existing operational baseline** — ticket volume, ad spend, maintenance
costs, etc. — evaluating whether to adopt a specific, well-defined AI
capability. The actual user is whoever has to build the business case
(finance/strategy analyst, ops director) for a CEO or investment
committee — not the CEO directly.

### What it explicitly does NOT do
- Does not evaluate startup/venture viability (market sizing, funding
  potential) — only "should an existing company with existing data adopt
  this capability"
- Does not generalize beyond 3 hardcoded project categories
- Does not give investment advice — outputs are explicitly labeled "not
  financial advice"

---

## 3. Architecture — What's Actually Running

Full technical detail lives in `docs/ARCHITECTURE.md`. Summary:

### Pipeline (6 stages, 5 LLM-driven agents + 1 deterministic tool)

```
Company Profile
      ↓
Planner (classify, detect unknowns, branch on uncertainty)
      ↓
Retrieval Layer (per branch):
  Internal Retrieval (rerank) → Benchmark Retrieval (rerank)
      → LLM Claim Validation (judges claims against benchmark evidence)
      ↓
Modeling Tool (deterministic Python — HTEC ROI formula, 3 scenarios,
  non-linear Y2+ cost scaling, output-level sanity check)
      ↓
Explainability Agent (breaks down projection by Slalom ROI dimension,
  confidence score per dimension)
      ↓
Report Agent (side-by-side memo, LLM-reasoned recommendation)
```

### Models in use

| Role | Model | Provider |
|---|---|---|
| Planner / claim validation | `moonshotai/Kimi-K2.6` (fallback `MiniMaxAI/MiniMax-M2.7`) | Vultr Serverless Inference |
| Retrieval (rerank) | `vultr/VultronRetrieverCore-Qwen3.5-4.5B` | Vultr Serverless Inference |
| Explainability | `nvidia/nemotron-3-ultra-550b-a55b` (fallback `zai-org/GLM-5.2-FP8`) | NVIDIA build.nvidia.com (fallback Vultr) |
| Report recommendation | `MiniMaxAI/MiniMax-M2.7` (fallback `Kimi-K2.6`) | Vultr Serverless Inference |
| Math / ROI calculation | None — deterministic Python | N/A |

**Hard rule maintained throughout:** LLMs never compute the final ROI
number. All arithmetic runs in plain, auditable Python.

### The core differentiator, concretely proven

The claim-validation step doesn't just check if a number is "too high" —
it reasons over evidence. Real example from testing: the system caught
that a company's claimed 50% ticket deflection rate was actually
extrapolating a Tier-1-only industry benchmark (68%) across *all* ticket
types — a genuine logical error a hardcoded threshold could never catch.

### Data integrity discipline

- Every benchmark fact is paraphrased (not copied) from real, named,
  cited sources — McKinsey, Deloitte, NVIDIA State of AI, HTEC, Gartner,
  IoT Analytics, Persistence Market Research, Siemens/Aberdeen, and
  others — with source tier and citation type (primary/secondary)
  recorded for honesty
- A hard citation guard rejects any fact ID an LLM cites that wasn't
  actually shown to it — hallucinated citations are structurally
  impossible, not just discouraged
- Two real bugs were caught and fixed during build: (1) a benchmark
  reference injected into every category's prompt regardless of whether
  that category's corpus actually contained it, causing two branches of
  the same memo to contradict each other about whether a fact existed;
  (2) a recommendation step citing a per-dimension confidence score as if
  it were the overall confidence, due to a truncated context window. Both
  fixed with structural guards (citation validation, confidence-value
  verification with regenerate-on-mismatch), not just prompt tweaks.
- An **output-level sanity check** (separate from input-claim validation)
  catches cases where even a corrected/clamped input still produces an
  implausible final ROI or payback — e.g. an unrealistically low
  implementation-cost estimate slipping through despite realistic input
  claims. Ceilings are corpus-cited where a benchmark exists, and
  explicitly labeled as modeling assumptions where none exists (this
  distinction is maintained transparently, not blurred).

---

## 4. The 3 Categories — Current State

| Category | Benchmark facts | Company profile | Modeling logic | Status |
|---|---|---|---|---|
| Customer Support AI | 9 (real, cited) | Meridian Retail Co. (fabricated) | Ticket deflection × cost/ticket | ✅ Full pipeline tested, regression-locked |
| Marketing AI | 11 (real, cited) | Novavita Health Tech (fabricated) | Conversion lift × traffic × AOV | ✅ Full pipeline tested |
| Predictive Maintenance AI | 10 (real, cited) | Apex Precision Components (fabricated) | Maintenance spend reduction + avoided downtime (2 additive components) | ✅ Full pipeline tested |

Each company profile carries exactly one intentionally-optimistic claim
(to test whether validation catches it) and one intentionally-unknown
field (to test scenario branching) — all three categories have been
proven to correctly flag their planted unrealistic claim and correctly
branch into two scenarios with a coherent, non-contradictory memo.

Raw research (with source/tier/confidence metadata) is archived
separately in `data/benchmarks/_research_raw/` for provenance.

---

## 5. What's NOT Built Yet

| Component | Status |
|---|---|
| Frontend (Next.js) | Not started — CLI-only currently |
| FastAPI backend / API routes | Not started — pipeline runs as scripts |
| Live agent-trace streaming to UI | Not started (this was a stated design goal — showing the reasoning live, not hiding it behind a spinner, is the main defense against looking like "just a dashboard") |
| Dynamic real user input | Currently hardcoded to `"unknown"` for the clarifying question |
| Additional company profiles (2-3 per category, mixed formats) | Only 1 per category exists |
| Planner LLM for new-category branching | Marketing AI / Predictive Maintenance AI branch deterministically (no LLM call for branch construction); only Customer Support AI still uses the Planner LLM for this |

---

## 6. Competitive Positioning (researched, not assumed)

Confirmed via research that this space is **not empty** — worth being
upfront about this rather than overclaiming novelty:

- **Pay-i, Olakai** — measure ROI of AI *already deployed* (operational
  cost accounting, governance) — different moment in the decision cycle
  than us
- **Workhelix, Larridin** — adoption/fluency tracking platforms —
  different focus (process monitoring, not financial prediction)
- **Agentplace, TFSF Ventures** — genuine pre-deployment ROI forecasting
  tools/calculators — the closest real competitors

**Honest differentiation:** these appear to be calculators or structured
questionnaires. Ours is an agentic system that retrieves from actual
company documents, cross-checks specific numeric claims against cited
benchmarks with visible reasoning (not just a form → number pipeline),
and flags exactly which assumptions are unvalidated and why.

---

## 7. Known Limitations (stated proactively, not hidden)

1. Benchmark data is real and cited but mostly **secondary citations**
   (blog/article citing the primary McKinsey/Gartner/Deloitte report, not
   the report itself) — a structural limitation of this kind of research,
   not unique to us
2. No adoption/change-management-probability modeling — the system
   computes cost/benefit assuming successful deployment, not the
   probability of successful organizational adoption (a real, cited
   factor in why AI ROI often disappoints)
3. Retrieval "dialogue" is a single LLM validation call reasoning over
   both company claims and benchmark evidence together — not two
   separate LLMs debating in turns, despite early design language
   suggesting otherwise
4. NVIDIA's free-tier Explainability endpoint rate-limits under load
   (~32 concurrent) — a tested, working fallback exists (GLM-5.2-FP8 on
   Vultr) but produces lower-quality prose when triggered
5. Predictive Maintenance AI's ROI sanity-check ceiling (5.0x) is a
   modeling assumption, not a corpus-cited figure — no published
   ROI-multiple benchmark exists for this category in the researched set
6. System has only been stress-tested against inputs deliberately
   designed to trigger its own validation logic — not against organic,
   unpredictable bad inputs from a real user

---

## 8. Compliance Checklist (hackathon rules)

- ✅ Not a disqualified category (not a dashboard-as-main-feature, not
  basic RAG, not a mental-health/medical/nutrition/personality bot)
- ✅ Benchmark corpus paraphrased, not copied, from source articles —
  copyright-safe
- ✅ Uses Vultr Serverless Inference + VultronRetriever as core stack
  (satisfies track requirement); NVIDIA Nemotron used as a deliberate,
  disclosed secondary component, not a replacement for the Vultr core

---

## 9. Immediate Next Steps, In Priority Order

1. **Frontend build** — highest priority remaining item. Should
   prioritize: (a) live agent-trace visualization (the stated
   differentiator vs. "just a dashboard"), (b) side-by-side scenario
   comparison visual, (c) assumption/confidence breakdown visual
2. **Personal verification pass** — before demo day, manually read at
   least one full memo output per category end-to-end (not just a
   summary) to catch any remaining issues, as has been done successfully
   twice already in this build
3. **Live-load rehearsal** — run the full demo during a busy period to
   confirm the NVIDIA rate-limit fallback behaves acceptably under
   pressure
4. **Pitch script** — incorporate the honest positioning from §6-7 above;
   do not overclaim "replaces a consultancy" or "no one else does this"