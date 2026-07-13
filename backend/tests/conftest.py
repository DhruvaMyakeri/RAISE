"""Shared fixtures: fake LLM completions and provider mocks.

All tests run fully offline — no provider network calls. Live model behavior
is covered separately by the eval suite (backend/evals/).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture()
def meridian_company() -> dict[str, Any]:
    return load_json(DATA / "companies" / "meridian_support.json")


@pytest.fixture()
def novavita_company() -> dict[str, Any]:
    return load_json(DATA / "companies" / "novavita_marketing.json")


@pytest.fixture()
def apex_company() -> dict[str, Any]:
    return load_json(DATA / "companies" / "apex_maintenance.json")


@pytest.fixture()
def cs_benchmarks() -> dict[str, Any]:
    return load_json(DATA / "benchmarks" / "customer_support_ai.json")


def make_tool_completion(name: str, arguments: dict[str, Any]) -> SimpleNamespace:
    """Build an object shaped like an OpenAI ChatCompletion with one tool call."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    tool_calls=[
                        SimpleNamespace(
                            function=SimpleNamespace(
                                name=name, arguments=json.dumps(arguments)
                            )
                        )
                    ],
                    content="",
                    reasoning=None,
                ),
                finish_reason="tool_calls",
            )
        ]
    )


def make_text_completion(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(tool_calls=None, content=text, reasoning=None),
                finish_reason="stop",
            )
        ]
    )


def fake_rerank(*, model: str, query: str, documents: list[str], top_n: int | None = None):
    """Deterministic stand-in for the Vultr rerank endpoint: identity order."""
    n = len(documents) if top_n is None else min(top_n, len(documents))
    return [
        {"index": i, "document": documents[i], "relevance_score": 1.0 - i * 0.01}
        for i in range(n)
    ]


VERDICTS_ONE_FLAGGED = [
    {
        "claim": "Optimistic benefit claim",
        "verdict": "flagged",
        "reasoning": "Claim exceeds the benchmark-realistic range.",
        "cited_fact_id": "none",
    },
    {
        "claim": "Operating budget",
        "verdict": "defensible",
        "reasoning": "Budget is within the typical operating band.",
        "cited_fact_id": "none",
    },
]


EXPLANATION_TEXT = (
    "Cost impact\n"
    "Driven by ticket volume and cost per ticket. Confidence: 80%.\n\n"
    "Quality impact\n"
    "Deflection quality is assumed, flagged upstream. Confidence: 60%.\n\n"
    "Speed to value\n"
    "Payback is fast but flagged by the sanity check. Confidence: 65%.\n\n"
    "Process impact\n"
    "Tier-1 routing changes are operational, not financial. Confidence: 70%.\n\n"
    "Technology impact\n"
    "Branch architecture is an unvalidated assumption. Confidence: 55%.\n\n"
    "Overall confidence: 72%.\n"
    '===DATA=== {"overall_confidence": 72, "dimensions": ['
    '{"name": "Cost impact", "confidence": 80}, {"name": "Quality impact", "confidence": 60}, '
    '{"name": "Speed to value", "confidence": 65}, {"name": "Process impact", "confidence": 70}, '
    '{"name": "Technology impact", "confidence": 55}]}'
)


RECOMMENDATION_ARGS = {
    "winner": "A",
    "reasoning": (
        "Scenario A delivers comparable value at a lower 3-year cost, and its flagged "
        "assumptions are identical to Scenario B's."
    ),
    "confidence_caveat": (
        "Both branches rest on an unvalidated benefit claim; validate it before committing."
    ),
}
