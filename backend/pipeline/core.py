"""Unified pipeline core — the single implementation of the Vantage stage loop.

Every consumer (FastAPI SSE endpoint, synchronous API run, CLI) drives this
one function with a different EventEmitter. There is deliberately no other
copy of the stage sequence anywhere in the codebase.

Stages per run:
  1. Deterministic branch construction (2 scenario branches from category config)
  2. Per branch (parallel by default): retrieval + LLM claim validation ->
     deterministic modeling -> explainability (streamed)
  3. LLM recommendation comparing both branches
  4. Memo JSON assembly
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.explainability import explain_branch, parse_explanation
from agents.report import generate_recommendation
from agents.retrieval import run_retrieval_dialogue
from api.memo_json import build_memo_json
from modeling.roi import modeling_tool_from_args
from modeling.roi_maintenance import maintenance_modeling_from_args
from modeling.roi_marketing import marketing_modeling_from_args
from pipeline.claims import extract_claims
from pipeline.events import CancelToken, EventEmitter, NullEmitter

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]

CATEGORIES: dict[str, dict[str, Any]] = {
    "customer_support": {
        "company": ROOT / "data" / "companies" / "meridian_support.json",
        "benchmarks": ROOT / "data" / "benchmarks" / "customer_support_ai.json",
        "branch_field": "hosting_architecture",
        "branch_options": ["on_prem", "cloud"],
        "branch_labels": ["Scenario A — On-prem", "Scenario B — Cloud"],
        "modeling_fn": modeling_tool_from_args,
        "roi_dimensions": [
            "Cost impact", "Quality impact", "Speed to value",
            "Process impact", "Technology impact",
        ],
    },
    "marketing": {
        "company": ROOT / "data" / "companies" / "novavita_marketing.json",
        "benchmarks": ROOT / "data" / "benchmarks" / "marketing_ai.json",
        "branch_field": "data_enrichment_strategy",
        "branch_options": ["first_party_only", "third_party_enrichment"],
        "branch_labels": ["Scenario A — First-party only", "Scenario B — Third-party enrichment"],
        "modeling_fn": marketing_modeling_from_args,
        "roi_dimensions": [
            "Cost impact", "Revenue impact", "Speed to value",
            "Process impact", "Technology impact",
        ],
    },
    "maintenance": {
        "company": ROOT / "data" / "companies" / "apex_maintenance.json",
        "benchmarks": ROOT / "data" / "benchmarks" / "predictive_maintenance_ai.json",
        "branch_field": "hardware_deployment_method",
        "branch_options": ["retrofit", "new_install"],
        "branch_labels": ["Scenario A — Retrofit", "Scenario B — New install"],
        "modeling_fn": maintenance_modeling_from_args,
        "roi_dimensions": [
            "Cost impact", "Quality impact", "Speed to value",
            "Process impact", "Technology impact",
        ],
    },
}


@dataclass
class PipelineResult:
    memo: dict[str, Any]
    plan: dict[str, Any]
    branch_plan: dict[str, Any]
    branch_results: list[dict[str, Any]] = field(default_factory=list)
    company: dict[str, Any] = field(default_factory=dict)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_default_company(category_key: str) -> dict[str, Any]:
    return _load_json(CATEGORIES[category_key]["company"])


def _build_branches(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    branch_field = cfg["branch_field"]
    return [
        {
            "branch_id": f"{letter}_{option}",
            "label": label,
            "branch_field": branch_field,
            branch_field: option,
        }
        for letter, option, label in zip(
            "AB", cfg["branch_options"][:2], cfg["branch_labels"][:2], strict=True
        )
    ]


def _run_branch(
    *,
    cfg: dict[str, Any],
    category_key: str,
    company: dict[str, Any],
    benchmarks: dict[str, Any],
    branch: dict[str, Any],
    events: EventEmitter,
    cancel: CancelToken,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run retrieval -> modeling -> explainability for one branch.

    Returns (branch_result, full_retrieval).
    """
    branch_id = branch["branch_id"]
    branch_field = branch["branch_field"]
    branch_value = branch[branch_field]

    # --- Stage 2: Retrieval + claim validation ---
    cancel.raise_if_cancelled()
    events.emit("retrieval_started", {"branch_id": branch_id, "label": branch.get("label")})
    claims = extract_claims(company, branch_value, category_key)
    retrieval = run_retrieval_dialogue(
        company=company,
        benchmarks=benchmarks,
        claims=claims,
        branch_field=branch_field,
        branch_value=branch_value,
        branch_id=branch_id,
    )
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
            "flagged_assumptions": retrieval["flagged_assumptions"],
            "citations": retrieval["citations"],
            "verdicts": _verdicts_from_retrieval(retrieval),
        },
    )

    # --- Stage 3: Deterministic modeling ---
    cancel.raise_if_cancelled()
    events.emit("modeling_started", {"branch_id": branch_id})
    output = cfg["modeling_fn"](
        {
            "branch_id": branch_id,
            **claims,
            "flagged_assumptions": retrieval["flagged_assumptions"],
        }
    )
    modeling = {
        "branch_id": output.branch_id,
        "branch_field": branch_field,
        "branch_value": output.branch_value,
        "inputs": output.inputs,
        "scenarios": output.scenarios,
        "flagged_assumptions": output.flagged_assumptions,
    }
    for scenario_name, scenario_data in modeling["scenarios"].items():
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

    # --- Stage 4: Explainability (streamed; data tail withheld from stream) ---
    cancel.raise_if_cancelled()
    events.emit("explainability_started", {"branch_id": branch_id})

    def _on_chunk(chunk: str, _bid: str = branch_id) -> None:
        events.emit("explainability_chunk", {"branch_id": _bid, "chunk": chunk})

    raw_explanation = explain_branch(
        branch=branch,
        retrieval=retrieval,
        modeling=modeling,
        roi_dimensions=cfg["roi_dimensions"],
        on_chunk=_on_chunk,
    )
    parsed = parse_explanation(raw_explanation)
    events.emit(
        "explainability_complete",
        {
            "branch_id": branch_id,
            "text_length": len(parsed["text"]),
            "overall_confidence": parsed["overall_confidence"],
        },
    )

    branch_result = {
        "branch": branch,
        "retrieval": {
            "reconciled_inputs": retrieval["reconciled_inputs"],
            "flagged_assumptions": retrieval["flagged_assumptions"],
            "citations": retrieval["citations"],
        },
        "modeling": modeling,
        "explanation": parsed["text"],
        "explanation_parsed": parsed,
    }
    return branch_result, retrieval


