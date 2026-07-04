"""Planner/Orchestrator Agent — moonshotai/Kimi-K2.6 (project-plan §3a stage 1).

Structured steps use tool calls (reliable on Kimi); free-text content is not.
"""

from __future__ import annotations

import json
from typing import Any

from config.models import PLANNER_MODEL, PLANNER_MODEL_FALLBACK
from config.token_budgets import PLANNER
from llm.clients import chat_text, vultr_client
from modeling.roi import MODELING_TOOL_SCHEMA, modeling_tool_from_args


ROI_DIMENSIONS_CS = [
    "Cost impact",
    "Quality impact",
    "Speed to value",
    "Process impact",
    "Technology impact",
]

EMIT_PLAN_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "emit_plan",
        "description": "Emit the classified plan and optional clarifying question.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": [
                        "Customer Support AI",
                        "Marketing AI",
                        "Predictive Maintenance AI",
                    ],
                },
                "roi_dimensions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "missing_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "clarifying_question": {"type": "string"},
                "question_field": {"type": "string"},
            },
            "required": [
                "category",
                "roi_dimensions",
                "missing_fields",
                "clarifying_question",
                "question_field",
            ],
        },
    },
}

EMIT_BRANCHES_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "emit_branches",
        "description": (
            "When the user is uncertain, emit exactly 2 architecture branches "
            "(hard cap). Do not invent a single guess."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "branching": {"type": "boolean"},
                "branch_field": {"type": "string"},
                "branches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "branch_id": {"type": "string"},
                            "label": {"type": "string"},
                            "hosting_architecture": {
                                "type": "string",
                                "enum": ["on_prem", "cloud"],
                            },
                        },
                        "required": [
                            "branch_id",
                            "label",
                            "hosting_architecture",
                        ],
                    },
                },
            },
            "required": ["branching", "branch_field", "branches"],
        },
    },
}


def _call_planner(messages: list[dict], tools=None, tool_choice=None):
    client = vultr_client()
    try:
        return chat_text(
            client=client,
            model=PLANNER_MODEL,
            messages=messages,
            max_tokens=PLANNER["max_tokens"],
            temperature=0.2,
            tools=tools,
            tool_choice=tool_choice,
        )
    except Exception:
        return chat_text(
            client=client,
            model=PLANNER_MODEL_FALLBACK,
            messages=messages,
            max_tokens=PLANNER["max_tokens"],
            temperature=0.2,
            tools=tools,
            tool_choice=tool_choice,
        )


def _first_tool_args(completion: Any, expected_name: str) -> dict[str, Any]:
    message = completion.choices[0].message
    tool_calls = message.tool_calls or []
    if not tool_calls:
        # Retry once on MiniMax if primary returned no tool call (reasoning-only turn).
        raise RuntimeError(
            f"Planner did not call {expected_name}; "
            f"finish_reason={completion.choices[0].finish_reason!r} "
            f"content={message.content!r} "
            f"reasoning={getattr(message, 'reasoning', None)!r}"
        )
    tc = tool_calls[0]
    if tc.function.name != expected_name:
        raise RuntimeError(f"expected {expected_name}, got {tc.function.name}")
    return json.loads(tc.function.arguments)


def _call_planner_for_tool(
    messages: list[dict],
    tools: list[dict],
    expected_name: str,
) -> dict[str, Any]:
    """Call Planner with tools; try primary then explicit MiniMax fallback."""
    client = vultr_client()
    last_err: Exception | None = None
    for model in (PLANNER_MODEL, PLANNER_MODEL_FALLBACK):
        try:
            completion = chat_text(
                client=client,
                model=model,
                messages=messages,
                max_tokens=PLANNER["max_tokens"],
                temperature=0.2,
                tools=tools,
                tool_choice="required",
            )
            return _first_tool_args(completion, expected_name)
        except Exception as exc:
            last_err = exc
            continue
    raise RuntimeError(f"Planner tool {expected_name} failed: {last_err}")


