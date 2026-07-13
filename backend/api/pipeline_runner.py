"""Instrumented pipeline runner — same stages as run_category.py, with event emission."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.retrieval import run_retrieval_dialogue
from api.events import EventEmitter, NullEmitter
from api.explain_stream import explain_branch_streaming
from api.memo_json import (
    _generate_recommendation_structured,
    build_memo_json,
    build_recommendation_payload,
)
from pipeline.run_category import (
    CATEGORIES,
    _call_modeling_direct,
    _extract_claims_generic,
    _load_json,
)


def run_pipeline(
    category_key: str,
    company: dict[str, Any],
    emitter: EventEmitter | None = None,
) -> dict[str, Any]:
    """Run full pipeline and return structured memo JSON."""
    events = emitter or NullEmitter()
    cfg = CATEGORIES[category_key]
    benchmarks = _load_json(cfg["benchmarks"])

    branch_field = cfg["branch_field"]
    branches = [
        {
            "branch_id": f"A_{cfg['branch_options'][0]}",
            "label": cfg["branch_labels"][0],
            branch_field: cfg["branch_options"][0],
        },
        {
            "branch_id": f"B_{cfg['branch_options'][1]}",
            "label": cfg["branch_labels"][1],
            branch_field: cfg["branch_options"][1],
        },
    ]
    plan = {
        "category": company["project_category"],
        "roi_dimensions": cfg["roi_dimensions"],
        "missing_fields": list(company.get("unknown_fields", {}).keys()),
        "clarifying_question": f"What is your {branch_field.replace('_', ' ')}?",
        "question_field": branch_field,
    }
    branch_plan = {
        "branching": True,
        "branch_field": branch_field,
        "branches": branches,
    }

    events.emit(
        "planner_started",
        {"category_key": category_key, "company_id": company.get("company_id")},
    )
    events.emit(
        "planner_result",
        {
            "plan": plan,
            "branch_plan": branch_plan,
            "note": "Deterministic branch construction (run_category path)",
        },
    )

    branch_results: list[dict[str, Any]] = []
    full_retrievals: list[dict[str, Any]] = []

    for branch in branches:
        branch_id = branch["branch_id"]
        branch_value = branch[branch_field]

        events.emit("retrieval_started", {"branch_id": branch_id, "label": branch.get("label")})
        retrieval = run_retrieval_dialogue(
            company=company,
            benchmarks=benchmarks,
            hosting_architecture=branch_value,
            branch_id=branch_id,
        )
        retrieval["reconciled_inputs"] = _extract_claims_generic(
            company, branch_value, category_key
        )
        full_retrievals.append(retrieval)

        for verdict in _verdicts_from_retrieval(retrieval):
            events.emit(
                "retrieval_claim",
                {
                    "branch_id": branch_id,
                    "claim": verdict.get("claim"),
                    "verdict": verdict.get("verdict"),
                    "reasoning": verdict.get("reasoning"),
                    "cited_fact_id": verdict.get("cited_fact_id"),
                },
            )

        events.emit(
            "retrieval_complete",
            {
                "branch_id": branch_id,
                "flagged_assumptions": retrieval.get("flagged_assumptions", []),
                "citations": retrieval.get("citations", []),
                "verdicts": _verdicts_from_retrieval(retrieval),
            },
        )

        events.emit("modeling_started", {"branch_id": branch_id})
        modeling_wrap = _call_modeling_direct(
            cfg, branch, retrieval["reconciled_inputs"], retrieval["flagged_assumptions"]
        )
        scenarios = modeling_wrap["result"].get("scenarios") or {}
        for scenario_name, scenario_data in scenarios.items():
            events.emit(
                "modeling_result",
                {
                    "branch_id": branch_id,
                    "scenario": scenario_name,
                    "roi": scenario_data.get("roi"),
                    "payback_months": scenario_data.get("payback_months"),
                    "annual_value_usd": scenario_data.get("annual_value_usd"),
                    "total_cost_3y_usd": scenario_data.get("total_cost_3y_usd"),
                },
            )

        events.emit("explainability_started", {"branch_id": branch_id})

        def _on_chunk(chunk: str, _bid: str = branch_id) -> None:
            events.emit("explainability_chunk", {"branch_id": _bid, "chunk": chunk})

        explanation = explain_branch_streaming(
            branch=branch,
            retrieval=retrieval,
            modeling=modeling_wrap["result"],
            roi_dimensions=cfg["roi_dimensions"],
            on_chunk=_on_chunk,
        )
        events.emit(
            "explainability_complete",
            {"branch_id": branch_id, "text_length": len(explanation)},
        )

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

    events.emit("recommendation_started", {})
    rec_payload, _, valid_overall = build_recommendation_payload(branch_results)
    recommendation = _generate_recommendation_structured(rec_payload, valid_overall)
    events.emit("recommendation_result", recommendation)

    memo = build_memo_json(
        category_key=category_key,
        company=company,
        plan=plan,
        branch_plan=branch_plan,
        branch_results=branch_results,
        full_retrievals=full_retrievals,
        recommendation=recommendation,
    )
    events.emit("memo_ready", memo)
    return memo


def _verdicts_from_retrieval(retrieval: dict[str, Any]) -> list[dict[str, Any]]:
    for turn in retrieval.get("transcript") or []:
        if turn.get("speaker") == "benchmark_retrieval":
            return turn.get("verdicts") or []
    return []


def write_memo_artifact(category_key: str, memo: dict[str, Any]) -> Path:
    """Optional: persist markdown-compatible output for CLI parity."""
    root = Path(__file__).resolve().parents[2]
    out_path = root / "backend" / "pipeline" / f"last_memo_{category_key}.txt"
    # Store recommendation text as a simple artifact when markdown not built
    text = memo.get("recommendation", {}).get("text", "")
    branches = memo.get("branches", [])
    lines = [
        f"MEMO: {memo.get('meta', {}).get('project_name', 'AI Project')}",
        "",
        json.dumps({"branches": len(branches), "recommendation": text}, indent=2),
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
