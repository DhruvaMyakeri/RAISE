"""Marketing AI Modeling Tool — ad personalization / conversion lift.

Value formula (HTEC framework, same structural pattern as CS):
  ROI = (Total Business Value − Total Cost) / Total Cost

Branch field: data_enrichment_strategy ("first_party_only" vs "third_party_enrichment")
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from modeling.roi import FinancialScenario, ModelingOutput, _Y2_INTEGRATION_SCALE, _Y2_MODEL_UPDATE_SCALE
from modeling.sanity_check import check_outputs

DataStrategyBranch = Literal["first_party_only", "third_party_enrichment"]

# Same scenario multipliers as CS — applied to claimed conversion lift rate.
_LIFT_MULT: dict[FinancialScenario, float] = {
    "conservative": 0.7,
    "likely": 1.0,
    "optimistic": 1.15,
}

# Realistic conversion lift ceiling from marketing_ai.json:
# integrated_workflow_performance shows 32% as the absolute max for deep integrations.
# realistic_marketing_roi_range shows 20-25% as the defensible long-term band.
# We clamp effective lift at 0.32 (the 32% deep-integration ceiling).
_MAX_CONVERSION_LIFT = 0.32

# MODELING ASSUMPTION (not a researched figure):
# Estimated average cost-per-click for DTC health/supplements across paid social + search.
# Used to derive implied monthly traffic from ad spend since the company profile does not
# provide traffic volume directly. This is an estimation layer, not company-provided data.
_ASSUMED_CPC_USD = 2.50


@dataclass(frozen=True)
class MarketingInputs:
    monthly_ad_spend_usd: float
    current_conversion_rate: float
    average_order_value_usd: float
    claimed_conversion_lift_rate: float
    initial_build_cost_usd: float
    annual_inference_budget_usd: float
    data_enrichment_strategy: DataStrategyBranch
    flagged_assumptions: tuple[str, ...] = ()


def _data_strategy_cost_profile(
    strategy: DataStrategyBranch, build: float, inference: float
) -> dict[str, float]:
    """Branch-dependent cost profile for Marketing AI.

    MODELING ASSUMPTIONS (not researched figures — author's estimates):
    - first_party_only: lower data/licensing costs (no third-party vendors), simpler
      integration (no API connectors to data brokers), but the same build cost.
      inference_y1 scaled at 0.70x (only internal data processing).
      integration at 20% of build (simpler pipeline, internal data only).
      model_update at 10% of build (less complex retraining).
    - third_party_enrichment: higher data processing + vendor licensing fees,
      more complex integration (data broker APIs, privacy compliance, data mapping).
      inference_y1 scaled at 1.60x (vendor data fees + higher processing volume).
      integration at 45% of build (API connectors, compliance, data mapping).
      model_update at 18% of build (more data sources = more retraining complexity).
    """
    if strategy == "first_party_only":
        return {
            "build": build,
            "inference_y1": inference * 0.70,
            "integration_y1": build * 0.20,
            "model_update_y1": build * 0.10,
        }
    # third_party_enrichment
    return {
        "build": build,
        "inference_y1": inference * 1.60,
        "integration_y1": build * 0.45,
        "model_update_y1": build * 0.18,
    }


def _effective_lift(claimed: float, scenario: FinancialScenario) -> float:
    """Apply scenario multiplier and clamp to realistic ceiling."""
    raw = claimed * _LIFT_MULT[scenario]
    return max(0.0, min(raw, _MAX_CONVERSION_LIFT))


def compute_marketing_scenario(
    inputs: MarketingInputs, scenario: FinancialScenario
) -> dict[str, Any]:
    profile = _data_strategy_cost_profile(
        inputs.data_enrichment_strategy,
        inputs.initial_build_cost_usd,
        inputs.annual_inference_budget_usd,
    )

    lift = _effective_lift(inputs.claimed_conversion_lift_rate, scenario)
    baseline_rate = inputs.current_conversion_rate
    new_rate = baseline_rate * (1.0 + lift)
    additional_rate = new_rate - baseline_rate

    # Implied monthly traffic from ad spend (MODELING ASSUMPTION: _ASSUMED_CPC_USD)
    monthly_traffic = inputs.monthly_ad_spend_usd / _ASSUMED_CPC_USD
    additional_conversions_monthly = additional_rate * monthly_traffic
    annual_value = additional_conversions_monthly * 12.0 * inputs.average_order_value_usd

    # Cost structure (same HTEC Y2+ pattern as CS)
    build = profile["build"]
    inference_y1 = profile["inference_y1"]
    integration_y1 = profile["integration_y1"]
    model_update_y1 = profile["model_update_y1"]
    year1_cost = build + inference_y1 + integration_y1 + model_update_y1

    # Y2+: third-party has higher inference growth (data vendor price increases)
    inf_growth = 1.12 if inputs.data_enrichment_strategy == "third_party_enrichment" else 1.05
    inference_y2 = inference_y1 * inf_growth
    integration_y2 = integration_y1 * _Y2_INTEGRATION_SCALE
    model_update_y2 = model_update_y1 * _Y2_MODEL_UPDATE_SCALE
    year2_cost = inference_y2 + integration_y2 + model_update_y2
    year3_cost = year2_cost * 1.05

    total_cost_3y = year1_cost + year2_cost + year3_cost
    total_value_3y = annual_value * 3.0

    roi = (total_value_3y - total_cost_3y) / total_cost_3y if total_cost_3y > 0 else 0.0

    monthly_value = annual_value / 12.0
    monthly_ongoing = (inference_y1 + integration_y1 + model_update_y1) / 12.0
    monthly_net = monthly_value - monthly_ongoing
    payback_months = build / monthly_net if monthly_net > 0 else None

    return {
        "scenario": scenario,
        "year1_cost_usd": round(year1_cost, 2),
        "year2_cost_usd": round(year2_cost, 2),
        "total_cost_3y_usd": round(total_cost_3y, 2),
        "annual_value_usd": round(annual_value, 2),
        "total_value_3y_usd": round(total_value_3y, 2),
        "roi": round(roi, 4),
        "payback_months": round(payback_months, 1) if payback_months is not None else None,
        "effective_conversion_lift": round(lift, 4),
        "additional_conversions_annual": round(additional_conversions_monthly * 12, 1),
        "cost_breakdown": {
            "build_usd": round(build, 2),
            "inference_y1_usd": round(inference_y1, 2),
            "integration_y1_usd": round(integration_y1, 2),
            "model_update_y1_usd": round(model_update_y1, 2),
            "inference_y2_usd": round(inference_y2, 2),
            "integration_y2_usd": round(integration_y2, 2),
            "model_update_y2_usd": round(model_update_y2, 2),
        },
    }


def run_marketing_modeling_tool(inputs: MarketingInputs, branch_id: str) -> ModelingOutput:
    scenarios = {
        s: compute_marketing_scenario(inputs, s)
        for s in ("conservative", "likely", "optimistic")
    }
    output_flags = check_outputs("marketing", scenarios)
    all_flags = list(inputs.flagged_assumptions) + output_flags
    return ModelingOutput(
        branch_id=branch_id,
        hosting_architecture=inputs.data_enrichment_strategy,
        inputs={
            "monthly_ad_spend_usd": inputs.monthly_ad_spend_usd,
            "current_conversion_rate": inputs.current_conversion_rate,
            "average_order_value_usd": inputs.average_order_value_usd,
            "claimed_conversion_lift_rate": inputs.claimed_conversion_lift_rate,
            "initial_build_cost_usd": inputs.initial_build_cost_usd,
            "annual_inference_budget_usd": inputs.annual_inference_budget_usd,
            "data_enrichment_strategy": inputs.data_enrichment_strategy,
            "assumed_cpc_usd": _ASSUMED_CPC_USD,
        },
        scenarios=scenarios,
        flagged_assumptions=all_flags,
    )


def marketing_modeling_from_args(args: dict[str, Any]) -> ModelingOutput:
    inputs = MarketingInputs(
        monthly_ad_spend_usd=float(args["monthly_ad_spend_usd"]),
        current_conversion_rate=float(args["current_conversion_rate"]),
        average_order_value_usd=float(args["average_order_value_usd"]),
        claimed_conversion_lift_rate=float(args["claimed_conversion_lift_rate"]),
        initial_build_cost_usd=float(args["initial_build_cost_usd"]),
        annual_inference_budget_usd=float(args["annual_inference_budget_usd"]),
        data_enrichment_strategy=args["data_enrichment_strategy"],
        flagged_assumptions=tuple(args.get("flagged_assumptions") or ()),
    )
    return run_marketing_modeling_tool(inputs, branch_id=str(args["branch_id"]))


MARKETING_MODELING_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "run_modeling_tool",
        "description": (
            "Deterministic ROI calculator for Marketing AI. Computes "
            "conservative/likely/optimistic scenarios for one data-strategy branch."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "branch_id": {"type": "string"},
                "data_enrichment_strategy": {
                    "type": "string",
                    "enum": ["first_party_only", "third_party_enrichment"],
                },
                "monthly_ad_spend_usd": {"type": "number"},
                "current_conversion_rate": {"type": "number"},
                "average_order_value_usd": {"type": "number"},
                "claimed_conversion_lift_rate": {"type": "number"},
                "initial_build_cost_usd": {"type": "number"},
                "annual_inference_budget_usd": {"type": "number"},
                "flagged_assumptions": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "branch_id",
                "data_enrichment_strategy",
                "monthly_ad_spend_usd",
                "current_conversion_rate",
                "average_order_value_usd",
                "claimed_conversion_lift_rate",
                "initial_build_cost_usd",
                "annual_inference_budget_usd",
            ],
        },
    },
}
