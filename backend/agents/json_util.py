"""Extract a JSON object from an LLM response that may include prose/fences."""

from __future__ import annotations

import json
import re
from typing import Any


def message_text(message: Any) -> str:
    """Prefer content; fall back to reasoning (Kimi may fill reasoning first)."""
    content = getattr(message, "content", None) or ""
    if content.strip():
        return content
    reasoning = getattr(message, "reasoning", None) or ""
    return reasoning or ""


def parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise ValueError("empty model response")

    # Fenced block
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))

    # First {...} span
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError(f"no JSON object found in: {text[:200]!r}")
