"""Single source of truth for extracting numeric claims from a company profile.

Both the retrieval stage (what the LLM validates) and the modeling stage (what
the deterministic tool computes with) consume the output of this function, so
they can never drift apart.
"""

from __future__ import annotations

from typing import Any

# claimed tier-1 deflection is capped at 95% — a 100%+ implied rate is
# arithmetically possible from claimed_overall / tier1_share but never real.
_MAX_TIER1_DEFLECTION = 0.95

CATEGORY_KEYS = ("customer_support", "marketing", "maintenance")


def extract_claims(
    company: dict[str, Any], branch_value: str, category_key: str
) -> dict[str, Any]:
    """Extract the reconciled numeric inputs for one scenario branch."""
    ops = company.get("current_operations", {})
    proj = company.get("proposed_project", {})

    if category_key == "customer_support":
        tier1_share = float(ops["tier1_ticket_share"])
        claimed_overall = float(
            proj.get(
                "claimed_deflection_rate_all_tickets",
                proj.get("claimed_tier1_deflection_rate", 0),
            )
        )
        claimed_tier1 = (
            min(claimed_overall / tier1_share, _MAX_TIER1_DEFLECTION)
            if tier1_share > 0
            else claimed_overall
        )
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

    if category_key == "marketing":
        return {
            "monthly_ad_spend_usd": float(ops["monthly_ad_spend_usd"]),
            "current_conversion_rate": float(ops["current_conversion_rate"]),
            "average_order_value_usd": float(ops["average_order_value_usd"]),
            "claimed_conversion_lift_rate": float(proj["claimed_conversion_lift_rate"]),
            "initial_build_cost_usd": float(proj["initial_build_cost_usd"]),
            "annual_inference_budget_usd": float(proj["annual_inference_budget_usd_claimed"]),
            "data_enrichment_strategy": branch_value,
        }

    if category_key == "maintenance":
        return {
            "current_annual_maintenance_spend_usd": float(
                ops["current_annual_maintenance_spend_usd"]
            ),
            "annual_downtime_cost_usd": float(ops["annual_downtime_cost_usd"]),
            "claimed_maintenance_spend_reduction_rate": float(
                proj["claimed_maintenance_spend_reduction_rate"]
            ),
            "initial_build_cost_usd": float(proj["initial_build_cost_usd"]),
            "annual_inference_budget_usd": float(proj["annual_inference_budget_usd_claimed"]),
            "hardware_deployment_method": branch_value,
        }

    raise ValueError(f"Unknown category: {category_key}")
