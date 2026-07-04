"""Predictive Maintenance AI Modeling Tool — asset monitoring / spend reduction.

Value formula (HTEC framework, same structural pattern as CS):
  ROI = (Total Business Value − Total Cost) / Total Cost

Branch field: hardware_deployment_method ("retrofit" vs "new_install")
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from modeling.roi import FinancialScenario, ModelingOutput, _Y2_INTEGRATION_SCALE, _Y2_MODEL_UPDATE_SCALE
from modeling.sanity_check import check_outputs

HardwareBranch = Literal["retrofit", "new_install"]

# Same scenario multipliers — applied to claimed maintenance spend reduction rate.
_REDUCTION_MULT: dict[FinancialScenario, float] = {
    "conservative": 0.7,
    "likely": 1.0,
    "optimistic": 1.15,
}

# Realistic ceiling from predictive_maintenance_ai.json mid_market_realistic_target_range:
# total spend reduction: 11-18%. Clamp at 0.18 to prevent unchecked 35% passthrough.
_MAX_SPEND_REDUCTION = 0.18

# Downtime reduction on critical assets: 30-40% from the same benchmark fact.
# This is a SEPARATE metric from maintenance spend reduction — don't conflate.
# Apply the scenario multiplier to this as well, clamped at the upper bound.
_DOWNTIME_REDUCTION_BASE: dict[FinancialScenario, float] = {
    "conservative": 0.30,
    "likely": 0.35,
    "optimistic": 0.40,
}


@dataclass(frozen=True)
class MaintenanceInputs:
    current_annual_maintenance_spend_usd: float
    annual_downtime_cost_usd: float
    claimed_maintenance_spend_reduction_rate: float
    initial_build_cost_usd: float
    annual_inference_budget_usd: float
    hardware_deployment_method: HardwareBranch
    flagged_assumptions: tuple[str, ...] = ()


def _hardware_deployment_cost_profile(
    method: HardwareBranch, build: float, inference: float
) -> dict[str, float]:
    """Branch-dependent cost profile for Predictive Maintenance AI.

    MODELING ASSUMPTIONS (not researched figures — author's estimates):
    - retrofit: cheaper upfront integration (reuse existing telemetry boards,
      bolt-on adapters), but higher ongoing calibration cost due to sensor
      drift on legacy hardware. Also slightly less reliable data quality.
      inference_y1 scaled at 0.80x (fewer sensors, less data volume).
      integration at 30% of build (adapter work, custom wiring).
      model_update at 22% of build (frequent recalibration needed).
    - new_install: more expensive upfront (full sensor suite + native smart nodes),
      but more reliable data and lower ongoing calibration.
      inference_y1 scaled at 1.30x (more sensors, higher data volume).
      integration at 55% of build (full hardware + software setup).
      model_update at 10% of build (stable, less calibration).
    """
    if method == "retrofit":
        return {
            "build": build,
            "inference_y1": inference * 0.80,
            "integration_y1": build * 0.30,
            "model_update_y1": build * 0.22,
        }
    # new_install
    return {
        "build": build,
        "inference_y1": inference * 1.30,
        "integration_y1": build * 0.55,
        "model_update_y1": build * 0.10,
    }


def _effective_spend_reduction(claimed: float, scenario: FinancialScenario) -> float:
    """Apply scenario multiplier and clamp to realistic mid-market ceiling."""
    raw = claimed * _REDUCTION_MULT[scenario]
    return max(0.0, min(raw, _MAX_SPEND_REDUCTION))


def compute_maintenance_scenario(
    inputs: MaintenanceInputs, scenario: FinancialScenario
) -> dict[str, Any]:
    profile = _hardware_deployment_cost_profile(
        inputs.hardware_deployment_method,
        inputs.initial_build_cost_usd,
        inputs.annual_inference_budget_usd,
    )

    spend_reduction = _effective_spend_reduction(
        inputs.claimed_maintenance_spend_reduction_rate, scenario
    )
    maintenance_savings = inputs.current_annual_maintenance_spend_usd * spend_reduction

    # Avoided downtime: separate metric from spend reduction (benchmark: 30-40%)
    downtime_reduction = _DOWNTIME_REDUCTION_BASE[scenario]
    avoided_downtime_value = inputs.annual_downtime_cost_usd * downtime_reduction

    annual_value = maintenance_savings + avoided_downtime_value

    # Cost structure (same HTEC Y2+ pattern)
    build = profile["build"]
    inference_y1 = profile["inference_y1"]
    integration_y1 = profile["integration_y1"]
    model_update_y1 = profile["model_update_y1"]
    year1_cost = build + inference_y1 + integration_y1 + model_update_y1

    # Y2+: new_install has lower growth (stable hardware), retrofit has higher
    inf_growth = 1.04 if inputs.hardware_deployment_method == "new_install" else 1.10
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
        "effective_spend_reduction": round(spend_reduction, 4),
        "maintenance_savings_annual": round(maintenance_savings, 2),
        "avoided_downtime_value_annual": round(avoided_downtime_value, 2),
        "downtime_reduction_applied": round(downtime_reduction, 4),
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


def run_maintenance_modeling_tool(inputs: MaintenanceInputs, branch_id: str) -> ModelingOutput:
    scenarios = {
        s: compute_maintenance_scenario(inputs, s)
        for s in ("conservative", "likely", "optimistic")
    }
    output_flags = check_outputs("maintenance", scenarios)
    all_flags = list(inputs.flagged_assumptions) + output_flags
    return ModelingOutput(
        branch_id=branch_id,
        hosting_architecture=inputs.hardware_deployment_method,
        inputs={
            "current_annual_maintenance_spend_usd": inputs.current_annual_maintenance_spend_usd,
            "annual_downtime_cost_usd": inputs.annual_downtime_cost_usd,
            "claimed_maintenance_spend_reduction_rate": inputs.claimed_maintenance_spend_reduction_rate,
            "initial_build_cost_usd": inputs.initial_build_cost_usd,
            "annual_inference_budget_usd": inputs.annual_inference_budget_usd,
            "hardware_deployment_method": inputs.hardware_deployment_method,
        },
        scenarios=scenarios,
        flagged_assumptions=all_flags,
    )


def maintenance_modeling_from_args(args: dict[str, Any]) -> ModelingOutput:
    inputs = MaintenanceInputs(
        current_annual_maintenance_spend_usd=float(args["current_annual_maintenance_spend_usd"]),
        annual_downtime_cost_usd=float(args["annual_downtime_cost_usd"]),
        claimed_maintenance_spend_reduction_rate=float(args["claimed_maintenance_spend_reduction_rate"]),
        initial_build_cost_usd=float(args["initial_build_cost_usd"]),
        annual_inference_budget_usd=float(args["annual_inference_budget_usd"]),
        hardware_deployment_method=args["hardware_deployment_method"],
        flagged_assumptions=tuple(args.get("flagged_assumptions") or ()),
    )
    return run_maintenance_modeling_tool(inputs, branch_id=str(args["branch_id"]))


MAINTENANCE_MODELING_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "run_modeling_tool",
        "description": (
            "Deterministic ROI calculator for Predictive Maintenance AI. Computes "
            "conservative/likely/optimistic scenarios for one hardware-deployment branch."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "branch_id": {"type": "string"},
                "hardware_deployment_method": {
                    "type": "string",
                    "enum": ["retrofit", "new_install"],
                },
                "current_annual_maintenance_spend_usd": {"type": "number"},
                "annual_downtime_cost_usd": {"type": "number"},
                "claimed_maintenance_spend_reduction_rate": {"type": "number"},
                "initial_build_cost_usd": {"type": "number"},
                "annual_inference_budget_usd": {"type": "number"},
                "flagged_assumptions": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "branch_id",
                "hardware_deployment_method",
                "current_annual_maintenance_spend_usd",
                "annual_downtime_cost_usd",
                "claimed_maintenance_spend_reduction_rate",
                "initial_build_cost_usd",
                "annual_inference_budget_usd",
            ],
        },
    },
}
