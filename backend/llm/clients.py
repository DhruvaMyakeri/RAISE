"""OpenAI-compatible clients for Vultr and NVIDIA (project-plan §3b/§3c)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@lru_cache(maxsize=1)
def vultr_client() -> OpenAI:
    key = os.environ.get("VULTR_API_KEY")
    if not key:
        raise RuntimeError("VULTR_API_KEY not set in .env")
    return OpenAI(base_url="https://api.vultrinference.com/v1", api_key=key)


@lru_cache(maxsize=1)
def nvidia_client() -> OpenAI:
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        raise RuntimeError("NVIDIA_API_KEY not set in .env")
    return OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=key)


def chat_text(
    *,
    client: OpenAI,
    model: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float = 0.2,
    tools: list[dict] | None = None,
    tool_choice: str | dict | None = None,
) -> object:
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if tools is not None:
        kwargs["tools"] = tools
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice
    return client.chat.completions.create(**kwargs)


def nvidia_stream_text(
    *,
    model: str,
    messages: list[dict],
    max_tokens: int,
    reasoning_budget: int,
) -> str:
    """Explainability path — stream and collect content (project-plan §3c)."""
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
    return "".join(parts).strip()
