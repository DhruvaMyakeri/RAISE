"""Marketing AI modeling math, locked against hand-derived expected values
(Novavita demo profile; formulas per modeling/roi_marketing.py docstrings)."""

from __future__ import annotations

from modeling.roi_marketing import (
    MarketingInputs,
    compute_marketing_scenario,
    run_marketing_modeling_tool,
)

NOVAVITA_FIRST_PARTY = MarketingInputs(
    monthly_ad_spend_usd=150_000,
    current_conversion_rate=0.021,
    average_order_value_usd=120.0,
    claimed_conversion_lift_rate=0.45,
    initial_build_cost_usd=180_000,
    annual_inference_budget_usd=8_400,
    data_enrichment_strategy="first_party_only",
)


def test_likely_first_party_exact_values():
    s = compute_marketing_scenario(NOVAVITA_FIRST_PARTY, "likely")
    # 45% claimed lift must clamp to the 32% benchmark ceiling.
    assert s["effective_conversion_lift"] == 0.32
    assert s["additional_conversions_annual"] == 4_838.4
    assert s["annual_value_usd"] == 580_608.0
    assert s["year1_cost_usd"] == 239_880.0
    assert s["total_cost_3y_usd"] == 407_516.7
    assert s["roi"] == 3.2742
    assert s["payback_months"] == 4.1


def test_conservative_lift_below_ceiling_not_clamped():
    s = compute_marketing_scenario(NOVAVITA_FIRST_PARTY, "conservative")
    assert s["effective_conversion_lift"] == 0.315  # 0.45 * 0.7, under 0.32
    assert s["roi"] == 3.2075
    assert s["payback_months"] == 4.2


def test_third_party_branch_costs_higher():
    tp = MarketingInputs(
        **{**NOVAVITA_FIRST_PARTY.__dict__, "data_enrichment_strategy": "third_party_enrichment"}
    )
    s_fp = compute_marketing_scenario(NOVAVITA_FIRST_PARTY, "likely")
    s_tp = compute_marketing_scenario(tp, "likely")
    assert s_tp["total_cost_3y_usd"] > s_fp["total_cost_3y_usd"]
    assert s_tp["annual_value_usd"] == s_fp["annual_value_usd"]  # value model identical


def test_output_sanity_flags_fire_on_novavita_likely():
    out = run_marketing_modeling_tool(NOVAVITA_FIRST_PARTY, branch_id="A_first_party_only")
    flags = out.flagged_assumptions
    # likely ROI 3.2742 > 3.2 marketing ceiling AND payback 4.1 < 6mo floor
    assert any("ROI" in f and "ceiling" in f for f in flags)
    assert any("payback" in f.lower() for f in flags)


def test_zero_traffic_yields_zero_value_and_no_payback():
    z = MarketingInputs(
        **{**NOVAVITA_FIRST_PARTY.__dict__, "monthly_ad_spend_usd": 0.0}
    )
    s = compute_marketing_scenario(z, "likely")
    assert s["annual_value_usd"] == 0.0
    assert s["payback_months"] is None
