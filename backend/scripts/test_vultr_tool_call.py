"""Smoke test: Vultr tool calling for Planner → Modeling Tool path.

Usage:
  python backend/scripts/test_vultr_tool_call.py [model_id]
Default model is the confirmed Planner id from config.models.
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
from config.models import PLANNER_MODEL  # noqa: E402
from config.token_budgets import SMOKE_TEST  # noqa: E402

load_dotenv(ROOT / ".env")

API_KEY = os.getenv("VULTR_API_KEY")
if not API_KEY:
    print("ERROR: VULTR_API_KEY not set in .env", file=sys.stderr)
    sys.exit(1)

MODEL = sys.argv[1] if len(sys.argv) > 1 else PLANNER_MODEL

client = OpenAI(
    base_url="https://api.vultrinference.com/v1",
    api_key=API_KEY,
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a basic arithmetic expression.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Arithmetic expression, e.g. '12 * 7 + 3'",
                    }
                },
                "required": ["expression"],
            },
        },
    }
]

print(f"Requesting model={MODEL!r} with tool_choice=required ...")
completion = client.chat.completions.create(
    model=MODEL,
    messages=[
        {
            "role": "user",
            "content": "Use the calculator tool to compute 12 * 7 + 3. Do not answer yourself.",
        }
    ],
    tools=TOOLS,
    tool_choice="required",
    max_tokens=SMOKE_TEST["max_tokens"],
    temperature=0,
)

raw = completion.model_dump()
print("\n=== RAW RESPONSE (model_dump) ===")
print(json.dumps(raw, indent=2, default=str))

choice = completion.choices[0]
message = choice.message
tool_calls = message.tool_calls or []
reported_model = raw.get("model")

print("\n=== TOOL-CALL CHECK ===")
print(f"requested_model: {MODEL}")
print(f"reported_model:  {reported_model}")
print(f"finish_reason: {choice.finish_reason}")
print(f"content: {message.content!r}")
print(f"tool_calls count: {len(tool_calls)}")

if not tool_calls:
    print("FAIL: no tool_calls in response")
    sys.exit(2)

for i, tc in enumerate(tool_calls):
    print(f"\n[{i}] id={tc.id}")
    print(f"    name={tc.function.name}")
    print(f"    arguments={tc.function.arguments}")

ok = any(tc.function.name == "calculator" for tc in tool_calls)
if not ok:
    print("\nFAIL: tool_calls present but calculator was not invoked")
    sys.exit(3)

if reported_model and reported_model != MODEL:
    print(
        f"\nWARN: response model {reported_model!r} != requested {MODEL!r} "
        "(possible silent fallback)"
    )
    sys.exit(4)

print("\nPASS: calculator tool call triggered on requested model")
sys.exit(0)
