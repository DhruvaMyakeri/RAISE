> **Historical planning document (pre-build).** The implementation deviates in
> documented ways — ARCHITECTURE.md describes the system as it actually runs.

# AI ROI Agent — Project Plan (RAISE Hackathon 2026)

**Track:** Vultr — Enterprise Agent grounded in documents, multi-step, tool-calling
**Team:** Victor Robles, Dhruva

---

## 1. Final Goal

Build a multi-agent system that predicts and explains the ROI of a proposed AI
project for a mid-size enterprise. Not a calculator — an agent that:

1. Understands a company's current workflow/costs
2. Retrieves relevant industry benchmarks to sanity-check assumptions
3. Computes a real (non-LLM) financial projection across scenarios
4. Explains which inputs drove the number, flags shaky assumptions, cites sources
5. Outputs a CFO-readable memo, not a dashboard

**North star pitch:** "Replaces the first meeting with a consultancy firm —
grounded in your numbers, checked against real industry data, with the
reasoning shown, not hidden."

**Hard rule:** LLMs never do the arithmetic. All ROI math runs in a
deterministic Python function. LLMs plan, retrieve, and explain — not calculate.

---

## 2. Tech Stack

| Layer | Tool |
|---|---|
| Reasoning (agents) | Vultr Serverless Inference |
| Retrieval | VultronRetriever models (Vultr's own, see §3b) |
| Orchestration | Plain Python + function-calling loop (no LangChain — unneeded complexity for 20hrs) |
| Calculation | Deterministic Python function, called as a tool |
| Backend | FastAPI |
| Frontend | Next.js — single flow, shows live agent trace (not a dashboard) |
| Data | Curated real benchmark corpus + synthetic company profiles (see §5) |

---

## 3. Agent Pipeline

Five LLM agents + one deterministic tool, in order.

### 3a. Pipeline stages

1. **Planner/Orchestrator Agent**
   Classifies the project into one of 3 categories, decides which ROI
   dimensions apply (see §4), identifies missing data, can ask the user a
   clarifying question instead of assuming.

   **Scenario branching (extension, not a new agent):** if the user
   answers a clarifying question with "I don't know" on a real
   architectural/implementation choice (e.g. on-prem vs. cloud, Provider A
   vs. Provider B), Planner does NOT force a single guess. Instead it
   selects up to **2 representative options max** and tags the downstream
   pipeline run with which option. Each option is run through the
   existing pipeline independently — the Modeling Tool is simply called
   once per branch with different input assumptions; nothing new is built
   for the Modeling Tool itself. Report Agent renders the two as a
   side-by-side "Scenario A vs Scenario B" comparison rather than a single
   output. Hard cap: 2 branches max, only triggered on explicit user
   uncertainty — never speculative branching by default. This keeps total
   output bounded (2 architecture branches × 3 financial scenarios = 6
   numbers max), avoiding the "wall of numbers" risk flagged in §8.

2. **Retrieval Layer — Internal Retrieval Agent + Benchmark Retrieval Agent**
   These two agents run as a **dialogue, not a silent handoff**:
   - Internal Retrieval Agent pulls the company's own uploaded data (cost
     sheets, process description) and reports the company's claimed numbers.
   - Benchmark Retrieval Agent checks those claims against the curated
     industry benchmark corpus and pushes back if a claim looks unrealistic
     (e.g. "company claims 50% deflection; benchmark shows 20-35% typical
     for this company size — flag as optimistic").
   - Internal Retrieval Agent can respond if the company's own docs justify
     the outlier; otherwise the claim is passed downstream flagged as
     "assumption, not validated."
   - This exchange is what produces the "flagged assumption" data the
     Explainability Agent needs — it's not extra scope, it's the same two
     agents already in the plan, just interacting instead of handing off blindly.

3. **Modeling Tool** *(not an agent — plain Python, deterministic)*
   Takes the reconciled output from the retrieval layer, computes
   cost/benefit across conservative/likely/optimistic scenarios. Includes
   non-linear cost adjustment (integration + model-update costs scale in
   year 2+, not flat) per the HTEC framework.

4. **Explainability Agent**
   Breaks down which input drove which part of the projection, using the
   8-category Slalom framework (only categories relevant to the project
   type). Assigns a confidence score based on how much of the input was
   real vs. flagged-as-assumption from the retrieval dialogue.

5. **Report Agent**
   Assembles the memo: decision, range, top drivers, top risks/assumptions,
   citations.

### 3b. Model assignment (Vultr Serverless Inference catalog)

Pricing is per 1mm tokens (input / output). Cost is negligible at hackathon
scale — pick models for capability match to the task, not price.

| Agent | Model | Why |
|---|---|---|
| Planner/Orchestrator | **moonshotai/Kimi-K2.6** (primary), **MiniMaxAI/MiniMax-M2.7** (explicit fallback) | ⚠️ CONFIRMED via live API test: `kimi-k2-instruct` does NOT exist in Vultr's catalog and silently rerouted to MiniMax — this alias must never be used. Both Kimi-K2.6 and MiniMax-M2.7 are confirmed via explicit tool-call test to support function calling (Vultr's own docs claiming "only kimi-k2-instruct" is outdated). Planner triggers the Modeling Tool call, so it must use one of these two real, tested IDs — never the dead alias |
| Internal Retrieval Agent | **VultronRetrieverCore-Qwen3.5-4.5B** ($0.10 / $0.50) | Vultr's own retrieval-tuned model — matches "grounds decisions in documents" requirement directly |
| Benchmark Retrieval Agent | **VultronRetrieverCore-Qwen3.5-4.5B** ($0.10 / $0.50) | Same model, consistent retrieval quality across both sides of the dialogue |
| Explainability Agent | **nemotron-3-ultra-550b-a55b** (NVIDIA build.nvidia.com free inference catalog — separate from Vultr) | Largest available Nemotron variant, tagged "agent" on NVIDIA's catalog — this is the one output a judge reads closely, so a genuine capability upgrade shows up here more than anywhere else in the pipeline. No tool-calling needed here, so not restricted to kimi-k2 |
| Report Agent | **Nemotron-3-Nano-Omni** or **MiniMax-M2.7** ($0.30 / $1.20, Vultr) | Mostly assembly/formatting of already-computed content — no tool calling needed, cheapest reliable option |

