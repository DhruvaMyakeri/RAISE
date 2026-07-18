"""Shared helpers for the eval suite: case records, scoring, mock providers.

Evals score *real model behavior* (probabilistic) — they are deliberately
separate from backend/tests (deterministic, mocked, run in CI). Live runs
spend provider credits and are capped small; run them manually or nightly:

    python -m evals.run --live          # real providers
    python -m evals.run --mock          # free harness smoke (CI)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


@dataclass
class EvalCase:
    name: str
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResult:
    eval_name: str
    cases: list[EvalCase]

    @property
    def score(self) -> float:
        return sum(c.passed for c in self.cases) / len(self.cases) if self.cases else 0.0

    def summary(self) -> str:
        lines = [f"[{self.eval_name}] score {self.score:.0%} ({sum(c.passed for c in self.cases)}/{len(self.cases)})"]
        for c in self.cases:
            mark = "PASS" if c.passed else "FAIL"
            lines.append(f"  {mark}  {c.name}  {json.dumps(c.details, default=str)[:220]}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mock providers (harness smoke mode — verifies the evals themselves run)
# ---------------------------------------------------------------------------

def _tool_completion(name: str, arguments: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    tool_calls=[
                        SimpleNamespace(
                            function=SimpleNamespace(name=name, arguments=json.dumps(arguments))
                        )
                    ],
                    content="",
                    reasoning=None,
                ),
                finish_reason="tool_calls",
            )
        ]
    )


def install_mocks() -> None:
    """Patch provider seams with deterministic fakes (mirrors live behavior)."""
    import agents.explainability as explainability
    import agents.intake as intake_agent
    import agents.report as report
    import agents.retrieval as retrieval

    def fake_rerank(*, model, query, documents, top_n=None):
        n = len(documents) if top_n is None else min(top_n, len(documents))
        return [
            {"index": i, "document": documents[i], "relevance_score": 1.0 - i * 0.01}
            for i in range(n)
        ]

    def fake_chat_text(*, client=None, model, messages, max_tokens,
                       temperature=0.2, tools=None, tool_choice=None):
        names = [t["function"]["name"] for t in (tools or [])]
        if "validate_claims" in names:
            prompt = messages[-1]["content"].lower()
            if "deflection" in prompt:
                label = "Deflection rate"
            elif "conversion lift" in prompt:
                label = "Conversion lift"
            else:
                label = "Maintenance spend reduction"
            return _tool_completion(
                "validate_claims",
                {
                    "verdicts": [
                        {
                            "claim": label,
                            "verdict": "flagged",
                            "reasoning": f"{label} exceeds the benchmark-realistic range.",
                            "cited_fact_id": "none",
                        },
                        {
                            "claim": "Operating budget",
                            "verdict": "flagged",
                            "reasoning": "Budget is low relative to build cost.",
                            "cited_fact_id": "none",
                        },
                    ]
                },
            )
        if "emit_recommendation" in names:
            return _tool_completion(
                "emit_recommendation",
                {
                    "winner": "A",
                    "reasoning": (
                        "Scenario A delivers a 4.2x likely ROI on a $1.30M 3-year cost, "
                        "versus Scenario B's 5.1x on $1.15M, but both branches carry the "
                        "same flagged benefit-claim assumption, so the lower-variance "
                        "on-prem path is the safer commitment."
                    ),
                    "confidence_caveat": "Both branches rest on an unvalidated claim.",
                },
            )
        if "emit_profile" in names:
            prompt = messages[-1]["content"]
            if "Brightleaf" in prompt:
                return _tool_completion(
                    "emit_profile",
                    {"category": "marketing", "company_name": "Brightleaf DTC",
                     "monthly_ad_spend_usd": 120000, "current_conversion_rate": 0.018,
                     "average_order_value_usd": 95, "claimed_conversion_lift_rate": 0.35,
                     "initial_build_cost_usd": 160000,
                     "annual_inference_budget_usd_claimed": 7200},
                )
            return _tool_completion(
                "emit_profile",
                {"category": "customer_support", "company_name": "Acme Support Co",
                 "annual_ticket_volume": 200000, "cost_per_ticket_usd": 9.5,
                 "tier1_ticket_share": 0.55,
                 "claimed_deflection_rate_all_tickets": 0.40,
                 "initial_build_cost_usd": 250000},
            )
        raise AssertionError(f"unexpected tools: {names}")

    def fake_stream(*, model, messages, max_tokens, reasoning_budget, on_chunk=None):
        dims = [
            "Cost impact", "Quality impact", "Revenue impact",
            "Speed to value", "Process impact", "Technology impact",
        ]
        prose = "\n\n".join(f"{d}\nDriven by company inputs. Confidence: 80%." for d in dims)
        tail = json.dumps(
            {"overall_confidence": 72,
             "dimensions": [{"name": d, "confidence": 80} for d in dims]}
        )
        text = f"{prose}\n\nOverall confidence: 72%.\n===DATA=== {tail}"
        if on_chunk:
            on_chunk(text)
        return text

    retrieval.rerank = fake_rerank
    retrieval.chat_text = fake_chat_text
    retrieval.vultr_client = lambda: None
    report.chat_text = fake_chat_text
    report.vultr_client = lambda: None
    intake_agent.chat_text = fake_chat_text
    intake_agent.vultr_client = lambda: None
    explainability._stream_with_callback = fake_stream
