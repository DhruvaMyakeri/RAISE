"""Claim extraction from company profiles.

Written against the consolidated extractor; also asserts the exact values the
retrieval prompt and the modeling tool both consume, per category.
"""

from __future__ import annotations

import pytest

from pipeline.claims import extract_claims


def test_customer_support_claims(meridian_company):
    claims = extract_claims(meridian_company, "on_prem", "customer_support")
    assert claims["annual_ticket_volume"] == 480_000.0
    assert claims["cost_per_ticket_usd"] == 12.0
    assert claims["tier1_ticket_share"] == 0.6
    assert claims["claimed_overall_deflection_rate"] == 0.5
    # implied tier-1 = min(0.5 / 0.6, 0.95) rounded to 4dp
    assert claims["claimed_tier1_deflection_rate"] == 0.8333
    assert claims["initial_build_cost_usd"] == 380_000.0
    assert claims["annual_inference_budget_usd"] == 48_000.0
    assert claims["hosting_architecture"] == "on_prem"


def test_marketing_claims(novavita_company):
    claims = extract_claims(novavita_company, "first_party_only", "marketing")
    assert claims["monthly_ad_spend_usd"] == 150_000.0
    assert claims["current_conversion_rate"] == 0.021
    assert claims["average_order_value_usd"] == 120.0
    assert claims["claimed_conversion_lift_rate"] == 0.45
    assert claims["data_enrichment_strategy"] == "first_party_only"


def test_maintenance_claims(apex_company):
    claims = extract_claims(apex_company, "retrofit", "maintenance")
    assert claims["current_annual_maintenance_spend_usd"] == 1_850_000.0
    assert claims["annual_downtime_cost_usd"] == 3_080_000.0
    assert claims["claimed_maintenance_spend_reduction_rate"] == 0.35
    assert claims["hardware_deployment_method"] == "retrofit"


def test_tier1_implied_rate_clamped(meridian_company):
    company = dict(meridian_company)
    company["current_operations"] = {
        **company["current_operations"],
        "tier1_ticket_share": 0.4,  # 0.5 / 0.4 = 1.25 -> clamp 0.95
    }
    claims = extract_claims(company, "cloud", "customer_support")
    assert claims["claimed_tier1_deflection_rate"] == 0.95


def test_unknown_category_raises(meridian_company):
    with pytest.raises(ValueError):
        extract_claims(meridian_company, "on_prem", "nonsense")
