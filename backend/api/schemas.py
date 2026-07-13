"""Request validation for inline company profiles.

Inline ``company`` JSON on /api/run is untrusted input that flows into LLM
prompts and float() casts. These models gate it *before* any provider call:
numeric fields must exist and be sane, and free-text fields are length-capped
to shrink the prompt-injection surface. Extra fields are allowed so a full
profile passes through untouched.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

_TEXT_CAP = 2000


class _Project(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field("AI Project", max_length=200)
    initial_build_cost_usd: float = Field(..., gt=0, lt=1e10)
    annual_inference_budget_usd_claimed: float = Field(..., ge=0, lt=1e10)


class _CompanyBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    company_name: str = Field("Company", max_length=200)
    project_category: str = Field(..., max_length=100)
    project_description: str = Field("", max_length=_TEXT_CAP)
    notes: str = Field("", max_length=_TEXT_CAP)


class _CustomerSupportOps(BaseModel):
    model_config = ConfigDict(extra="allow")

    annual_ticket_volume: float = Field(..., gt=0, lt=1e9)
    cost_per_ticket_usd: float = Field(..., gt=0, lt=1e6)
    tier1_ticket_share: float = Field(..., gt=0, le=1)


class CustomerSupportProfile(_CompanyBase):
    current_operations: _CustomerSupportOps
    proposed_project: _Project

    @model_validator(mode="after")
    def _check_deflection(self) -> CustomerSupportProfile:
        extra = self.proposed_project.model_extra or {}
        claimed = extra.get("claimed_deflection_rate_all_tickets") or extra.get(
            "claimed_tier1_deflection_rate"
        )
        if claimed is None:
            raise ValueError(
                "proposed_project must include claimed_deflection_rate_all_tickets "
                "or claimed_tier1_deflection_rate"
            )
        if not 0 < float(claimed) <= 1:
            raise ValueError("claimed deflection rate must be in (0, 1]")
        return self


class _MarketingOps(BaseModel):
    model_config = ConfigDict(extra="allow")

    monthly_ad_spend_usd: float = Field(..., ge=0, lt=1e9)
    current_conversion_rate: float = Field(..., gt=0, lt=1)
    average_order_value_usd: float = Field(..., gt=0, lt=1e6)


class _MarketingProject(_Project):
    claimed_conversion_lift_rate: float = Field(..., gt=0, le=2)


class MarketingProfile(_CompanyBase):
    current_operations: _MarketingOps
    proposed_project: _MarketingProject


class _MaintenanceOps(BaseModel):
    model_config = ConfigDict(extra="allow")

    current_annual_maintenance_spend_usd: float = Field(..., gt=0, lt=1e10)
    annual_downtime_cost_usd: float = Field(..., ge=0, lt=1e10)


class _MaintenanceProject(_Project):
    claimed_maintenance_spend_reduction_rate: float = Field(..., gt=0, le=1)


class MaintenanceProfile(_CompanyBase):
    current_operations: _MaintenanceOps
    proposed_project: _MaintenanceProject


_PROFILE_MODELS: dict[str, type[BaseModel]] = {
    "customer_support": CustomerSupportProfile,
    "marketing": MarketingProfile,
    "maintenance": MaintenanceProfile,
}


def validate_company_profile(category_key: str, company: dict[str, Any]) -> dict[str, Any]:
    """Validate an inline company profile for *category_key*.

    Raises pydantic.ValidationError (or KeyError for unknown categories).
    Returns the original dict unchanged on success — validation gates, it does
    not transform.
    """
    model = _PROFILE_MODELS.get(category_key)
    if model is None:
        raise KeyError(f"Unknown category: {category_key}")
    model.model_validate(company)
    return company