**Confirmed Vultr Serverless Inference API details:**
- Endpoint: `https://api.vultrinference.com/v1/chat/completions` (note: different base URL from the main Vultr account API — this is inference-specific)
- Auth: `Authorization: Bearer ${INFERENCE_API_KEY}` — the key from your specific inference instance page, NOT the account-level API key
- Request shape is OpenAI-compatible (`model`, `messages`, `max_tokens`), so the same `OpenAI` Python client pattern used for NVIDIA works here too — just swap `base_url`
- Tool calling: define `"tools"` param, set `"tool_choice"` to `"auto"`/`"required"`/`"none"` — but ONLY works with `model: "kimi-k2-instruct"` as of now

**Important — this is a deliberate two-provider setup, not scope creep:**
Vultr Serverless Inference remains the entire core stack — orchestration,
retrieval, Planner, Report Agent, and the tool-calling to the Modeling Tool
all stay on Vultr. Only the Explainability Agent calls out to NVIDIA's own
free inference catalog (build.nvidia.com) for a larger Nemotron model.
This means:
- A second API integration (separate auth/endpoint from Vultr) — but since
  both are OpenAI-SDK compatible, this is a low-cost swap (same client
  class, different `base_url`/key), not a heavy lift
- NVIDIA's catalog is a **free tier** — no visibility into rate limits
  under load, so **have a fallback**: if it's flaky during demo rehearsal,
  fall back to a Vultr model for Explainability (e.g. GLM-5.2-fp8) rather
  than risk a live failure
- Test both versions side-by-side before the final demo and pick whichever
  is reliably available, not just whichever tests best once

**Critical thing confirmed in Hour 1 (done):** `moonshotai/Kimi-K2.6` reliably
triggers tool calling on Vultr, verified via explicit test with matching
requested/reported model name. `MiniMaxAI/MiniMax-M2.7` also works and is
kept as an explicit, code-level fallback — never a silent one. Smoke test
now hard-fails if reported model ≠ requested, to catch any future alias
drift immediately instead of silently.

**Do not use:** the string `kimi-k2-instruct` anywhere in code — it is not
a real catalog ID and silently reroutes to MiniMax-M2.7. Always use the
full real catalog IDs (`moonshotai/Kimi-K2.6`, `MiniMaxAI/MiniMax-M2.7`,
etc.) as confirmed via `GET /v1/models` against the live API.

---

### 3c. Confirmed integration pattern (NVIDIA)

NVIDIA's build.nvidia.com endpoint is OpenAI-SDK compatible — same `OpenAI`
client class as any OpenAI-compatible provider, just a different
`base_url` and key. Confirm whether Vultr Serverless Inference is also
OpenAI-compatible (likely) so both providers can share the same client
pattern in code, instantiated twice.

