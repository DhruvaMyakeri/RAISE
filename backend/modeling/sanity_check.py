"""Output-level sanity check for Modeling Tool projections.

After computing ROI and payback, this module compares outputs against
benchmark-sourced realistic ranges. Violations produce NEW flagged
assumptions distinct from input-claim flags — they indicate the overall
projection exceeds defensible boundaries even after input clamping.

These flags signal that the cost estimate itself may be unrealistic
relative to the company's operational scale.
"""

from __future__ import annotations

from typing import Any

# Marketing AI: directly from corpus fact use_case_roi_content_drafting (~3.2x),
# which is the HIGHEST isolated marketing AI application ROI measured by McKinsey.
# The four use-case facts span 2.3x (ad copy) to 3.2x (content drafting).
# Any output above 3.2x exceeds the most optimistic published benchmark.
# Corpus citation: use_case_roi_content_drafting (McKinsey).
_MARKETING_ROI_CEILING = 3.2

# All categories: every benchmark source across both research passes
# shows realistic payback at 6+ months (sector_payback_manufacturing
# = 12-14mo, adopter_payback_distribution = "roughly one-quarter
# achieve return within the initial year"). Flag anything under 6 months.
# Corpus citations: sector_payback_manufacturing, sector_payback_finance,
# adopter_payback_distribution.
_MIN_REALISTIC_PAYBACK_MONTHS = 6.0

# Customer Support AI: directly from corpus fact mckinsey_roi_multiple —
# "organizations that put AI into production report an average ROI multiple
# of about 5.8x within roughly 14 months of go-live." This is the industry
# AVERAGE; outputs above it indicate the projection exceeds typical realized
# returns and likely relies on unvalidated optimistic inputs.
# Corpus citation: mckinsey_roi_multiple (McKinsey Global AI Survey).
_CS_ROI_CEILING = 5.8

# Predictive Maintenance AI: MODELING ASSUMPTION — no published PMAI
# ROI-multiple benchmark exists in the corpus. The 5.0x ceiling is derived
# from conservative reasoning about typical payback economics:
# - adopter_payback_distribution: 75% of organizations take >1 year to
#   achieve full return, implying modest early-year multiples
# - mid_market_savings_reality: 11-18% spend reduction limits the
#   value numerator relative to implementation costs
# - A 5.0x 3-year ROI implies ~2.7x annual value-to-cost ratio, which
#   is aggressive given the above constraints
# This ceiling is NOT benchmark-derived and should be treated as such.
_MAINTENANCE_ROI_CEILING = 5.0

_OUTPUT_FLAG_PREFIX = "output sanity check: "
_COST_UNDERSTATEMENT_NOTE = (
    "This suggests the implementation cost estimate may be understated "
    "relative to the company's operational scale — recommend validating "
    "the cost estimate before relying on this projection."
)


def check_outputs(
    category: str,
    scenarios: dict[str, dict[str, Any]],
) -> list[str]:
    """Return a list of output-level flagged assumptions.

    Called after scenario computation. Returns empty list if all outputs
    are within realistic ranges.
    """
    flags: list[str] = []
    likely = scenarios.get("likely", {})
    roi = likely.get("roi", 0)
    payback = likely.get("payback_months")

    # Category-specific ROI ceiling check
    roi_ceiling: float | None = None
    if category in ("Marketing AI", "marketing"):
        roi_ceiling = _MARKETING_ROI_CEILING
    elif category in ("Predictive Maintenance AI", "maintenance"):
        roi_ceiling = _MAINTENANCE_ROI_CEILING
    elif category in ("Customer Support AI", "customer_support"):
        roi_ceiling = _CS_ROI_CEILING

    if roi_ceiling is not None and roi > roi_ceiling:
        flags.append(
            f"{_OUTPUT_FLAG_PREFIX}Computed 3-year ROI ({roi:.1f}x) exceeds the "
            f"benchmark-realistic ceiling ({roi_ceiling:.1f}x) even after input-claim "
            f"clamping. {_COST_UNDERSTATEMENT_NOTE}"
        )

    # Universal payback floor check
    if payback is not None and payback < _MIN_REALISTIC_PAYBACK_MONTHS:
        flags.append(
            f"{_OUTPUT_FLAG_PREFIX}Computed payback ({payback:.1f} months) is below "
            f"the minimum realistic threshold ({_MIN_REALISTIC_PAYBACK_MONTHS:.0f} months) "
            f"established across all benchmark sources. {_COST_UNDERSTATEMENT_NOTE}"
        )

    return flags
