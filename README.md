# Vantage

**Grounded AI ROI Intelligence** — a multi-agent system that predicts and *explains* the ROI of a proposed AI project, grounding every number in either the company's own operating data or a real, cited industry benchmark, and explicitly flagging the assumptions that don't hold up.

> Built for the RAISE Summit Hackathon 2026 (Vultr track).

---

## Why

Enterprises spend heavily on AI but can rarely answer a simple question with confidence: *"How much will this project actually return if we build it?"* Only ~20% of organizations achieve the revenue growth they expect from AI (Deloitte), only ~6% are "high performers" who can attribute real bottom-line impact (McKinsey), and ~30% of GenAI projects are abandoned after proof-of-concept (Gartner).

Existing tools either measure ROI *after* deployment or are static pre-deployment calculators. **Vantage** is different: it's an agentic system that retrieves company data, cross-checks specific numeric claims against cited benchmarks with **visible reasoning**, and shows exactly which assumptions are unvalidated and why.

It's aimed at the analyst who has to build the business case for a mid-size enterprise with an existing operational baseline — not at replacing a consultancy, but at compressing the discovery-and-benchmarking stage from weeks to minutes, with the reasoning shown rather than hidden.

---

## How it works

Six stages — five LLM-driven agents plus one deterministic tool:

```
Company Profile
      │
      ▼
Planner ─ classify category, detect unknown fields, branch on uncertainty
      │
      ▼
Retrieval (per branch)
   Internal retrieval (rerank) → Benchmark retrieval (rerank)
      → LLM claim validation (judges each claim against benchmark evidence)
      │
      ▼
Modeling Tool ─ deterministic Python: HTEC ROI formula, 3 scenarios
   (conservative / likely / optimistic), non-linear Y2+ cost scaling,
   output-level sanity check
      │
      ▼
Explainability ─ breaks the projection down by Slalom ROI dimension,
   with a confidence score per dimension
      │
      ▼
Report ─ side-by-side "Scenario A vs Scenario B" memo + LLM-reasoned
   recommendation
```

**Hard rule:** LLMs never compute the final ROI number. All arithmetic runs in plain, auditable Python.

### Models

| Role | Model | Provider |
|---|---|---|
| Planner / claim validation | `moonshotai/Kimi-K2.6` (fallback `MiniMaxAI/MiniMax-M2.7`) | Vultr Serverless Inference |
| Retrieval (rerank) | `vultr/VultronRetrieverCore-Qwen3.5-4.5B` | Vultr Serverless Inference |
| Explainability | `nvidia/nemotron-3-ultra-550b-a55b` (fallback `zai-org/GLM-5.2-FP8`) | NVIDIA build.nvidia.com (fallback Vultr) |
| Report recommendation | `MiniMaxAI/MiniMax-M2.7` (fallback `Kimi-K2.6`) | Vultr Serverless Inference |
| ROI math | none — deterministic Python | — |

---

## Supported categories

| Category | Benchmark facts | Demo company (fabricated) | Core value driver |
|---|---|---|---|
| Customer Support AI | 9 cited | Meridian Retail Co. | Ticket deflection × cost/ticket |
| Marketing AI | 11 cited | Novavita Health Tech | Conversion lift × traffic × AOV |
| Predictive Maintenance AI | 10 cited | Apex Precision Components | Maintenance spend reduction + avoided downtime |

Each demo company carries exactly one **intentionally-optimistic claim** (to test whether validation catches it) and one **intentionally-unknown field** (to test scenario branching).

---

## What makes it trustworthy

- **Claim validation reasons over evidence, not thresholds.** In testing it caught a company extrapolating a Tier-1-only deflection benchmark (68%) across *all* ticket types — a logical error a hardcoded rule could never catch.
- **Hard citation guard.** Any benchmark fact ID an LLM cites that wasn't actually shown to it is rejected — hallucinated citations are structurally impossible, not just discouraged.
- **Output-level sanity check.** Separate from input validation: even when inputs are clamped to realistic ranges, an implausible final ROI/payback (e.g. from an understated cost estimate) gets flagged. Ceilings are corpus-cited where a benchmark exists and explicitly labeled as modeling assumptions where none does.
- **Paraphrased, cited corpus.** Every benchmark fact is paraphrased (never copied) from named sources — McKinsey, Deloitte, Gartner, NVIDIA, IoT Analytics, Persistence Market Research, Siemens/Aberdeen, HTEC. Raw research is archived in `data/benchmarks/_research_raw/` for provenance.
- **View source data.** A read-only transparency viewer in the UI lets you inspect the raw synthetic company profile and the full benchmark corpus (with source tiers and citation types) behind any run — and jump from a flagged assumption straight to the exact source and data field.

