"""Predictive Maintenance AI modeling math, locked against hand-derived values
(Apex demo profile; formulas per modeling/roi_maintenance.py docstrings)."""

from __future__ import annotations

from modeling.roi_maintenance import (
    MaintenanceInputs,
    compute_maintenance_scenario,
    run_maintenance_modeling_tool,
)

APEX_RETROFIT = MaintenanceInputs(
    current_annual_maintenance_spend_usd=1_850_000,
    annual_downtime_cost_usd=3_080_000,
    claimed_maintenance_spend_reduction_rate=0.35,
    initial_build_cost_usd=380_000,
    annual_inference_budget_usd=12_000,
    hardware_deployment_method="retrofit",
)


def test_likely_retrofit_exact_values():
    s = compute_maintenance_scenario(APEX_RETROFIT, "likely")
    # 35% claimed reduction must clamp to the 18% mid-market ceiling.
    assert s["effective_spend_reduction"] == 0.18
    assert s["maintenance_savings_annual"] == 333_000.0
    assert s["avoided_downtime_value_annual"] == 1_078_000.0  # 3.08M * 0.35
    assert s["annual_value_usd"] == 1_411_000.0
    assert s["year1_cost_usd"] == 587_200.0
    assert s["total_cost_3y_usd"] == 1_181_413.0
    assert s["roi"] == 2.583
    assert s["payback_months"] == 3.8


def test_conservative_uses_lower_downtime_reduction():
    s = compute_maintenance_scenario(APEX_RETROFIT, "conservative")
    # Even at 0.7x, 0.35 * 0.7 = 0.245 still clamps to 0.18.
    assert s["effective_spend_reduction"] == 0.18
    assert s["avoided_downtime_value_annual"] == 924_000.0  # 3.08M * 0.30
    assert s["roi"] == 2.1919
    assert s["payback_months"] == 4.3


def test_new_install_branch_profile_differs():
    ni = MaintenanceInputs(
        **{**APEX_RETROFIT.__dict__, "hardware_deployment_method": "new_install"}
    )
    s = compute_maintenance_scenario(ni, "likely")
    assert s["cost_breakdown"]["integration_y1_usd"] == 209_000.0  # 55% of build
    assert s["cost_breakdown"]["model_update_y1_usd"] == 38_000.0  # 10% of build


def test_payback_flag_fires_on_apex_likely():
    out = run_maintenance_modeling_tool(APEX_RETROFIT, branch_id="A_retrofit")
    # likely ROI 2.583 is under the 5.0 ceiling, but payback 3.8mo < 6mo floor
    assert not any("ceiling" in f for f in out.flagged_assumptions)
    assert any("payback" in f.lower() for f in out.flagged_assumptions)