def run(
    category_key: str,
    company: dict[str, Any],
    emitter: EventEmitter | None = None,
    cancel: CancelToken | None = None,
    parallel: bool = True,
) -> PipelineResult:
    """Run the full pipeline; returns memo plus intermediate context."""
    events = emitter or NullEmitter()
    cancel = cancel or CancelToken()
    cfg = CATEGORIES[category_key]
    benchmarks = _load_json(cfg["benchmarks"])

    # --- Stage 1: Deterministic branch construction ---
    branch_field = cfg["branch_field"]
    branches = _build_branches(cfg)
    plan = {
        "category": company["project_category"],
        "roi_dimensions": cfg["roi_dimensions"],
        "missing_fields": list(company.get("unknown_fields", {}).keys()),
        "clarifying_question": f"What is your {branch_field.replace('_', ' ')}?",
        "question_field": branch_field,
    }
    branch_plan = {"branching": True, "branch_field": branch_field, "branches": branches}

    events.emit(
        "planner_started",
        {"category_key": category_key, "company_id": company.get("company_id")},
    )
    events.emit(
        "planner_result",
        {
            "plan": plan,
            "branch_plan": branch_plan,
            "note": "Deterministic branch construction",
        },
    )

    def _branch_task(branch: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        return _run_branch(
            cfg=cfg,
            category_key=category_key,
            company=company,
            benchmarks=benchmarks,
            branch=branch,
            events=events,
            cancel=cancel,
        )

    if parallel:
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="branch") as pool:
            pairs = list(pool.map(_branch_task, branches))
    else:
        pairs = [_branch_task(b) for b in branches]

    branch_results = [p[0] for p in pairs]
    full_retrievals = [p[1] for p in pairs]

    # --- Stage 5: Recommendation + memo ---
    cancel.raise_if_cancelled()
    events.emit("recommendation_started", {})
    recommendation = generate_recommendation(branch_results)
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
    return PipelineResult(
        memo=memo,
        plan=plan,
        branch_plan=branch_plan,
        branch_results=branch_results,
        company=company,
    )


def run_pipeline(
    category_key: str,
    company: dict[str, Any],
    emitter: EventEmitter | None = None,
    cancel: CancelToken | None = None,
    parallel: bool = True,
) -> dict[str, Any]:
    """Run the full pipeline and return the structured memo JSON."""
    return run(category_key, company, emitter=emitter, cancel=cancel, parallel=parallel).memo


def _verdicts_from_retrieval(retrieval: dict[str, Any]) -> list[dict[str, Any]]:
    for turn in retrieval.get("transcript") or []:
        if turn.get("speaker") == "benchmark_retrieval":
            return turn.get("verdicts") or []
    return []
