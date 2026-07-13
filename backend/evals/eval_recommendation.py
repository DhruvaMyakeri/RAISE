"""Eval: recommendation integrity — valid winner, and any confidence
percentage the model cites must match a real overall score (the validator
should already enforce this; the eval confirms it end-to-end on live output).
"""

from __future__ import annotations

from agents.report import _confidence_citations_valid, generate_recommendation

from ._common import EvalCase, EvalResult

_OVERALL = {"A": 72, "B": 58}


def _branch_result(letter: str, roi: float, cost: float, conf: int) -> dict:
    field = "hosting_architecture"
    value = "on_prem" if letter == "A" else "cloud"
    return {
        "branch": {
            "branch_id": f"{letter}_{value}",
            "label": f"Scenario {letter}",
            "branch_field": field,
            field: value,
        },
        "modeling": {
            "scenarios": {
                name: {
                    "roi": round(roi * mult, 4),
                    "payback_months": 8.0,
                    "annual_value_usd": 2_000_000 * mult,
                    "total_cost_3y_usd": cost,
                }
                for name, mult in (("conservative", 0.7), ("likely", 1.0), ("optimistic", 1.15))
            },
            "flagged_assumptions": [
                "assumption, not validated: benefit claim exceeds benchmark range",
                f"assumption, not validated: {field}={value} (user unknown; branch {letter})",
            ],
        },
        "retrieval": {"flagged_assumptions": []},
        "explanation_parsed": {"overall_confidence": conf, "dimensions": [], "text": ""},
    }


def run_eval(repeats: int = 2) -> EvalResult:
    branch_results = [
        _branch_result("A", roi=4.2, cost=1_300_000, conf=_OVERALL["A"]),
        _branch_result("B", roi=5.1, cost=1_150_000, conf=_OVERALL["B"]),
    ]
    cases: list[EvalCase] = []
    for i in range(repeats):
        rec = generate_recommendation(branch_results)
        winner_ok = rec.get("winner") in ("A", "B")
        conf_ok = _confidence_citations_valid(rec.get("text", ""), list(_OVERALL.values()))
        substantive = len(rec.get("reasoning", "")) > 80 and "unavailable" not in rec.get("text", "")
        cases.append(
            EvalCase(
                name=f"run {i + 1}: winner is A or B",
                passed=winner_ok,
                details={"winner": rec.get("winner")},
            )
        )
        cases.append(
            EvalCase(
                name=f"run {i + 1}: cited confidence matches real overall scores",
                passed=conf_ok,
                details={"text": rec.get("text", "")[:200]},
            )
        )
        cases.append(
            EvalCase(
                name=f"run {i + 1}: substantive reasoning (no fallback)",
                passed=substantive,
                details={"reasoning_len": len(rec.get("reasoning", ""))},
            )
        )
    return EvalResult("recommendation_integrity", cases)
