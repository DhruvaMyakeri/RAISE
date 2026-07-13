"""Golden regression: full pipeline run with all providers mocked.

Locks the memo JSON structure and the deterministic numbers inside it for all
three categories, plus the SSE event sequence. If a refactor changes pipeline
behavior, this fails.
"""

from __future__ import annotations

import pytest
from conftest import (
    EXPLANATION_TEXT,
    RECOMMENDATION_ARGS,
    VERDICTS_ONE_FLAGGED,
    fake_rerank,
    make_tool_completion,
)

import pipeline.core as core
from pipeline.events import CallbackEmitter

EXPECTED_LIKELY_ROI = {
    # (category, branch index) -> likely 3y ROI from the demo profiles
    ("customer_support", 0): 5.686,   # on_prem
    ("customer_support", 1): 6.6086,  # cloud
    ("marketing", 0): 3.2742,         # first_party_only
    ("maintenance", 0): 2.583,        # retrofit
}


@pytest.fixture()
def mocked_providers(monkeypatch):
    """Patch every network seam in the pipeline."""

    def fake_chat_text(*, client=None, model, messages, max_tokens,
                       temperature=0.2, tools=None, tool_choice=None):
        names = [t["function"]["name"] for t in (tools or [])]
        if "validate_claims" in names:
            return make_tool_completion("validate_claims", {"verdicts": VERDICTS_ONE_FLAGGED})
        if "emit_recommendation" in names:
            return make_tool_completion("emit_recommendation", RECOMMENDATION_ARGS)
        raise AssertionError(f"unexpected chat_text call with tools={names}")

    def fake_stream(*, model, messages, max_tokens, reasoning_budget, on_chunk=None):
        if on_chunk:
            on_chunk(EXPLANATION_TEXT[:40])
            on_chunk(EXPLANATION_TEXT[40:])
        return EXPLANATION_TEXT

    monkeypatch.setattr("agents.retrieval.rerank", fake_rerank)
    monkeypatch.setattr("agents.retrieval.chat_text", fake_chat_text)
    monkeypatch.setattr("agents.retrieval.vultr_client", lambda: None)
    monkeypatch.setattr("agents.report.chat_text", fake_chat_text)
    monkeypatch.setattr("agents.report.vultr_client", lambda: None)
    monkeypatch.setattr("agents.explainability._stream_with_callback", fake_stream)
    return fake_chat_text


@pytest.mark.parametrize("category_key", ["customer_support", "marketing", "maintenance"])
def test_full_pipeline_memo_structure(mocked_providers, category_key):
    events: list[str] = []
    emitter = CallbackEmitter(lambda t, d: events.append(t))
    company = core.load_default_company(category_key)

    memo = core.run_pipeline(category_key, company, emitter=emitter)

    # --- meta / framing ---
    assert memo["meta"]["category_key"] == category_key
    assert memo["meta"]["company_name"]
    assert memo["decision_framing"]["summary"]

    # --- branches ---
    assert len(memo["branches"]) == 2
    for i, br in enumerate(memo["branches"]):
        assert br["label"] == ["Scenario A", "Scenario B"][i]
        metrics = br["metrics"]
        for row in ("roi_3yr", "payback_months", "annual_value_usd", "total_cost_3y_usd"):
            assert set(metrics[row]) == {"conservative", "likely", "optimistic"}
        expected = EXPECTED_LIKELY_ROI.get((category_key, i))
        if expected is not None:
            assert metrics["roi_3yr"]["likely"] == expected
        # flagged assumptions include the branch-unknown flag and parse into types
        types = {f["type"] for f in br["flagged_assumptions"]}
        assert "branch_unknown" in types
        # explainability parsed from the structured contract
        assert br["explainability"]["overall_confidence"] == 72
        assert len(br["explainability"]["dimensions"]) == 5
        # verdicts survive into the memo
        verdicts = br["retrieval"]["verdicts"]
        assert {v["verdict"] for v in verdicts} == {"flagged", "defensible"}

    # --- recommendation ---
    rec = memo["recommendation"]
    assert rec["winner"] == "A"
    assert rec["reasoning"]
    assert rec["text"].startswith(rec["reasoning"])

    # --- event sequence ---
    assert events[0] == "planner_started"
    assert events.count("retrieval_started") == 2
    assert events.count("modeling_started") == 2
    assert events.count("explainability_complete") == 2
    assert events.count("recommendation_result") == 1
    assert events[-1] == "memo_ready"
    # 3 scenarios per branch
    assert events.count("modeling_result") == 6


def test_pipeline_streams_explainability_chunks(mocked_providers):
    chunks: list[str] = []
    emitter = CallbackEmitter(
        lambda t, d: chunks.append(d.get("chunk", "")) if t == "explainability_chunk" else None
    )
    company = core.load_default_company("customer_support")
    core.run_pipeline("customer_support", company, emitter=emitter)
    joined = "".join(chunks)
    assert "Cost impact" in joined
    # The machine-readable data tail must NOT be streamed to the UI.
    assert "===DATA===" not in joined