---

## Project structure

```
.
├── backend/
│   ├── main.py               # FastAPI app (API layer only — no pipeline logic)
│   ├── api/                  # thin wrappers: pipeline runner, SSE events, JSON memo, source data
│   ├── agents/               # planner, retrieval, explainability, report
│   ├── modeling/             # deterministic ROI math + output sanity check
│   ├── pipeline/             # CLI runners (run_category.py, run_slice.py)
│   ├── llm/                  # Vultr / NVIDIA clients, rerank
│   └── config/               # model names + per-agent token budgets
├── frontend/                 # Next.js 14 app (analyst-console UI)
│   ├── app/                  # pages, layout, global styles
│   ├── components/           # agent trace, memo charts, confidence panels, source-data modal
│   └── lib/                  # API client, types, SSE hook, formatters
├── data/
│   ├── companies/            # synthetic company profiles
│   └── benchmarks/           # cited benchmark corpora (+ _research_raw/)
└── docs/                     # ARCHITECTURE.md, project-plan.md, status
```

---

## Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- A **Vultr Serverless Inference** API key and an **NVIDIA build.nvidia.com** API key

### 1. Environment variables

Copy `.env.example` to `.env` in the repo root and fill in your keys:

```bash
cp .env.example .env
```

```
VULTR_API_KEY=your_vultr_serverless_inference_key_here
NVIDIA_API_KEY=your_nvidia_api_key_here
```

### 2. Backend

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

The API is now on `http://127.0.0.1:8001`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The frontend reads the backend base URL from `frontend/.env.local` (`NEXT_PUBLIC_API_BASE`, defaults to `http://127.0.0.1:8001`).

---

## Usage

### Web app
Pick one of the three demo companies, hit **Run live analysis**, and watch the agents work in real time — stage-by-stage trace, live claim verdicts (defensible / flagged), and token-by-token explainability. When the run completes you get a side-by-side scenario comparison (ROI ranges, payback, cost breakdown), a per-dimension confidence breakdown, and a **View source data** panel to verify every input.

### CLI (no frontend needed)
Run any category end-to-end and print the full memo to the terminal:

```bash
cd backend
python pipeline/run_category.py customer_support   # or: marketing | maintenance
```

Output is also written to `backend/pipeline/last_memo_<category>.txt`.

---

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/companies` | List the demo companies (id, name, category) |
| `POST` | `/api/run` | Run a category synchronously, return the full structured JSON memo |
| `GET` | `/api/run/stream` | Stream pipeline progress as Server-Sent Events (per-stage, per-branch) |
| `GET` | `/api/companies/{company_id}/source` | Raw company profile JSON (read-only transparency) |
| `GET` | `/api/benchmarks/{category_key}` | Full benchmark corpus JSON (read-only transparency) |
| `GET` | `/health` | Health check |

`POST /api/run` accepts `{ "category": "customer_support", "company_id": "meridian-retail-support" }` (or inline `company` JSON).

---

## Known limitations

- Benchmark data is real and cited but mostly **secondary citations** (an article citing the primary McKinsey/Gartner report, not the report itself).
- No adoption / change-management-probability modeling — costs and benefits assume successful deployment.
- Retrieval is a single LLM validation call reasoning over claims *and* benchmark evidence together, not two agents debating in turns.
- The NVIDIA free-tier Explainability endpoint rate-limits under load; a tested Vultr GLM fallback exists but produces lower-quality prose.
- Predictive Maintenance's ROI sanity-check ceiling (5.0x) is a modeling assumption, not a corpus-cited figure — no published ROI-multiple benchmark exists for that category in the researched set.
- Marketing and Predictive Maintenance branch deterministically; only Customer Support uses the Planner LLM for branch construction.

---

## Disclaimer

Vantage produces **grounded projections, not financial advice.** All company profiles included are **fabricated demo data** built to exercise the pipeline — not real companies. Benchmark figures are paraphrased from published sources and cited for reference.
