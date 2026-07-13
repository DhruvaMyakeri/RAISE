"""Explainability structured-output contract: data-tail parsing + stream gate."""

from __future__ import annotations

import json

from agents.explainability import DATA_MARKER, _MarkerGate, parse_explanation

PROSE = (
    "Cost impact\nDriven by ticket volume. Confidence: 80%.\n\n"
    "Quality impact\nAssumed deflection quality. Confidence: 60%.\n\n"
    "Overall confidence: 72%."
)
TAIL = json.dumps(
    {
        "overall_confidence": 72,
        "dimensions": [
            {"name": "Cost impact", "confidence": 80},
            {"name": "Quality impact", "confidence": 60},
        ],
    }
)


class TestParseExplanation:
    def test_structured_tail_is_primary_channel(self):
        parsed = parse_explanation(f"{PROSE}\n{DATA_MARKER} {TAIL}")
        assert parsed["overall_confidence"] == 72
        assert [d["name"] for d in parsed["dimensions"]] == ["Cost impact", "Quality impact"]
        assert parsed["dimensions"][0]["confidence"] == 80
        # Prose text is preserved, tail stripped.
        assert DATA_MARKER not in parsed["text"]
        assert parsed["text"].startswith("Cost impact")
        # Dimension prose recovered from the text body.
        assert "ticket volume" in parsed["dimensions"][0]["text"]

    def test_malformed_tail_falls_back_to_legacy_regex(self):
        parsed = parse_explanation(f"{PROSE}\n{DATA_MARKER} {{not json")
        assert parsed["overall_confidence"] == 72  # from 'Overall confidence: 72%'
        names = [d["name"] for d in parsed["dimensions"]]
        assert "Cost impact" in names and "Quality impact" in names

    def test_no_tail_uses_legacy_regex(self):
        parsed = parse_explanation(PROSE)
        assert parsed["overall_confidence"] == 72
        assert parsed["dimensions"][0]["confidence"] == 80

    def test_out_of_range_scores_rejected(self):
        parsed = parse_explanation(
            f"prose\n{DATA_MARKER} "
            + json.dumps({"overall_confidence": 250, "dimensions": [{"name": "Cost impact", "confidence": -5}]})
        )
        assert parsed["overall_confidence"] is None
        assert parsed["dimensions"][0]["confidence"] is None

    def test_empty_input(self):
        parsed = parse_explanation("")
        assert parsed == {"text": "", "overall_confidence": None, "dimensions": []}


class TestMarkerGate:
    def _run(self, chunks: list[str]) -> str:
        out: list[str] = []
        gate = _MarkerGate(out.append)
        for c in chunks:
            gate.feed(c)
        gate.flush()
        return "".join(out)

    def test_passes_prose_through(self):
        assert self._run(["hello ", "world"]) == "hello world"

    def test_withholds_tail_after_marker(self):
        emitted = self._run(["prose text ", f"{DATA_MARKER} {{json}}", " more"])
        assert emitted == "prose text "

    def test_marker_split_across_chunks(self):
        emitted = self._run(["prose ", "===DA", "TA===", ' {"x": 1}'])
        assert emitted == "prose "

    def test_marker_split_one_char_at_a_time(self):
        emitted = self._run(list("abc" + DATA_MARKER + "tail"))
        assert emitted == "abc"

    def test_equals_signs_that_are_not_marker_still_emitted(self):
        emitted = self._run(["a == b ", "and c === d end"])
        assert emitted == "a == b and c === d end"

    def test_none_callback_is_safe(self):
        gate = _MarkerGate(None)
        gate.feed("anything")
        gate.flush()