def plan_and_clarify(company: dict[str, Any]) -> dict[str, Any]:
    """Classify project, list ROI dimensions, identify missing data, ask one question."""
    unknown = company.get("unknown_fields") or {}
    messages = [
        {
            "role": "user",
            "content": (
                "You are the Planner/Orchestrator for an AI ROI agent. Call emit_plan.\n"
                f"project_category={company.get('project_category')!r}\n"
                f"project_description={company.get('project_description')!r}\n"
                f"unknown_fields={json.dumps(unknown)}\n"
                "Rules: classify into one of 3 categories; list relevant ROI dimensions; "
                "any field with value unknown goes in missing_fields; ask one "
                "clarifying_question for the top missing field."
            ),
        }
    ]
    plan = _call_planner_for_tool(messages, [EMIT_PLAN_TOOL], "emit_plan")

    if plan.get("category") != "Customer Support AI":
        plan["category"] = "Customer Support AI"
    # Enforce Slalom dimensions relevant to Customer Support AI (§4)
    plan["roi_dimensions"] = ROI_DIMENSIONS_CS

    unknown = company.get("unknown_fields") or {}
    missing = list(plan.get("missing_fields") or [])
    for field, value in unknown.items():
        if str(value).lower() in {"unknown", "i don't know", "not decided"}:
            if field not in missing:
                missing.append(field)
    plan["missing_fields"] = missing
    if "hosting_architecture" in missing and not plan.get("clarifying_question"):
        plan["question_field"] = "hosting_architecture"
        plan["clarifying_question"] = (
            "Is Meridian Assist hosted on-premises or in the cloud?"
        )
    return plan


def branch_on_unknown(plan: dict[str, Any], user_answer: str) -> dict[str, Any]:
    """If user answer is unknown, select up to 2 representative architecture branches."""
    messages = [
        {
            "role": "user",
            "content": (
                "You are the Planner/Orchestrator. The user answered a clarifying question.\n"
                f"Prior plan:\n{json.dumps(plan, indent=2)}\n"
                f"User answer: {user_answer!r}\n\n"
                "If the answer indicates uncertainty, call emit_branches with exactly 2 "
                "options: on_prem (Scenario A) and cloud (Scenario B). Hard cap: 2 branches."
            ),
        }
    ]
    branches = _call_planner_for_tool(messages, [EMIT_BRANCHES_TOOL], "emit_branches")

    default_branches = [
        {
            "branch_id": "A_on_prem",
            "label": "Scenario A — On-prem",
            "hosting_architecture": "on_prem",
        },
        {
            "branch_id": "B_cloud",
            "label": "Scenario B — Cloud",
            "hosting_architecture": "cloud",
        },
    ]
    if not branches.get("branches") or len(branches["branches"]) < 2:
        branches = {
            "branching": True,
            "branch_field": "hosting_architecture",
            "branches": default_branches,
        }
    # Normalize ids/labels for the side-by-side memo
    normalized = []
    for branch, default in zip(branches["branches"][:2], default_branches):
        hosting = branch.get("hosting_architecture") or default["hosting_architecture"]
        normalized.append(
            {
                "branch_id": default["branch_id"],
                "label": default["label"],
                "hosting_architecture": hosting,
            }
        )
    branches["branches"] = normalized
    branches["branching"] = True
    branches["branch_field"] = "hosting_architecture"
    return branches


def call_modeling_tool_via_planner(
    *,
    branch: dict[str, Any],
    reconciled: dict[str, Any],
    flagged_assumptions: list[str],
) -> dict[str, Any]:
    """Planner triggers Modeling Tool via function calling; Python executes the tool."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are the Planner. Call run_modeling_tool exactly once with the "
                "reconciled numeric inputs. Do not compute ROI yourself."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Branch: {json.dumps(branch)}\n"
                f"Reconciled inputs: {json.dumps(reconciled)}\n"
                f"Flagged assumptions: {json.dumps(flagged_assumptions)}\n"
                "Call run_modeling_tool with branch_id, hosting_architecture, and all "
                "numeric fields. Include flagged_assumptions."
            ),
        },
    ]
    args = _call_planner_for_tool(
        messages, [MODELING_TOOL_SCHEMA], "run_modeling_tool"
    )
    args["branch_id"] = branch["branch_id"]
    args["hosting_architecture"] = branch["hosting_architecture"]
    args.setdefault("flagged_assumptions", flagged_assumptions)

    output = modeling_tool_from_args(args)
    return {
        "tool_call": {
            "id": f"planner-modeling-{branch['branch_id']}",
            "name": "run_modeling_tool",
            "arguments": args,
        },
        "result": {
            "branch_id": output.branch_id,
            "hosting_architecture": output.hosting_architecture,
            "inputs": output.inputs,
            "scenarios": output.scenarios,
            "flagged_assumptions": output.flagged_assumptions,
        },
    }