```python
import os
from openai import OpenAI

nvidia_client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ["NVIDIA_API_KEY"],  # never hardcode
)

# Used for the Explainability Agent specifically —
# reasoning_budget + enable_thinking are worth spending here since
# this is the one output a judge reads closely
completion = nvidia_client.chat.completions.create(
    model="nvidia/nemotron-3-ultra-550b-a55b",
    messages=[{"role": "user", "content": "..."}],
    temperature=1,
    top_p=0.95,
    max_tokens=16384,
    extra_body={
        "chat_template_kwargs": {"enable_thinking": True},
        "reasoning_budget": 16384,
    },
    stream=True,  # stream into the live agent-trace UI for the demo
)
for chunk in completion:
    if not chunk.choices:
        continue
    reasoning = getattr(chunk.choices[0].delta, "reasoning_content", None)
    if reasoning:
        print(reasoning, end="")
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="")
```

Vultr client instantiation follows the same shape once its base_url/key
are confirmed — both keys read from `.env`, never committed.

---

## 4. ROI Framework (Slalom's 8 categories — apply only relevant ones per project)

1. Cost impact
2. Revenue impact
3. Quality impact
4. Technology impact
5. Speed to value
6. Security impact
7. Process impact
8. Business differentiator

## 5. Data

### A. Benchmark corpus (real, cited — not synthetic)
Curated facts per project category, sourced from published surveys, each
tagged with source for citation:

- McKinsey Global AI Survey — e.g. 5.8x avg ROI within 14 months of production
- NVIDIA State of AI Report 2026 — industry-specific adoption/ROI (financial
  services, retail, healthcare, telecom, manufacturing)
- Deloitte State of AI in the Enterprise — 66% report productivity gains;
  revenue growth still aspirational for most (74% hoping vs 20% achieving)
- Sector payback timelines — finance ~8mo, manufacturing ~12-14mo (agentic systems)
- Customer service specific — chatbots resolving ~68% of Tier-1 tickets
- HTEC framework — true op cost often 3-5x initial build estimate; ROI
  formula = (Total Business Value − Total Cost) / Total Cost, cost includes
  build + inference at scale + integration + model-update cycles

**Honesty note for the pitch:** this is real published data, manually
curated and cited — not an independent rigorous dataset, and mostly
vendor/survey-sourced. State this explicitly; it's a feature (grounded in
real citable numbers) not a hidden weakness.

### B. Synthetic company profiles (fabricated, for demo only)
2-3 fake companies per category, mixed formats (clean JSON + messy free text)
to also demo Retrieval Agent robustness to real-world messy input.

### 3 Hardcoded Project Categories (do not expand — scope discipline)
1. Marketing AI
2. Customer Support AI
3. Predictive Maintenance AI

---

## 6. Security Considerations

Even for a hackathon demo, say this explicitly in the pitch:

- Don't send raw uploaded company documents further than necessary; be able
  to state what Vultr's data retention/handling policy is for inference calls
- Customer data is not used to train/fine-tune anything
- Mention encryption-at-rest as a stated design principle, even if not fully
  implemented in the demo build
- This is a credibility signal — most hackathon teams skip it entirely

---

## 7. Build Order (~20-22 hrs, 2 people)

1. **Hours 0-3:** Benchmark corpus (real, cited) + 3 category schemas + synthetic company profiles
2. **Hours 3-8:** Modeling Tool (deterministic, build/test first — everything depends on it) + FastAPI scaffold. Verify function-calling on chosen model(s) here.
3. **Hours 8-14:** Agent loop — Planner → Retrieval dialogue (Internal ⇄ Benchmark) → Modeling call → Explainability, wired to Vultr inference
4. **Hours 14-18:** Frontend — input flow + live agent trace view + memo output
5. **Hours 18-22:** Polish, rehearse demo 2x, cut anything flaky

---

## 8. Guardrails / Things Not To Deviate On

- No more than 3 project categories
- No more than 6 total agent components (5 agents + 1 tool) — scenario
  branching (§3a) is an extension of the Planner and Modeling Tool, not a
  new component; do not add a 7th agent for this
- LLM never computes the final ROI number — tool call only
- Demo must show the agent trace live, not hide it behind a spinner —
  this is the main defense against looking like "a dashboard" (a disqualified category)
- Output is a memo/document, not a dashboard, per hackathon rules
- Don't chase "many industries, many formats" generality — 3 categories, done well, beats broad and shallow
- No NVIDIA/Crusoe prize chase — Vultr track only, stay focused