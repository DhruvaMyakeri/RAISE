"""Multi-category pipeline runner.

Runs any of the three supported categories end-to-end:
  python backend/pipeline/run_category.py [customer_support|marketing|maintenance]

Defaults to customer_support for backward compatibility.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from agents.explainability import explain_branch  # noqa: E402
from agents.report import assemble_memo  # noqa: E402
from agents.retrieval import run_retrieval_dialogue  # noqa: E402
from modeling.roi import MODELING_TOOL_SCHEMA, modeling_tool_from_args  # noqa: E402
from modeling.roi_maintenance import (  # noqa: E402
    MAINTENANCE_MODELING_TOOL_SCHEMA,
    maintenance_modeling_from_args,
)
from modeling.roi_marketing import (  # noqa: E402
    MARKETING_MODELING_TOOL_SCHEMA,
    marketing_modeling_from_args,
)

# Category configuration
CATEGORIES = {
    "customer_support": {
        "company": ROOT / "data" / "companies" / "meridian_support.json",
        "benchmarks": ROOT / "data" / "benchmarks" / "customer_support_ai.json",
        "branch_field": "hosting_architecture",
        "branch_options": ["on_prem", "cloud"],
        "branch_labels": ["Scenario A — On-prem", "Scenario B — Cloud"],
        "modeling_schema": MODELING_TOOL_SCHEMA,
        "modeling_fn": modeling_tool_from_args,
        "roi_dimensions": ["Cost impact", "Quality impact", "Speed to value", "Process impact", "Technology impact"],
    },
    "marketing": {
        "company": ROOT / "data" / "companies" / "novavita_marketing.json",
        "benchmarks": ROOT / "data" / "benchmarks" / "marketing_ai.json",
        "branch_field": "data_enrichment_strategy",
        "branch_options": ["first_party_only", "third_party_enrichment"],
        "branch_labels": ["Scenario A — First-party only", "Scenario B — Third-party enrichment"],
        "modeling_schema": MARKETING_MODELING_TOOL_SCHEMA,
        "modeling_fn": marketing_modeling_from_args,
        "roi_dimensions": ["Cost impact", "Revenue impact", "Speed to value", "Process impact", "Technology impact"],
    },
    "maintenance": {
        "company": ROOT / "data" / "companies" / "apex_maintenance.json",
        "benchmarks": ROOT / "data" / "benchmarks" / "predictive_maintenance_ai.json",
        "branch_field": "hardware_deployment_method",
        "branch_options": ["retrofit", "new_install"],
        "branch_labels": ["Scenario A — Retrofit", "Scenario B — New install"],
        "modeling_schema": MAINTENANCE_MODELING_TOOL_SCHEMA,
        "modeling_fn": maintenance_modeling_from_args,
        "roi_dimensions": ["Cost impact", "Quality impact", "Speed to value", "Process impact", "Technology impact"],
    },
}


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


def _extract_claims_generic(company: dict, branch_value: str, category: str) -> dict:
    """Category-aware claim extraction."""
    proj = company["proposed_project"]
    ops = company["current_operations"]

    if category == "customer_support":
        tier1_share = float(ops["tier1_ticket_share"])
        claimed_overall = float(proj.get("claimed_deflection_rate_all_tickets", proj.get("claimed_tier1_deflection_rate", 0)))
        claimed_tier1 = min(claimed_overall / tier1_share, 0.95) if tier1_share > 0 else claimed_overall
        return {
            "annual_ticket_volume": float(ops["annual_ticket_volume"]),
            "cost_per_ticket_usd": float(ops["cost_per_ticket_usd"]),
            "tier1_ticket_share": tier1_share,
            "claimed_overall_deflection_rate": claimed_overall,
            "claimed_tier1_deflection_rate": round(claimed_tier1, 4),
            "implied_overall_deflection_rate": claimed_overall,
            "initial_build_cost_usd": float(proj["initial_build_cost_usd"]),
            "annual_inference_budget_usd": float(proj["annual_inference_budget_usd_claimed"]),
            "hosting_architecture": branch_value,
        }
    elif category == "marketing":
        return {
            "monthly_ad_spend_usd": float(ops["monthly_ad_spend_usd"]),
            "current_conversion_rate": float(ops["current_conversion_rate"]),
            "average_order_value_usd": float(ops["average_order_value_usd"]),
            "claimed_conversion_lift_rate": float(proj["claimed_conversion_lift_rate"]),
            "initial_build_cost_usd": float(proj["initial_build_cost_usd"]),
            "annual_inference_budget_usd": float(proj["annual_inference_budget_usd_claimed"]),
            "data_enrichment_strategy": branch_value,
        }
    elif category == "maintenance":
        return {
            "current_annual_maintenance_spend_usd": float(ops["current_annual_maintenance_spend_usd"]),
            "annual_downtime_cost_usd": float(ops["annual_downtime_cost_usd"]),
            "claimed_maintenance_spend_reduction_rate": float(proj["claimed_maintenance_spend_reduction_rate"]),
            "initial_build_cost_usd": float(proj["initial_build_cost_usd"]),
            "annual_inference_budget_usd": float(proj["annual_inference_budget_usd_claimed"]),
            "hardware_deployment_method": branch_value,
        }
    raise ValueError(f"Unknown category: {category}")


def _call_modeling_direct(
    category_cfg: dict, branch: dict, reconciled: dict, flagged_assumptions: list[str]
) -> dict:
    """Call the modeling tool directly (bypassing the Planner LLM for new categories).

    For Customer Support AI we still use the Planner tool-call path via run_slice.py.
    For new categories we call the modeling function directly since the Planner doesn't
    have category-specific schemas hardcoded yet.
    """
    branch_field = [k for k in branch if k not in ("branch_id", "label")][0]
    args = {
        "branch_id": branch["branch_id"],
        branch_field: branch[branch_field],
        **reconciled,
        "flagged_assumptions": flagged_assumptions,
    }
    output = category_cfg["modeling_fn"](args)
    return {
        "tool_call": {
            "id": f"modeling-{branch['branch_id']}",
            "name": "run_modeling_tool",
            "arguments": args,
        },
        "result": {
            "branch_id": output.branch_id,
            "hosting_architecture": output.hosting_architecture,
            "inputs": output.inputs,
            "scenarios": output.scenarios,
            "flagged_assumptions": output.flagged_assumptions,
        },
    }


def run(category_key: str = "customer_support") -> str:
    cfg = CATEGORIES[category_key]
    company = _load_json(cfg["company"])
    benchmarks = _load_json(cfg["benchmarks"])

    _log("COMPANY PROFILE", company)

    # --- Stage 1: Build branches from config ---
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
    _log("PLAN + BRANCHES", {"plan": plan, "branches": branch_plan})

    branch_results: list[dict] = []

    for branch in branches:
        branch_id = branch["branch_id"]
        branch_value = branch[branch_field]
        _log(f"BRANCH START — {branch.get('label', branch_id)}")

        # --- Stage 2: Retrieval ---
        retrieval = run_retrieval_dialogue(
            company=company,
            benchmarks=benchmarks,
            hosting_architecture=branch_value,
            branch_id=branch_id,
        )
        # Override reconciled inputs with category-specific extraction
        retrieval["reconciled_inputs"] = _extract_claims_generic(
            company, branch_value, category_key
        )
        _log(f"RETRIEVAL DIALOGUE — {branch_id}", retrieval)

        # --- Stage 3: Modeling ---
        modeling_wrap = _call_modeling_direct(
            cfg, branch, retrieval["reconciled_inputs"], retrieval["flagged_assumptions"]
        )
        _log(f"MODELING TOOL — {branch_id}", modeling_wrap)

        # --- Stage 4: Explainability ---
        explanation = explain_branch(
            branch=branch,
            retrieval=retrieval,
            modeling=modeling_wrap["result"],
            roi_dimensions=cfg["roi_dimensions"],
        )
        _log(f"EXPLAINABILITY — {branch_id}", explanation)

        branch_results.append({
            "branch": branch,
            "retrieval": {
                "reconciled_inputs": retrieval["reconciled_inputs"],
                "flagged_assumptions": retrieval["flagged_assumptions"],
                "citations": retrieval["citations"],
            },
            "modeling": modeling_wrap["result"],
            "explanation": explanation,
        })

    # --- Stage 5: Report ---
    memo = assemble_memo(
        company=company,
        plan=plan,
        branch_plan=branch_plan,
        branch_results=branch_results,
    )
    _log("FINAL MEMO", memo)

    out_path = ROOT / "backend" / "pipeline" / f"last_memo_{category_key}.txt"
    out_path.write_text(memo, encoding="utf-8")
    print(f"\nMemo written to {out_path}")
    return memo


if __name__ == "__main__":
    cat = sys.argv[1] if len(sys.argv) > 1 else "customer_support"
    if cat not in CATEGORIES:
        print(f"Usage: python run_category.py [{' | '.join(CATEGORIES.keys())}]")
        sys.exit(1)
    try:
        run(cat)
    except Exception as exc:
        print(f"\nPIPELINE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
