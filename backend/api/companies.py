"""Company profile registry for demo/API use."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
COMPANIES_DIR = ROOT / "data" / "companies"
BENCHMARKS_DIR = ROOT / "data" / "benchmarks"

# category_key ↔ benchmark corpus filename (matches run_category.py CATEGORIES)
CATEGORY_BENCHMARK_FILE: dict[str, str] = {
    "customer_support": "customer_support_ai.json",
    "marketing": "marketing_ai.json",
    "maintenance": "predictive_maintenance_ai.json",
}

# Demo company ↔ category mapping (matches run_category.py defaults)
COMPANY_REGISTRY: dict[str, dict[str, str]] = {
    "meridian-retail-support": {
        "category_key": "customer_support",
        "filename": "meridian_support.json",
    },
    "novavita-dtc-marketing": {
        "category_key": "marketing",
        "filename": "novavita_marketing.json",
    },
    "apex-valve-maintenance": {
        "category_key": "maintenance",
        "filename": "apex_maintenance.json",
    },
}

CATEGORY_DEFAULT_COMPANY: dict[str, str] = {
    "customer_support": "meridian-retail-support",
    "marketing": "novavita-dtc-marketing",
    "maintenance": "apex-valve-maintenance",
}


def load_company_profile(company_id: str) -> dict[str, Any]:
    entry = COMPANY_REGISTRY.get(company_id)
    if not entry:
        raise KeyError(f"Unknown company_id: {company_id}")
    path = COMPANIES_DIR / entry["filename"]
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_benchmark_corpus(category_key: str) -> dict[str, Any]:
    """Return the benchmark corpus JSON for a category exactly as stored."""
    filename = CATEGORY_BENCHMARK_FILE.get(category_key)
    if not filename:
        raise KeyError(f"Unknown category_key: {category_key}")
    path = BENCHMARKS_DIR / filename
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def list_companies() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for company_id, meta in COMPANY_REGISTRY.items():
        profile = load_company_profile(company_id)
        out.append(
            {
                "id": company_id,
                "name": profile.get("company_name", company_id),
                "category": profile.get("project_category", ""),
                "category_key": meta["category_key"],
            }
        )
    return out


def resolve_run_inputs(
    *,
    category: str | None,
    company_id: str | None,
    company: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """Return (category_key, company_profile) from API request fields."""
    if company is not None:
        profile = company
        if category:
            cat_key = category
        else:
            project_cat = profile.get("project_category", "")
            cat_key = _project_category_to_key(project_cat)
            if not cat_key:
                raise ValueError(
                    "When passing inline company JSON, provide category or a "
                    "recognized project_category value."
                )
        return cat_key, profile

    if company_id:
        if company_id not in COMPANY_REGISTRY:
            raise KeyError(f"Unknown company_id: {company_id}")
        meta = COMPANY_REGISTRY[company_id]
        cat_key = category or meta["category_key"]
        if cat_key != meta["category_key"]:
            raise ValueError(
                f"company_id {company_id} belongs to category {meta['category_key']}, "
                f"not {cat_key}"
            )
        return cat_key, load_company_profile(company_id)

    if category:
        default_id = CATEGORY_DEFAULT_COMPANY.get(category)
        if not default_id:
            raise ValueError(f"Unknown category: {category}")
        return category, load_company_profile(default_id)

    raise ValueError("Provide category, company_id, or company profile JSON.")


def _project_category_to_key(project_category: str) -> str | None:
    mapping = {
        "Customer Support AI": "customer_support",
        "Marketing AI": "marketing",
        "Predictive Maintenance AI": "maintenance",
    }
    return mapping.get(project_category)
