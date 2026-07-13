"""Customer Support AI modeling math, locked against hand-derived expected values.

Expected literals were derived independently from the documented HTEC formulas
and cost-share tables (see docstrings in modeling/roi.py and README), using the
Meridian demo profile numbers — not by running the implementation.
"""

from __future__ import annotations

import pytest

from modeling.roi import (
    ModelingInputs,
    compute_scenario,
    modeling_tool_from_args,
    run_modeling_tool,
)

MERIDIAN_ON_PREM = ModelingInputs(
    annual_ticket_volume=480_000,
    cost_per_ticket_usd=12.0,
    tier1_ticket_share=0.6,
    claimed_tier1_deflection_rate=0.8333,  # min(0.5 / 0.6, 0.95) rounded to 4dp
    initial_build_cost_usd=380_000,
    annual_inference_budget_usd=48_000,
    hosting_architecture="on_prem",
)

MERIDIAN_CLOUD = ModelingInputs(
    annual_ticket_volume=480_000,
    cost_per_ticket_usd=12.0,
    tier1_ticket_share=0.6,
    claimed_tier1_deflection_rate=0.8333,
    initial_build_cost_usd=380_000,
    annual_inference_budget_usd=48_000,
    hosting_architecture="cloud",
)


def test_likely_on_prem_exact_values():
    s = compute_scenario(MERIDIAN_ON_PREM, "likely")
    assert s.tickets_deflected_annual == 239_990.4
    assert s.annual_value_usd == 2_879_884.8
    assert s.year1_cost_usd == 623_000.0
    assert s.year2_cost_usd == 326_442.0
    assert s.total_cost_3y_usd == 1_292_206.1
    assert s.total_value_3y_usd == 8_639_654.4
    assert s.roi == 5.686
    assert s.payback_months == 1.7
    assert s.cost_breakdown["build_usd"] == 380_000.0
    assert s.cost_breakdown["inference_y1_usd"] == 26_400.0
    assert s.cost_breakdown["integration_y1_usd"] == 171_000.0
    assert s.cost_breakdown["model_update_y1_usd"] == 45_600.0


def test_conservative_on_prem_exact_values():
    s = compute_scenario(MERIDIAN_ON_PREM, "conservative")
    assert s.tickets_deflected_annual == pytest.approx(167_993.3, abs=0.1)
    assert s.annual_value_usd == pytest.approx(2_015_919.36, abs=0.01)
    assert s.roi == 3.6802
    assert s.payback_months == 2.6


def test_optimistic_deflection_clamped_at_95_percent():
    # 0.8333 * 1.15 = 0.9583 -> must clamp to 0.95
    s = compute_scenario(MERIDIAN_ON_PREM, "optimistic")
    assert s.tickets_deflected_annual == 273_600.0  # 480k * 0.6 * 0.95
    assert s.roi == 6.6223


def test_likely_cloud_exact_values():
    s = compute_scenario(MERIDIAN_CLOUD, "likely")
    assert s.year1_cost_usd == 585_400.0
    assert s.total_cost_3y_usd == 1_135_505.2
    assert s.roi == 6.6086
    assert s.payback_months == 1.7


def test_payback_none_when_costs_exceed_value():
    inputs = ModelingInputs(
        annual_ticket_volume=1_000,
        cost_per_ticket_usd=1.0,
        tier1_ticket_share=0.5,
        claimed_tier1_deflection_rate=0.5,
        initial_build_cost_usd=1_000_000,
        annual_inference_budget_usd=500_000,
        hosting_architecture="on_prem",
    )
    s = compute_scenario(inputs, "likely")
    assert s.payback_months is None


def test_zero_cost_guard_returns_zero_roi():
    inputs = ModelingInputs(
        annual_ticket_volume=0,
        cost_per_ticket_usd=0,
        tier1_ticket_share=0,
        claimed_tier1_deflection_rate=0,
        initial_build_cost_usd=0,
        annual_inference_budget_usd=0,
        hosting_architecture="on_prem",
    )
    s = compute_scenario(inputs, "likely")
    assert s.roi == 0.0
    assert s.payback_months is None


def test_run_modeling_tool_merges_input_and_output_flags():
    inputs = ModelingInputs(
        **{
            **MERIDIAN_ON_PREM.__dict__,
            "flagged_assumptions": ("assumption, not validated: demo flag",),
        }
    )
    out = run_modeling_tool(inputs, branch_id="A_on_prem")
    assert out.branch_id == "A_on_prem"
    assert set(out.scenarios) == {"conservative", "likely", "optimistic"}
    # Input flag preserved first, then output sanity flags appended.
    assert out.flagged_assumptions[0] == "assumption, not validated: demo flag"
    # Likely payback (1.7mo) is under the 6-month floor -> sanity flag must fire.
    assert any("output sanity check" in f for f in out.flagged_assumptions)
    assert any("payback" in f.lower() for f in out.flagged_assumptions)


def test_modeling_tool_from_args_round_trip():
    out = modeling_tool_from_args(
        {
            "branch_id": "B_cloud",
            "hosting_architecture": "cloud",
            "annual_ticket_volume": 480_000,
            "cost_per_ticket_usd": 12.0,
            "tier1_ticket_share": 0.6,
            "claimed_tier1_deflection_rate": 0.8333,
            "initial_build_cost_usd": 380_000,
            "annual_inference_budget_usd": 48_000,
            "flagged_assumptions": ["x"],
        }
    )
    assert out.scenarios["likely"]["roi"] == 6.6086
    assert out.flagged_assumptions[0] == "x"
