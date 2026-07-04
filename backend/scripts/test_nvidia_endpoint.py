"""Smoke test: nemotron-3-ultra-550b-a55b on NVIDIA integrate.api.nvidia.com.

Confirms the Explainability Agent provider path (project-plan §3c).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from config.token_budgets import SMOKE_TEST_NVIDIA  # noqa: E402

load_dotenv(ROOT / ".env")

API_KEY = os.getenv("NVIDIA_API_KEY")
if not API_KEY:
    print("ERROR: NVIDIA_API_KEY not set in .env", file=sys.stderr)
    sys.exit(1)

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=API_KEY,
)

print("Calling nvidia/nemotron-3-ultra-550b-a55b (stream=True) ...")
completion = client.chat.completions.create(
    model="nvidia/nemotron-3-ultra-550b-a55b",
    messages=[
        {
            "role": "user",
            "content": "Reply with exactly one word: pong",
        }
    ],
    temperature=1,
    top_p=0.95,
    max_tokens=SMOKE_TEST_NVIDIA["max_tokens"],
    extra_body={
        "chat_template_kwargs": {"enable_thinking": True},
        "reasoning_budget": SMOKE_TEST_NVIDIA["reasoning_budget"],
    },
    stream=True,
)

reasoning_parts: list[str] = []
content_parts: list[str] = []
chunk_count = 0
last_chunk_dump: dict | None = None

for chunk in completion:
    chunk_count += 1
    last_chunk_dump = chunk.model_dump()
    if not chunk.choices:
        continue
    delta = chunk.choices[0].delta
    reasoning = getattr(delta, "reasoning_content", None)
    if reasoning:
        reasoning_parts.append(reasoning)
    if delta.content is not None:
        content_parts.append(delta.content)

content = "".join(content_parts)
reasoning = "".join(reasoning_parts)

print("\n=== STREAM SUMMARY ===")
print(f"chunks received: {chunk_count}")
print(f"reasoning_content length: {len(reasoning)}")
print(f"content: {content!r}")
if reasoning:
    preview = reasoning[:400] + ("..." if len(reasoning) > 400 else "")
    print(f"reasoning_content preview: {preview!r}")

print("\n=== LAST CHUNK (model_dump) ===")
print(json.dumps(last_chunk_dump, indent=2, default=str))

if chunk_count == 0:
    print("\nFAIL: no chunks received")
    sys.exit(2)

if not content.strip() and not reasoning.strip():
    print("\nFAIL: empty content and reasoning")
    sys.exit(3)

print("\nPASS: NVIDIA endpoint responded")
sys.exit(0)
