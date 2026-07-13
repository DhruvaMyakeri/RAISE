"""Report Agent — recommendation generation + Scenario A vs B memo text.

Numbers are templated from Modeling Tool outputs (deterministic data).
``generate_recommendation`` is the single recommendation implementation used
by both the API (JSON memo) and the CLI (text memo). The LLM reasons about
tradeoffs between branches via the emit_recommendation tool call; any
confidence percentage it cites is verified against the real overall scores
and regenerated on mismatch.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from config.models import CLAIM_VALIDATION_MODEL_FALLBACK, REPORT_MODEL
from config.token_budgets import REPORT
from llm.clients import chat_text, vultr_client

logger = logging.getLogger(__name__)

_EXPLANATION_SOFT_LIMIT = 3000

# Patterns that clearly denote a *confidence* figure cited in recommendation text.
_REC_CONF_PATTERNS = [
    re.compile(r"(\d{1,3})\s*%\s*(?:overall\s+)?confidence", re.IGNORECASE),
    re.compile(r"(\d{1,3})\s*%?\s*(?:vs\.?|versus)\s*(\d{1,3})\s*%?[^.]{0,25}?confidence", re.IGNORECASE),
    re.compile(r"confidence[^.\d]{0,20}?(\d{1,3})\s*%", re.IGNORECASE),
    re.compile(r"confidence[^.\d]{0,10}?\(?\s*(\d{1,3})\s*%?\s*(?:vs\.?|versus)\s*(\d{1,3})", re.IGNORECASE),
]

EMIT_RECOMMENDATION_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "emit_recommendation",
        "description": (
            "Emit a structured recommendation comparing Scenario A vs Scenario B. "
            "Weigh ROI, cost, flagged assumptions, and confidence."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "winner": {
                    "type": "string",
                    "enum": ["A", "B"],
                    "description": "Which scenario is recommended.",
                },
                "reasoning": {
                    "type": "string",
                    "description": (
                        "2-4 sentence CFO-readable recommendation. Reference specific "
                        "ROI and cost numbers. Note if the higher-ROI branch also carries "
                        "more risk from flagged assumptions."
                    ),
                },
                "confidence_caveat": {
                    "type": "string",
                    "description": (
                        "1 sentence caveat about the recommendation's confidence "
                        "given unvalidated assumptions."
                    ),
                },
            },
            "required": ["winner", "reasoning", "confidence_caveat"],
        },
    },
}


def _cited_confidence_numbers(text: str) -> list[int]:
    """Extract confidence percentages a recommendation explicitly cites."""
    nums: list[int] = []
    for pat in _REC_CONF_PATTERNS:
        for m in pat.finditer(text or ""):
            for g in m.groups():
                if g is None:
                    continue
                v = int(g)
                if 0 <= v <= 100:
                    nums.append(v)
    return nums


def _confidence_citations_valid(text: str, valid_overall: list[int]) -> bool:
    """True if every confidence % cited in *text* matches a real overall score.

    If no overall scores could be parsed, we cannot verify — allow it. If the
    text cites no confidence numbers at all, it is trivially valid.
    """
    if not valid_overall:
        return True
    for n in _cited_confidence_numbers(text):
        if not any(abs(n - v) <= 1 for v in valid_overall):
            return False
    return True


def _truncate_at_sentence(text: str, limit: int) -> str:
    """Truncate to the last complete sentence within *limit* characters."""
    if len(text) <= limit:
        return text
    truncated = text[:limit]
    last_sentence_end = max(
        truncated.rfind(". "),
        truncated.rfind(".\n"),
        truncated.rfind(".)"),
    )
    if last_sentence_end == -1:
        last_sentence_end = truncated.rfind(".")
    if last_sentence_end > 0:
        truncated = truncated[: last_sentence_end + 1]
    else:
        last_space = truncated.rfind(" ")
        if last_space > 0:
            truncated = truncated[:last_space]
    return truncated + "\n\n[additional detail omitted for brevity]"


def _fmt_usd(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:,.0f}"


def build_recommendation_payload(
    branch_results: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[int]]:
    """Build the LLM-facing comparison payload and the list of real overall
    confidence scores (used to validate any confidence % the LLM cites)."""
    rec_branch_payloads: list[dict[str, Any]] = []
    valid_overall: list[int] = []
    rec_labels = ["A", "B"]

    for i, result in enumerate(branch_results[:2]):
        branch_info = result.get("branch") or {}
        modeling = result.get("modeling") or {}
        retrieval_summary = result.get("retrieval") or {}
        parsed = result.get("explanation_parsed") or {}
        overall_conf = parsed.get("overall_confidence")
        if overall_conf is not None:
            valid_overall.append(overall_conf)
        scenarios = modeling.get("scenarios") or {}
        flags_raw = modeling.get("flagged_assumptions") or retrieval_summary.get(
            "flagged_assumptions", []
        )
        branch_field = branch_info.get("branch_field")
        rec_branch_payloads.append(
            {
                "scenario": rec_labels[i],
                "label": branch_info.get("label"),
                "branch_choice": {
                    "field": branch_field,
                    "value": branch_info.get(branch_field) if branch_field else None,
                },
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

    return {"branches": rec_branch_payloads}, valid_overall


def generate_recommendation(branch_results: list[dict[str, Any]]) -> dict[str, Any]:
    """LLM recommendation via emit_recommendation tool call (structured).

    Returns {winner, reasoning, confidence_caveat, text}. The payload carries
    ONLY each branch's overall confidence (never per-dimension scores). Any
    confidence % cited in the output is verified against the real overall
    scores; a mismatch triggers one corrected regenerate per model.
    """
    payload, valid_overall = build_recommendation_payload(branch_results)

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
    for model in (REPORT_MODEL, CLAIM_VALIDATION_MODEL_FALLBACK):
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
                        logger.warning("recommendation confidence mismatch on %s, retrying", model)
                        continue
                raise RuntimeError("emit_recommendation not called or empty")
            except Exception as exc:
                last_err = exc
                logger.warning("recommendation attempt failed on %s: %s", model, exc)
                continue

    # Hard fallback — should not normally be reached. Uses only verified numbers.
    logger.error("recommendation unavailable from all models: %s", last_err)
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
    return {"winner": None, "reasoning": fallback, "confidence_caveat": "", "text": fallback}


def _scenario_block(label: str, branch: dict[str, Any]) -> str:
    modeling = branch.get("modeling") or {}
    scenarios = modeling.get("scenarios") or {}
    flags = modeling.get("flagged_assumptions") or (branch.get("retrieval") or {}).get("flagged_assumptions") or []
    citations = (branch.get("retrieval") or {}).get("citations") or []
    branch_info = branch.get("branch") or {}
    branch_field = branch_info.get("branch_field")
    branch_value = branch_info.get(branch_field, "?") if branch_field else "?"

    lines = [
        f"### {label} ({str(branch_value).replace('_', '-')})",
        "",
        "| Metric | Conservative | Likely | Optimistic |",
        "|--------|-------------|--------|------------|",
    ]

    con = scenarios.get("conservative", {})
    lik = scenarios.get("likely", {})
    opt = scenarios.get("optimistic", {})

    rows = [
        ("3-yr ROI", f"{con.get('roi', 0):.1f}x", f"{lik.get('roi', 0):.1f}x", f"{opt.get('roi', 0):.1f}x"),
        ("Payback", f"{con.get('payback_months', '—')} mo", f"{lik.get('payback_months', '—')} mo", f"{opt.get('payback_months', '—')} mo"),
        ("Annual value", _fmt_usd(con.get("annual_value_usd", 0)), _fmt_usd(lik.get("annual_value_usd", 0)), _fmt_usd(opt.get("annual_value_usd", 0))),
        ("3-yr total cost", _fmt_usd(con.get("total_cost_3y_usd", 0)), _fmt_usd(lik.get("total_cost_3y_usd", 0)), _fmt_usd(opt.get("total_cost_3y_usd", 0))),
    ]

    # Category-specific key metric row
    if con.get("tickets_deflected_annual") is not None and con.get("tickets_deflected_annual", 0) > 0:
        rows.append(("Tickets deflected/yr", f"{con.get('tickets_deflected_annual', 0):,.0f}", f"{lik.get('tickets_deflected_annual', 0):,.0f}", f"{opt.get('tickets_deflected_annual', 0):,.0f}"))
    elif con.get("additional_conversions_annual") is not None:
        rows.append(("Additional conversions/yr", f"{con.get('additional_conversions_annual', 0):,.0f}", f"{lik.get('additional_conversions_annual', 0):,.0f}", f"{opt.get('additional_conversions_annual', 0):,.0f}"))
    elif con.get("maintenance_savings_annual") is not None:
        rows.append(("Maintenance savings/yr", _fmt_usd(con.get("maintenance_savings_annual", 0)), _fmt_usd(lik.get("maintenance_savings_annual", 0)), _fmt_usd(opt.get("maintenance_savings_annual", 0))))
        rows.append(("Avoided downtime value/yr", _fmt_usd(con.get("avoided_downtime_value_annual", 0)), _fmt_usd(lik.get("avoided_downtime_value_annual", 0)), _fmt_usd(opt.get("avoided_downtime_value_annual", 0))))

    for name, c_val, l_val, o_val in rows:
        lines.append(f"| {name} | {c_val} | {l_val} | {o_val} |")

    # Cost breakdown from likely scenario
    bd = lik.get("cost_breakdown") or {}
    if bd:
        lines.append("")
        lines.append("**Cost breakdown (likely):**")
        lines.append(f"  Build: {_fmt_usd(bd.get('build_usd', 0))} | "
                     f"Inference Y1: {_fmt_usd(bd.get('inference_y1_usd', 0))} | "
                     f"Integration Y1: {_fmt_usd(bd.get('integration_y1_usd', 0))} | "
                     f"Model-update Y1: {_fmt_usd(bd.get('model_update_y1_usd', 0))}")
        lines.append(f"  Y2 non-linear scale: "
                     f"Integration {_fmt_usd(bd.get('integration_y2_usd', 0))}, "
                     f"Model-update {_fmt_usd(bd.get('model_update_y2_usd', 0))}")

    if flags:
        lines.append("")
        lines.append("**Flagged assumptions:**")
        for f in flags:
            lines.append(f"  - {f}")

    if citations:
        lines.append("")
        lines.append("**Citations:**")
        for c in citations[:4]:
            lines.append(f"  - {c}")

    return "\n".join(lines)


def assemble_memo(
    *,
    company: dict[str, Any],
    plan: dict[str, Any],
    branch_plan: dict[str, Any],
    branch_results: list[dict[str, Any]],
    recommendation: dict[str, Any] | None = None,
) -> str:
    """One text memo comparing both branches — not two separate memos."""
    company_name = company.get("company_name", "Company")
    project_name = company.get("proposed_project", {}).get("name", "AI Project")
    category = company.get("project_category", "AI")
    project_desc = company.get("project_description", "an AI project")
    branch_field = branch_plan.get("branch_field", "architecture")
    branch_labels_short = [
        b.get("label", f"Option {i + 1}")
        for i, b in enumerate(branch_plan.get("branches", [])[:2])
    ]

    sections = [
        f"MEMO: AI ROI — {project_name}",
        "",
        f"TO: Chief Financial Officer, {company_name}",
        "FROM: AI Investment Analysis Team",
        f"RE: ROI Projection — {project_name} ({category})",
        "",
        "---",
        "",
        "## Decision Framing",
        "",
        f"{company_name} is evaluating {project_name}: {project_desc} "
        f"The {branch_field.replace('_', ' ')} has not been finalized. This memo presents "
        f"two scenarios — {branch_labels_short[0]} and {branch_labels_short[1]} — each "
        "modeled across conservative, likely, and optimistic financial assumptions. "
        "All ROI numbers are computed by a deterministic modeling tool; no LLM-generated arithmetic.",
        "",
        "---",
        "",
    ]

    labels = ["Scenario A", "Scenario B"]
    for i, result in enumerate(branch_results[:2]):
        sections.append(_scenario_block(labels[i], result))
        sections.append("")
        parsed = result.get("explanation_parsed") or {}
        explanation = parsed.get("text") or result.get("explanation")
        if explanation:
            sections.append(f"**Explainability ({labels[i]}):**")
            if len(explanation) > _EXPLANATION_SOFT_LIMIT:
                explanation = _truncate_at_sentence(explanation, _EXPLANATION_SOFT_LIMIT)
            sections.append(explanation)
            sections.append("")
        sections.append("---")
        sections.append("")

    if recommendation is None:
        recommendation = generate_recommendation(branch_results)
    sections.append("## Recommendation")
    sections.append("")
    sections.append(recommendation["text"])
    sections.append("")
    sections.append("---")
    sections.append("*All projections use company-provided inputs where available. "
                    "Flagged assumptions are based on curated industry benchmarks "
                    "(McKinsey, HTEC, Deloitte, NVIDIA State of AI). "
                    "This memo is not financial advice.*")

    return "\n".join(sections)
