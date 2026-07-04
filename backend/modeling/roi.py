"""Deterministic ROI Modeling Tool (project-plan §3a stage 3).

LLMs never compute these numbers. HTEC framework:
  ROI = (Total Business Value − Total Cost) / Total Cost
  Total Cost = build + inference + integration + model-update cycles
  Integration + model-update costs scale non-linearly in year 2+ (not flat).
  True op cost is often 3–5x initial build (sanity band, not a hard override).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from modeling.sanity_check import check_outputs

FinancialScenario = Literal["conservative", "likely", "optimistic"]
HostingBranch = Literal["on_prem", "cloud"]


# Multipliers applied to claimed deflection for each financial scenario.
_DEFLECTION_MULT: dict[FinancialScenario, float] = {
    "conservative": 0.7,
    "likely": 1.0,
    "optimistic": 1.15,
}

# Year-2+ non-linear scale factors for integration + model-update (HTEC).
_Y2_INTEGRATION_SCALE = 1.35
_Y2_MODEL_UPDATE_SCALE = 1.5


@dataclass(frozen=True)
class ModelingInputs:
    """Reconciled inputs from the retrieval layer for one architecture branch."""

    annual_ticket_volume: float
    cost_per_ticket_usd: float
    tier1_ticket_share: float
    claimed_tier1_deflection_rate: float
    initial_build_cost_usd: float
    annual_inference_budget_usd: float
    hosting_architecture: HostingBranch
    # Flagged assumptions from retrieval dialogue (passed through, not used in math)
    flagged_assumptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioResult:
    scenario: FinancialScenario
    year1_cost_usd: float
    year2_cost_usd: float
    total_cost_3y_usd: float
    annual_value_usd: float
    total_value_3y_usd: float
    roi: float
    payback_months: float | None
    tickets_deflected_annual: float
    cost_breakdown: dict[str, float]


@dataclass(frozen=True)
class ModelingOutput:
    branch_id: str
    hosting_architecture: HostingBranch
    inputs: dict[str, Any]
    scenarios: dict[str, dict[str, Any]]
    flagged_assumptions: list[str]


def _hosting_cost_profile(hosting: HostingBranch, build: float, inference: float) -> dict[str, float]:
    """Branch-specific cost shares. On-prem: higher integration/capex, lower inference.
    Cloud: lower integration, higher ongoing inference.
    """
    if hosting == "on_prem":
        return {
            "build": build,
            "inference_y1": inference * 0.55,
            "integration_y1": build * 0.45,
            "model_update_y1": build * 0.12,
        }
    # cloud
    return {
        "build": build,
        "inference_y1": inference * 1.35,
        "integration_y1": build * 0.22,
        "model_update_y1": build * 0.15,
    }


def _scenario_deflection(claimed: float, scenario: FinancialScenario) -> float:
    rate = claimed * _DEFLECTION_MULT[scenario]
    return max(0.0, min(rate, 0.95))


def compute_scenario(inputs: ModelingInputs, scenario: FinancialScenario) -> ScenarioResult:
    profile = _hosting_cost_profile(
        inputs.hosting_architecture,
        inputs.initial_build_cost_usd,
        inputs.annual_inference_budget_usd,
    )

    deflection = _scenario_deflection(inputs.claimed_tier1_deflection_rate, scenario)
    tier1_tickets = inputs.annual_ticket_volume * inputs.tier1_ticket_share
    tickets_deflected = tier1_tickets * deflection
    annual_value = tickets_deflected * inputs.cost_per_ticket_usd

    # Year 1 costs (build is one-time in Y1)
    build = profile["build"]
    inference_y1 = profile["inference_y1"]
    integration_y1 = profile["integration_y1"]
    model_update_y1 = profile["model_update_y1"]
    year1_cost = build + inference_y1 + integration_y1 + model_update_y1

    # Year 2+ : no rebuild; integration + model-update scale non-linearly (HTEC)
    inference_y2 = inference_y1 * (1.08 if inputs.hosting_architecture == "cloud" else 1.03)
    integration_y2 = integration_y1 * _Y2_INTEGRATION_SCALE
    model_update_y2 = model_update_y1 * _Y2_MODEL_UPDATE_SCALE
    year2_cost = inference_y2 + integration_y2 + model_update_y2
    year3_cost = year2_cost * 1.05  # mild growth, still no rebuild

    total_cost_3y = year1_cost + year2_cost + year3_cost
    total_value_3y = annual_value * 3.0  # steady-state value from go-live (simplified)

    roi = (total_value_3y - total_cost_3y) / total_cost_3y if total_cost_3y > 0 else 0.0

    # Simple payback from monthly net (value/12 - ongoing monthly cost after build)
    monthly_value = annual_value / 12.0
    monthly_ongoing = (inference_y1 + integration_y1 + model_update_y1) / 12.0
    monthly_net = monthly_value - monthly_ongoing
    if monthly_net > 0:
        payback_months = build / monthly_net
    else:
        payback_months = None

    return ScenarioResult(
        scenario=scenario,
        year1_cost_usd=round(year1_cost, 2),
        year2_cost_usd=round(year2_cost, 2),
        total_cost_3y_usd=round(total_cost_3y, 2),
        annual_value_usd=round(annual_value, 2),
        total_value_3y_usd=round(total_value_3y, 2),
        roi=round(roi, 4),
        payback_months=round(payback_months, 1) if payback_months is not None else None,
        tickets_deflected_annual=round(tickets_deflected, 1),
        cost_breakdown={
            "build_usd": round(build, 2),
            "inference_y1_usd": round(inference_y1, 2),
            "integration_y1_usd": round(integration_y1, 2),
            "model_update_y1_usd": round(model_update_y1, 2),
            "inference_y2_usd": round(inference_y2, 2),
            "integration_y2_usd": round(integration_y2, 2),
            "model_update_y2_usd": round(model_update_y2, 2),
        },
    )


def run_modeling_tool(inputs: ModelingInputs, branch_id: str) -> ModelingOutput:
    """Public tool entrypoint — called once per architecture branch."""
    scenarios = {
        s: asdict(compute_scenario(inputs, s))
        for s in ("conservative", "likely", "optimistic")
    }
    output_flags = check_outputs("customer_support", scenarios)
    all_flags = list(inputs.flagged_assumptions) + output_flags
    return ModelingOutput(
        branch_id=branch_id,
        hosting_architecture=inputs.hosting_architecture,
        inputs={
            "annual_ticket_volume": inputs.annual_ticket_volume,
            "cost_per_ticket_usd": inputs.cost_per_ticket_usd,
            "tier1_ticket_share": inputs.tier1_ticket_share,
            "claimed_tier1_deflection_rate": inputs.claimed_tier1_deflection_rate,
            "initial_build_cost_usd": inputs.initial_build_cost_usd,
            "annual_inference_budget_usd": inputs.annual_inference_budget_usd,
            "hosting_architecture": inputs.hosting_architecture,
        },
        scenarios=scenarios,
        flagged_assumptions=all_flags,
    )


# OpenAI-style tool schema for Planner function-calling (Modeling Tool).
MODELING_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "run_modeling_tool",
        "description": (
            "Deterministic ROI calculator. Computes conservative/likely/optimistic "
            "financial scenarios for one architecture branch. LLMs must not do this math."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "branch_id": {
                    "type": "string",
                    "description": "Scenario branch tag, e.g. 'A_on_prem' or 'B_cloud'.",
                },
                "hosting_architecture": {
                    "type": "string",
                    "enum": ["on_prem", "cloud"],
                },
                "annual_ticket_volume": {"type": "number"},
                "cost_per_ticket_usd": {"type": "number"},
                "tier1_ticket_share": {"type": "number"},
                "claimed_tier1_deflection_rate": {"type": "number"},
                "initial_build_cost_usd": {"type": "number"},
                "annual_inference_budget_usd": {"type": "number"},
                "flagged_assumptions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "branch_id",
                "hosting_architecture",
                "annual_ticket_volume",
                "cost_per_ticket_usd",
                "tier1_ticket_share",
                "claimed_tier1_deflection_rate",
                "initial_build_cost_usd",
                "annual_inference_budget_usd",
            ],
        },
    },
}


def modeling_tool_from_args(args: dict[str, Any]) -> ModelingOutput:
    """Execute Modeling Tool from a Planner tool-call argument payload."""
    inputs = ModelingInputs(
        annual_ticket_volume=float(args["annual_ticket_volume"]),
        cost_per_ticket_usd=float(args["cost_per_ticket_usd"]),
        tier1_ticket_share=float(args["tier1_ticket_share"]),
        claimed_tier1_deflection_rate=float(args["claimed_tier1_deflection_rate"]),
        initial_build_cost_usd=float(args["initial_build_cost_usd"]),
        annual_inference_budget_usd=float(args["annual_inference_budget_usd"]),
        hosting_architecture=args["hosting_architecture"],
        flagged_assumptions=tuple(args.get("flagged_assumptions") or ()),
    )
    return run_modeling_tool(inputs, branch_id=str(args["branch_id"]))
