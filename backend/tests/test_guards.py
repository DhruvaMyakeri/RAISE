"""Guard layer: citation guard, confidence validators, memo text parsers.

These are the trust mechanisms the product's pitch depends on.
"""

from __future__ import annotations

from agents.report import (
    _cited_confidence_numbers,
    _confidence_citations_valid,
    _parse_overall_confidence,
    _truncate_at_sentence,
)
from agents.retrieval import _guard_citations
from api.memo_json import _parse_citations, _parse_flag


class TestCitationGuard:
    def test_valid_citation_passes_through(self):
        verdicts = [{"claim": "x", "verdict": "flagged", "reasoning": "see cs_tier1_deflection",
                     "cited_fact_id": "cs_tier1_deflection"}]
        out = _guard_citations(verdicts, {"cs_tier1_deflection"})
        assert out[0]["cited_fact_id"] == "cs_tier1_deflection"
        assert "rejected_fact_id" not in out[0]

    def test_hallucinated_citation_rejected_and_scrubbed(self):
        verdicts = [{"claim": "x", "verdict": "flagged",
                     "reasoning": "per made_up_fact the claim is high",
                     "cited_fact_id": "made_up_fact"}]
        out = _guard_citations(verdicts, {"cs_tier1_deflection"})
        assert out[0]["cited_fact_id"] == "none"
        assert out[0]["rejected_fact_id"] == "made_up_fact"
        assert "made_up_fact" not in out[0]["reasoning"]
        assert "[benchmark not in provided set]" in out[0]["reasoning"]

    def test_none_citation_untouched(self):
        verdicts = [{"claim": "x", "verdict": "defensible", "reasoning": "ok",
                     "cited_fact_id": "none"}]
        out = _guard_citations(verdicts, set())
        assert out[0]["cited_fact_id"] == "none"


class TestOverallConfidence:
    def test_parses_last_overall_confidence(self):
        text = "Overall confidence: 40%. ... revised. Overall confidence is 72%."
        assert _parse_overall_confidence(text) == 72

    def test_ignores_dimension_confidences(self):
        text = "Cost impact ... Confidence: 90%.\nNo overall summary present."
        assert _parse_overall_confidence(text) is None

    def test_empty_returns_none(self):
        assert _parse_overall_confidence("") is None

    def test_out_of_range_rejected(self):
        assert _parse_overall_confidence("overall confidence: 250") is None


class TestConfidenceCitationValidator:
    def test_no_valid_scores_allows_anything(self):
        assert _confidence_citations_valid("confidence of 99%", [])

    def test_matching_citation_valid(self):
        assert _confidence_citations_valid("72% overall confidence", [72, 65])

    def test_off_by_one_tolerated(self):
        assert _confidence_citations_valid("73% confidence", [72])

    def test_mismatched_citation_invalid(self):
        assert not _confidence_citations_valid("90% confidence", [72, 65])

    def test_extracts_versus_pattern(self):
        nums = _cited_confidence_numbers("confidence (72% vs 65%)")
        assert 72 in nums and 65 in nums


class TestTruncateAtSentence:
    def test_short_text_unchanged(self):
        assert _truncate_at_sentence("Short.", 100) == "Short."

    def test_truncates_at_sentence_boundary(self):
        text = "First sentence. Second sentence. " + "x" * 200
        out = _truncate_at_sentence(text, 40)
        assert out.startswith("First sentence. Second sentence.")
        assert "[additional detail omitted for brevity]" in out


class TestFlagParsing:
    def test_input_claim_flag(self):
        f = _parse_flag("assumption, not validated: Deflection: too high (ref: cs_tier1_deflection)")
        assert f["type"] == "input_claim"
        assert f["cited_fact_id"] == "cs_tier1_deflection"
        assert not f["text"].startswith("assumption, not validated:")

    def test_output_sanity_flag(self):
        f = _parse_flag("output sanity check: Computed payback (1.7 months) is below the minimum")
        assert f["type"] == "output_sanity_check"

    def test_branch_unknown_flag(self):
        f = _parse_flag("assumption, not validated: hosting_architecture=cloud (user unknown; branch B_cloud)")
        assert f["type"] == "branch_unknown"


class TestCitationParsing:
    def test_well_formed_citation(self):
        parsed = _parse_citations(["[cs_x] Some claim text (source: McKinsey)"])
        assert parsed[0] == {"fact_id": "cs_x", "claim": "Some claim text", "source": "McKinsey"}

    def test_malformed_citation_falls_back(self):
        parsed = _parse_citations(["free-form citation"])
        assert parsed[0]["fact_id"] == ""
        assert parsed[0]["claim"] == "free-form citation"
