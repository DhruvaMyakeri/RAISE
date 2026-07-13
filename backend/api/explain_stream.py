"""Streaming explainability wrapper — emits token chunks without modifying agents."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from agents.explainability import _prompt
from agents.json_util import message_text
from config.models import EXPLAINABILITY_FALLBACK_MODEL, EXPLAINABILITY_MODEL
from config.token_budgets import EXPLAINABILITY, EXPLAINABILITY_FALLBACK
from llm.clients import chat_text, nvidia_client, vultr_client


def explain_branch_streaming(
    *,
    branch: dict[str, Any],
    retrieval: dict[str, Any],
    modeling: dict[str, Any],
    roi_dimensions: list[str],
    on_chunk: Callable[[str], None] | None = None,
) -> str:
    """Same output as explain_branch(), but invokes on_chunk for each token delta."""
    prompt = _prompt(
        branch=branch,
        retrieval=retrieval,
        modeling=modeling,
        roi_dimensions=roi_dimensions,
    )
    messages = [{"role": "user", "content": prompt}]

    for attempt in range(2):
        try:
            text = _nvidia_stream_with_callback(
                model=EXPLAINABILITY_MODEL,
                messages=messages,
                max_tokens=EXPLAINABILITY["max_tokens"],
                reasoning_budget=EXPLAINABILITY["reasoning_budget"],
                on_chunk=on_chunk,
            )
            if text.strip():
                return text
        except Exception:
            time.sleep(5 * (attempt + 1))

    # Fallback: non-streaming Vultr completion, emit in small chunks for UI parity
    fallback_messages = [
        {
            "role": "system",
            "content": (
                "Output ONLY the explainability section for the CFO memo. "
                "No planning notes or instruction restatement."
            ),
        },
        messages[0],
    ]
    completion = chat_text(
        client=vultr_client(),
        model=EXPLAINABILITY_FALLBACK_MODEL,
        messages=fallback_messages,
        max_tokens=EXPLAINABILITY_FALLBACK["max_tokens"],
        temperature=0.3,
    )
    text = message_text(completion.choices[0].message).strip()
    if text.lower().startswith("the user wants") or text.lower().startswith("i need to"):
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(parts) > 1:
            text = parts[-1]
    if on_chunk and text:
        # Simulate streaming so the UI still "types out" on fallback path
        chunk_size = 24
        for i in range(0, len(text), chunk_size):
            on_chunk(text[i : i + chunk_size])
    return text


def _nvidia_stream_with_callback(
    *,
    model: str,
    messages: list[dict],
    max_tokens: int,
    reasoning_budget: int,
    on_chunk: Callable[[str], None] | None,
) -> str:
    client = nvidia_client()
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=1,
        top_p=0.95,
        max_tokens=max_tokens,
        extra_body={
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": reasoning_budget,
        },
        stream=True,
    )
    parts: list[str] = []
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content is not None:
            parts.append(delta.content)
            if on_chunk and delta.content:
                on_chunk(delta.content)
    return "".join(parts).strip()
