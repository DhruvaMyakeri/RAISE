"""Field specifications for custom company intake.

Single source of truth consumed by three things:
- GET /api/intake/fields (the frontend renders the intake form from this)
- the LLM extraction tool schema in agents/intake.py
- construction of a pipeline-ready profile from submitted form values

Field names deliberately match the demo-profile JSON schema so the same
validation (api/schemas.py) and pipeline path handle demo and custom runs.
"""

from __future__ import annotations

from typing import Any

# section: where the field lives in the profile JSON.
# kind: "number" | "rate" (0-1 fraction) | "text"
INTAKE_FIELDS: dict[str, dict[str, Any]] = {
    "customer_support": {
        "label": "Customer Support AI",
        "branch_field": "hosting_architecture",
        "branch_question": "Hosting architecture (on-prem vs cloud) — Vantage models both scenarios",
        "fields": [
            {"name": "company_name", "section": "root", "kind": "text",
             "label": "Company name", "required": True},
            {"name": "industry", "section": "root", "kind": "text",
             "label": "Industry", "required": False},
            {"name": "project_description", "section": "root", "kind": "text",
             "label": "Project description", "required": False},
            {"name": "annual_ticket_volume", "section": "current_operations", "kind": "number",
             "label": "Annual ticket volume", "required": True, "unit": "tickets/yr"},
            {"name": "cost_per_ticket_usd", "section": "current_operations", "kind": "number",
             "label": "Cost per ticket", "required": True, "unit": "USD"},
            {"name": "tier1_ticket_share", "section": "current_operations", "kind": "rate",
             "label": "Tier-1 ticket share", "required": True, "unit": "0-1"},
            {"name": "claimed_deflection_rate_all_tickets", "section": "proposed_project",
             "kind": "rate", "label": "Claimed deflection rate (all tickets)",
             "required": True, "unit": "0-1"},
            {"name": "initial_build_cost_usd", "section": "proposed_project", "kind": "number",
             "label": "Initial build cost", "required": True, "unit": "USD"},
            {"name": "annual_inference_budget_usd_claimed", "section": "proposed_project",
             "kind": "number", "label": "Annual inference budget (claimed)",
             "required": True, "unit": "USD"},
        ],
    },
    "marketing": {
        "label": "Marketing AI",
        "branch_field": "data_enrichment_strategy",
        "branch_question": "Data enrichment strategy (first-party vs third-party) — Vantage models both scenarios",
        "fields": [
            {"name": "company_name", "section": "root", "kind": "text",
             "label": "Company name", "required": True},
            {"name": "industry", "section": "root", "kind": "text",
             "label": "Industry", "required": False},
            {"name": "project_description", "section": "root", "kind": "text",
             "label": "Project description", "required": False},
            {"name": "monthly_ad_spend_usd", "section": "current_operations", "kind": "number",
             "label": "Monthly ad spend", "required": True, "unit": "USD"},
            {"name": "current_conversion_rate", "section": "current_operations", "kind": "rate",
             "label": "Current conversion rate", "required": True, "unit": "0-1"},
            {"name": "average_order_value_usd", "section": "current_operations", "kind": "number",
             "label": "Average order value", "required": True, "unit": "USD"},
            {"name": "claimed_conversion_lift_rate", "section": "proposed_project", "kind": "rate",
             "label": "Claimed conversion lift", "required": True, "unit": "0-1"},
            {"name": "initial_build_cost_usd", "section": "proposed_project", "kind": "number",
             "label": "Initial build cost", "required": True, "unit": "USD"},
            {"name": "annual_inference_budget_usd_claimed", "section": "proposed_project",
             "kind": "number", "label": "Annual inference budget (claimed)",
             "required": True, "unit": "USD"},
        ],
    },
    "maintenance": {
        "label": "Predictive Maintenance AI",
        "branch_field": "hardware_deployment_method",
        "branch_question": "Hardware deployment (retrofit vs new install) — Vantage models both scenarios",
        "fields": [
            {"name": "company_name", "section": "root", "kind": "text",
             "label": "Company name", "required": True},
            {"name": "industry", "section": "root", "kind": "text",
             "label": "Industry", "required": False},
            {"name": "project_description", "section": "root", "kind": "text",
             "label": "Project description", "required": False},
            {"name": "current_annual_maintenance_spend_usd", "section": "current_operations",
             "kind": "number", "label": "Annual maintenance spend", "required": True,
             "unit": "USD"},
            {"name": "annual_downtime_cost_usd", "section": "current_operations", "kind": "number",
             "label": "Annual unplanned-downtime cost", "required": True, "unit": "USD"},
            {"name": "claimed_maintenance_spend_reduction_rate", "section": "proposed_project",
             "kind": "rate", "label": "Claimed maintenance spend reduction",
             "required": True, "unit": "0-1"},
            {"name": "initial_build_cost_usd", "section": "proposed_project", "kind": "number",
             "label": "Initial build cost", "required": True, "unit": "USD"},
            {"name": "annual_inference_budget_usd_claimed", "section": "proposed_project",
             "kind": "number", "label": "Annual inference budget (claimed)",
             "required": True, "unit": "USD"},
        ],
    },
}

_CATEGORY_DISPLAY = {
    "customer_support": "Customer Support AI",
    "marketing": "Marketing AI",
    "maintenance": "Predictive Maintenance AI",
}


def build_profile(category_key: str, values: dict[str, Any]) -> dict[str, Any]:
    """Assemble a pipeline-ready profile from flat intake values.

    Unknown/extra keys are ignored; missing keys are simply absent (schema
    validation in api/schemas.py decides whether that's acceptable).
    """
    spec = INTAKE_FIELDS[category_key]
    profile: dict[str, Any] = {
        "company_id": "custom",
        "project_category": _CATEGORY_DISPLAY[category_key],
        "current_operations": {},
        "proposed_project": {"name": "Custom AI Project"},
        # The branch decision is always modeled as unknown: Vantage's job is
        # to show both scenarios side by side.
        "unknown_fields": {spec["branch_field"]: "unknown"},
        "notes": "Custom profile entered via intake form.",
    }
    for field in spec["fields"]:
        val = values.get(field["name"])
        if val is None or val == "":
            continue
        if field["kind"] in ("number", "rate"):
            val = float(val)
        if field["section"] == "root":
            profile[field["name"]] = val
        else:
            profile[field["section"]][field["name"]] = val
    return profile
