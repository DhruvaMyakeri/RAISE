"""Structured memo JSON builder — mirrors assemble_memo data without changing agents."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from agents.report import (
    EMIT_RECOMMENDATION_TOOL,
    _confidence_citations_valid,
    _parse_overall_confidence,
)
from config.models import PLANNER_MODEL_FALLBACK, REPORT_MODEL
from config.token_budgets import REPORT
from llm.clients import chat_text, vultr_client

_OUTPUT_SANITY_PREFIX = "output sanity check:"
_INPUT_CLAIM_PREFIX = "assumption, not validated:"

_DIM_HEADING_RE = re.compile(
    r"(?:\*\*)?([A-Za-z][\w\s]+impact|[A-Za-z][\w\s]+value)(?:\*\*)?\s*[:\n]",
    re.IGNORECASE,
)
_CONF_IN_DIM_RE = re.compile(r"Confidence:\s*(\d{1,3})\s*%?", re.IGNORECASE)
_CITATION_RE = re.compile(r"^\[(?P<id>[^\]]+)\]\s*(?P<claim>.+?)\s*\(source:\s*(?P<source>.+)\)$")
_REF_RE = re.compile(r"\(ref:\s*([^)]+)\)")


def build_memo_json(
    *,
    category_key: str,
    company: dict[str, Any],
    plan: dict[str, Any],
    branch_plan: dict[str, Any],
    branch_results: list[dict[str, Any]],
    full_retrievals: list[dict[str, Any]] | None = None,
    recommendation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build JSON-serializable memo payload preserving all memo sections."""
    company_name = company.get("company_name", "Company")
    project = company.get("proposed_project", {})
    project_name = project.get("name", "AI Project")
    category = company.get("project_category", "AI")
    branch_field = branch_plan.get("branch_field", "architecture")
    branch_labels = [
        b.get("label", f"Option {i + 1}")
        for i, b in enumerate(branch_plan.get("branches", [])[:2])
    ]

    branches_json: list[dict[str, Any]] = []
    labels = ["Scenario A", "Scenario B"]
    rec_branch_payloads: list[dict[str, Any]] = []
    valid_overall: list[int] = []

    for i, result in enumerate(branch_results[:2]):
        branch_info = result.get("branch") or {}
        modeling = result.get("modeling") or {}
        retrieval_summary = result.get("retrieval") or {}
        full_retrieval = (
            (full_retrievals[i] if full_retrievals and i < len(full_retrievals) else None)
            or retrieval_summary
        )
        explanation = result.get("explanation") or ""
        overall_conf = _parse_overall_confidence(explanation)
        if overall_conf is not None:
            valid_overall.append(overall_conf)

        branch_value = (
            branch_info.get("hosting_architecture")
            or branch_info.get("data_enrichment_strategy")
            or branch_info.get("hardware_deployment_method")
            or "?"
        )

        scenarios = modeling.get("scenarios") or {}
        lik = scenarios.get("likely", {})
        flags_raw = modeling.get("flagged_assumptions") or retrieval_summary.get(
            "flagged_assumptions", []
        )

        branches_json.append(
            {
                "label": labels[i],
                "branch_id": branch_info.get("branch_id"),
                "branch_label": branch_info.get("label"),
                "branch_field": branch_field,
                "branch_value": branch_value,
                "metrics": _metrics_table(scenarios),
                "cost_breakdown_likely": lik.get("cost_breakdown") or {},
                "flagged_assumptions": [_parse_flag(f) for f in flags_raw],
                "citations": _parse_citations(retrieval_summary.get("citations") or []),
                "explainability": {
                    "text": explanation,
                    "overall_confidence": overall_conf,
                    "dimensions": _parse_explainability_dimensions(explanation),
                },
                "retrieval": {
                    "reconciled_inputs": retrieval_summary.get("reconciled_inputs")
                    or full_retrieval.get("reconciled_inputs"),
                    "verdicts": _extract_verdicts(full_retrieval),
                },
            }
        )

        rec_branch_payloads.append(
            {
                "scenario": "AB"[i],
                "label": branch_info.get("label"),
                "hosting": branch_info.get("hosting_architecture"),
                "scenarios": {
                    name: {
                        "roi": s.get("roi"),
                        "payback_months": s.get("payback_months"),
                        "annual_value_usd": s.get("annual_value_usd"),
                        "total_cost_3y_usd": s.get("total_cost_3y_usd"),
                    }
                    for name, s in scenarios.items()
                },
                "flagged_assumptions": flags_raw,
                "overall_confidence": overall_conf,
            }
        )

    if recommendation is None:
        recommendation = _generate_recommendation_structured(
            {"branches": rec_branch_payloads}, valid_overall
        )

    return {
        "meta": {
            "category_key": category_key,
            "project_category": category,
            "company_id": company.get("company_id"),
            "company_name": company_name,
            "project_name": project_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "decision_framing": {
            "company_name": company_name,
            "project_name": project_name,
            "project_description": company.get("project_description", ""),
            "branch_field": branch_field,
            "branch_labels": branch_labels,
            "summary": (
                f"{company_name} is evaluating {project_name}: "
                f"{company.get('project_description', '')} "
                f"The {branch_field.replace('_', ' ')} has not been finalized."
            ),
        },
        "plan": plan,
        "branch_plan": branch_plan,
        "branches": branches_json,
        "recommendation": recommendation,
    }


def build_recommendation_payload(
    branch_results: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[int]]:
    """Build recommendation tool payload + valid overall confidences."""
    rec_branch_payloads: list[dict[str, Any]] = []
    valid_overall: list[int] = []
    rec_labels = ["A", "B"]

    for i, result in enumerate(branch_results[:2]):
        branch_info = result.get("branch") or {}
        modeling = result.get("modeling") or {}
        retrieval_summary = result.get("retrieval") or {}
        explanation = result.get("explanation") or ""
        overall_conf = _parse_overall_confidence(explanation)
        if overall_conf is not None:
            valid_overall.append(overall_conf)
        scenarios = modeling.get("scenarios") or {}
        flags_raw = modeling.get("flagged_assumptions") or retrieval_summary.get(
            "flagged_assumptions", []
        )
        rec_branch_payloads.append(
            {
                "scenario": rec_labels[i],
                "label": branch_info.get("label"),
                "hosting": branch_info.get("hosting_architecture"),
                "scenarios": {
                    name: {
                        "roi": s.get("roi"),
                        "payback_months": s.get("payback_months"),
                        "annual_value_usd": s.get("annual_value_usd"),
                        "total_cost_3y_usd": s.get("total_cost_3y_usd"),
                    }
                    for name, s in scenarios.items()
                },
                "flagged_assumptions": flags_raw,
                "overall_confidence": overall_conf,
            }
        )

    return {"branches": rec_branch_payloads}, rec_branch_payloads, valid_overall


def _metrics_table(scenarios: dict[str, dict[str, Any]]) -> dict[str, Any]:
    con = scenarios.get("conservative", {})
    lik = scenarios.get("likely", {})
    opt = scenarios.get("optimistic", {})

    rows: dict[str, dict[str, Any]] = {
        "roi_3yr": {
            "conservative": con.get("roi"),
            "likely": lik.get("roi"),
            "optimistic": opt.get("roi"),
        },
        "payback_months": {
            "conservative": con.get("payback_months"),
            "likely": lik.get("payback_months"),
            "optimistic": opt.get("payback_months"),
        },
        "annual_value_usd": {
            "conservative": con.get("annual_value_usd"),
            "likely": lik.get("annual_value_usd"),
            "optimistic": opt.get("annual_value_usd"),
        },
        "total_cost_3y_usd": {
            "conservative": con.get("total_cost_3y_usd"),
            "likely": lik.get("total_cost_3y_usd"),
            "optimistic": opt.get("total_cost_3y_usd"),
        },
    }

    if con.get("tickets_deflected_annual") is not None:
        rows["tickets_deflected_annual"] = {
            "conservative": con.get("tickets_deflected_annual"),
            "likely": lik.get("tickets_deflected_annual"),
            "optimistic": opt.get("tickets_deflected_annual"),
        }
    elif con.get("additional_conversions_annual") is not None:
        rows["additional_conversions_annual"] = {
            "conservative": con.get("additional_conversions_annual"),
            "likely": lik.get("additional_conversions_annual"),
            "optimistic": opt.get("additional_conversions_annual"),
        }
    elif con.get("maintenance_savings_annual") is not None:
        rows["maintenance_savings_annual"] = {
            "conservative": con.get("maintenance_savings_annual"),
            "likely": lik.get("maintenance_savings_annual"),
            "optimistic": opt.get("maintenance_savings_annual"),
        }
        rows["avoided_downtime_value_annual"] = {
            "conservative": con.get("avoided_downtime_value_annual"),
            "likely": lik.get("avoided_downtime_value_annual"),
            "optimistic": opt.get("avoided_downtime_value_annual"),
        }

    return rows


def _parse_flag(text: str) -> dict[str, Any]:
    flag_type = "input_claim"
    lower = text.lower()
    if _OUTPUT_SANITY_PREFIX in lower:
        flag_type = "output_sanity_check"
    elif "user unknown; branch" in lower or "hosting_architecture=" in lower:
        flag_type = "branch_unknown"

    ref_match = _REF_RE.search(text)
    cited_fact_id = ref_match.group(1).strip() if ref_match else None

    # Strip standard prefix for display
    display = text
    if display.startswith(_INPUT_CLAIM_PREFIX):
        display = display[len(_INPUT_CLAIM_PREFIX) :].strip()

    return {
        "text": display,
        "raw": text,
        "type": flag_type,
        "cited_fact_id": cited_fact_id,
    }


def _parse_citations(citations: list[str]) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for c in citations:
        m = _CITATION_RE.match(c.strip())
        if m:
            parsed.append(
                {
                    "fact_id": m.group("id"),
                    "claim": m.group("claim").strip(),
                    "source": m.group("source").strip(),
                }
            )
        else:
            parsed.append({"fact_id": "", "claim": c, "source": ""})
    return parsed


def _parse_explainability_dimensions(text: str) -> list[dict[str, Any]]:
    if not text:
        return []

    # Split on dimension headings (Cost impact, Quality impact, etc.)
    known_dims = [
        "Cost impact",
        "Quality impact",
        "Revenue impact",
        "Speed to value",
        "Process impact",
        "Technology impact",
    ]
    dimensions: list[dict[str, Any]] = []
    for dim in known_dims:
        pattern = re.compile(
            rf"(?:\*\*)?{re.escape(dim)}(?:\*\*)?\s*[:\n](.*?)(?=(?:\*\*)?(?:{'|'.join(re.escape(d) for d in known_dims if d != dim)})(?:\*\*)?\s*[:\n]|Overall confidence|$)",
            re.IGNORECASE | re.DOTALL,
        )
        m = pattern.search(text)
        if not m:
            continue
        body = m.group(1).strip()
        conf_m = _CONF_IN_DIM_RE.search(body)
        confidence = int(conf_m.group(1)) if conf_m else None
        dimensions.append(
            {
                "name": dim,
                "text": body,
                "confidence": confidence,
            }
        )
    return dimensions


def _extract_verdicts(retrieval: dict[str, Any]) -> list[dict[str, Any]]:
    for turn in retrieval.get("transcript") or []:
        if turn.get("speaker") == "benchmark_retrieval":
            return turn.get("verdicts") or []
    return []


def _generate_recommendation_structured(
    payload: dict[str, Any], valid_overall: list[int]
) -> dict[str, Any]:
    """Mirror report._generate_recommendation but return structured fields."""
    conf_note = ""
    if valid_overall:
        conf_note = (
            "\nThe ONLY valid confidence figures are the per-branch 'overall_confidence' "
            "values in the data below. If you cite a confidence percentage, it MUST be "
            "one of those overall values and you must label it 'overall confidence'. "
            "Never cite per-dimension confidence numbers.\n"
        )
    prompt = (
        "You are the Report Agent. Compare Scenario A vs Scenario B and call "
        "emit_recommendation.\n"
        "Do NOT just pick the higher ROI. Consider:\n"
        "- ROI and cost differences between branches\n"
        "- Number and severity of flagged assumptions per branch\n"
        "- Whether the higher-ROI branch carries proportionally more risk\n"
        "- Each branch's overall confidence score\n"
        "Reference specific numbers. Be CFO-readable."
        f"{conf_note}\n"
        f"Data:\n{json.dumps(payload, indent=2, default=str)}"
    )

    client = vultr_client()
    last_err: Exception | None = None
    for model in (REPORT_MODEL, PLANNER_MODEL_FALLBACK):
        for attempt in range(2):
            try:
                messages = [{"role": "user", "content": prompt}]
                if attempt == 1 and valid_overall:
                    correction = (
                        "\n\nCORRECTION: your previous answer cited a confidence "
                        "percentage that does not match any branch's overall confidence "
                        f"({', '.join(f'{v}%' for v in valid_overall)}). Regenerate and "
                        "cite ONLY those overall values, or omit confidence percentages."
                    )
                    messages = [{"role": "user", "content": prompt + correction}]
                completion = chat_text(
                    client=client,
                    model=model,
                    messages=messages,
                    max_tokens=REPORT["max_tokens"],
                    temperature=0.3,
                    tools=[EMIT_RECOMMENDATION_TOOL],
                    tool_choice="required",
                )
                message = completion.choices[0].message
                tool_calls = message.tool_calls or []
                if tool_calls and tool_calls[0].function.name == "emit_recommendation":
                    args = json.loads(tool_calls[0].function.arguments)
                    reasoning = (args.get("reasoning") or "").strip()
                    caveat = (args.get("confidence_caveat") or "").strip()
                    winner = args.get("winner")
                    if reasoning:
                        full_text = reasoning + (" " + caveat if caveat else "")
                        if _confidence_citations_valid(full_text, valid_overall):
                            return {
                                "winner": winner,
                                "reasoning": reasoning,
                                "confidence_caveat": caveat,
                                "text": full_text,
                            }
                        last_err = RuntimeError(
                            "recommendation cited a confidence % not matching any overall score"
                        )
                        continue
                raise RuntimeError("emit_recommendation not called or empty")
            except Exception as exc:
                last_err = exc
                continue

    conf_txt = (
        f" Overall confidence is {valid_overall[0]}% (Scenario A) vs "
        f"{valid_overall[1]}% (Scenario B)."
        if len(valid_overall) >= 2
        else ""
    )
    fallback = (
        "Both scenarios show positive ROI. The branch decision should be "
        f"validated before committing.{conf_txt} "
        f"(LLM recommendation unavailable: {last_err})"
    )
    return {
        "winner": None,
        "reasoning": fallback,
        "confidence_caveat": "",
        "text": fallback,
    }
