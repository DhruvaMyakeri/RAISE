"""Helpers for reading LLM message objects."""

from __future__ import annotations

from typing import Any


def message_text(message: Any) -> str:
    """Prefer content; fall back to reasoning (some models fill reasoning first)."""
    content = getattr(message, "content", None) or ""
    if content.strip():
        return content
    reasoning = getattr(message, "reasoning", None) or ""
    return reasoning or ""
