"""Eval: does the live explainability model honor the structured-output
contract (===DATA=== JSON tail, dimension coverage, confidence scores)?"""

from __future__ import annotations

from agents.explainability import DATA_MARKER, explain_branch, parse_explanation
from pipeline.claims import extract_claims
from pipeline.core import CATEGORIES, load_default_company

from ._common import EvalCase, EvalResult


def run_eval() -> EvalResult:
    cases: list[EvalCase] = []
    for category_key, cfg in CATEGORIES.items():
        company = load_default_company(category_key)
        branch_field = cfg["branch_field"]
        branch_value = cfg["branch_options"][0]
        branch = {
            "branch_id": f"A_{branch_value}",
            "label": cfg["branch_labels"][0],
            "branch_field": branch_field,
            branch_field: branch_value,
        }
        claims = extract_claims(company, branch_value, category_key)
        output = cfg["modeling_fn"](
            {
                "branch_id": branch["branch_id"],
                **claims,
                "flagged_assumptions": [
                    "assumption, not validated: benefit claim exceeds benchmark range",
                    f"assumption, not validated: {branch_field}={branch_value} "
                    f"(user unknown; branch {branch['branch_id']})",
                ],
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
        retrieval_stub = {
            "flagged_assumptions": output.flagged_assumptions,
            "transcript": [],
        }

        chunks: list[str] = []
        raw = explain_branch(
            branch=branch,
            retrieval=retrieval_stub,
            modeling=modeling,
            roi_dimensions=cfg["roi_dimensions"],
            on_chunk=chunks.append,
        )
        parsed = parse_explanation(raw)
        expected_dims = {d.lower() for d in cfg["roi_dimensions"]}
        got_dims = {d["name"].lower() for d in parsed["dimensions"]}
        coverage = len(expected_dims & got_dims) / len(expected_dims)
        scored = [d for d in parsed["dimensions"] if d.get("confidence") is not None]

        cases.append(
            EvalCase(
                name=f"{category_key}: data tail present & parsed",
                passed=DATA_MARKER in raw and parsed["overall_confidence"] is not None,
                details={"overall_confidence": parsed["overall_confidence"],
                         "raw_len": len(raw)},
            )
        )
        cases.append(
            EvalCase(
                name=f"{category_key}: dimension coverage >= 80%",
                passed=coverage >= 0.8,
                details={"coverage": round(coverage, 2), "got": sorted(got_dims)},
            )
        )
        cases.append(
            EvalCase(
                name=f"{category_key}: per-dimension confidences scored",
                passed=len(scored) >= max(1, int(0.8 * len(parsed["dimensions"] or [1]))),
                details={"n_scored": len(scored), "n_dims": len(parsed["dimensions"])},
            )
        )
        cases.append(
            EvalCase(
                name=f"{category_key}: tail not streamed to UI",
                passed=DATA_MARKER not in "".join(chunks),
                details={"n_chunks": len(chunks)},
            )
        )
    return EvalResult("explainability_format", cases)
