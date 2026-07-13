"""Output-level sanity check thresholds (modeling/sanity_check.py)."""

from __future__ import annotations

from modeling.sanity_check import check_outputs


def _scenarios(roi: float, payback: float | None) -> dict:
    return {"likely": {"roi": roi, "payback_months": payback}}


def test_no_flags_when_within_bounds():
    assert check_outputs("customer_support", _scenarios(3.0, 12.0)) == []


def test_cs_roi_ceiling_5_8():
    assert check_outputs("customer_support", _scenarios(5.8, 12.0)) == []
    flags = check_outputs("customer_support", _scenarios(5.9, 12.0))
    assert len(flags) == 1 and "5.8x" in flags[0]


def test_marketing_roi_ceiling_3_2():
    assert check_outputs("marketing", _scenarios(3.2, 12.0)) == []
    flags = check_outputs("marketing", _scenarios(3.3, 12.0))
    assert len(flags) == 1 and "3.2x" in flags[0]


def test_maintenance_roi_ceiling_5_0():
    assert check_outputs("maintenance", _scenarios(5.0, 12.0)) == []
    flags = check_outputs("maintenance", _scenarios(5.1, 12.0))
    assert len(flags) == 1 and "5.0x" in flags[0]


def test_category_display_names_also_match():
    assert check_outputs("Marketing AI", _scenarios(3.3, 12.0))
    assert check_outputs("Customer Support AI", _scenarios(5.9, 12.0))
    assert check_outputs("Predictive Maintenance AI", _scenarios(5.1, 12.0))


def test_payback_floor_6_months():
    assert check_outputs("customer_support", _scenarios(2.0, 6.0)) == []
    flags = check_outputs("customer_support", _scenarios(2.0, 5.9))
    assert len(flags) == 1 and "payback" in flags[0].lower()


def test_none_payback_does_not_flag():
    assert check_outputs("customer_support", _scenarios(2.0, None)) == []


def test_both_violations_produce_two_flags():
    flags = check_outputs("marketing", _scenarios(9.9, 1.0))
    assert len(flags) == 2
    assert all(f.startswith("output sanity check:") for f in flags)
