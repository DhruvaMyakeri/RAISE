"""End-to-end vertical slice: Customer Support AI only, terminal memo output.

Pipeline (project-plan §3a):
  Planner → (unknown → 2 branches) → per branch:
    Retrieval dialogue (Internal ⇄ Benchmark, max 1 pushback) →
    Modeling Tool (via Planner tool call) →
    Explainability
  → Report (Scenario A vs B side-by-side memo)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Windows consoles often default to cp1252; memo text may include unicode dashes.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from agents.explainability import explain_branch  # noqa: E402
from agents.planner import (  # noqa: E402
    branch_on_unknown,
    call_modeling_tool_via_planner,
    plan_and_clarify,
)
from agents.report import assemble_memo  # noqa: E402
from agents.retrieval import run_retrieval_dialogue  # noqa: E402

COMPANY_PATH = ROOT / "data" / "companies" / "meridian_support.json"
BENCHMARK_PATH = ROOT / "data" / "benchmarks" / "customer_support_ai.json"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _log(section: str, payload: object | None = None) -> None:
    print("\n" + "=" * 72)
    print(section)
    print("=" * 72)
    if payload is not None:
        if isinstance(payload, str):
            print(payload)
        else:
            print(json.dumps(payload, indent=2, default=str))


def run() -> str:
    company = _load_json(COMPANY_PATH)
    benchmarks = _load_json(BENCHMARK_PATH)

    _log("COMPANY PROFILE", company)

    # --- Stage 1: Planner — classify, missing data, clarifying question ---
    plan = plan_and_clarify(company)
    _log("PLANNER — plan + clarifying question", plan)

    question = plan.get("clarifying_question") or (
        "Is Meridian Assist hosted on-prem or in the cloud?"
    )
    # Simulated user answer: unknown (triggers scenario branching per §3a)
    user_answer = "unknown"
    _log(
        "USER ANSWER (simulated)",
        {"question": question, "answer": user_answer},
    )

    branch_plan = branch_on_unknown(plan, user_answer)
    _log("PLANNER — scenario branches (max 2)", branch_plan)

    branch_results: list[dict] = []

    for branch in branch_plan["branches"][:2]:
        branch_id = branch["branch_id"]
        hosting = branch["hosting_architecture"]
        _log(f"BRANCH START — {branch.get('label', branch_id)}")

        # --- Stage 2: Retrieval dialogue (once per branch) ---
        retrieval = run_retrieval_dialogue(
            company=company,
            benchmarks=benchmarks,
            hosting_architecture=hosting,
            branch_id=branch_id,
        )
        _log(f"RETRIEVAL DIALOGUE — {branch_id}", retrieval)

        # --- Stage 3: Modeling Tool via Planner tool call (once per branch) ---
        modeling_wrap = call_modeling_tool_via_planner(
            branch=branch,
            reconciled=retrieval["reconciled_inputs"],
            flagged_assumptions=retrieval["flagged_assumptions"],
        )
        _log(
            f"MODELING TOOL (Planner tool call) — {branch_id}",
            modeling_wrap,
        )

        # --- Stage 4: Explainability (once per branch) ---
        explanation = explain_branch(
            branch=branch,
            retrieval=retrieval,
            modeling=modeling_wrap["result"],
            roi_dimensions=plan.get("roi_dimensions") or [],
        )
        _log(f"EXPLAINABILITY — {branch_id}", explanation)

        branch_results.append(
            {
                "branch": branch,
                "retrieval": {
                    "reconciled_inputs": retrieval["reconciled_inputs"],
                    "flagged_assumptions": retrieval["flagged_assumptions"],
                    "citations": retrieval["citations"],
                },
                "modeling": modeling_wrap["result"],
                "explanation": explanation,
            }
        )

    # --- Stage 5: Report — one side-by-side memo ---
    memo = assemble_memo(
        company=company,
        plan=plan,
        branch_plan=branch_plan,
        branch_results=branch_results,
    )
    _log("FINAL MEMO — Scenario A vs Scenario B", memo)
    out_path = ROOT / "backend" / "pipeline" / "last_memo.txt"
    out_path.write_text(memo, encoding="utf-8")
    print(f"\nMemo also written to {out_path}")
    return memo


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"\nPIPELINE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
