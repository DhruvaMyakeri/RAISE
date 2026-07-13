"""Retrieval dialogue: Internal ⇄ Benchmark (VultronRetrieverCore via /v1/rerank).

Hard round-cap: max 1 pushback round, then auto-flag as unvalidated assumption.
VultronRetriever models only support /v1/rerank (not chat/completions).

Claim validation uses an LLM call (Kimi-K2.6 via validate_claims tool) to
judge whether each company claim is defensible given benchmark evidence and
any justifying company documentation. The rerank calls retrieve the relevant
evidence; the LLM reasons about whether the claim fits.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from config.models import (
    BENCHMARK_RETRIEVAL_MODEL,
    CLAIM_VALIDATION_MODEL,
    CLAIM_VALIDATION_MODEL_FALLBACK,
    INTERNAL_RETRIEVAL_MODEL,
)
from config.token_budgets import CLAIM_VALIDATION
from llm.clients import chat_text, vultr_client
from llm.rerank import rerank

logger = logging.getLogger(__name__)

VALIDATE_CLAIMS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "validate_claims",
        "description": (
            "Judge each company claim against benchmark evidence and any "
            "justifying documentation. Return a structured verdict per claim."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "verdicts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "claim": {
                                "type": "string",
                                "description": "Short label for the claim being judged.",
                            },
                            "verdict": {
                                "type": "string",
                                "enum": ["defensible", "flagged"],
                            },
                            "reasoning": {
                                "type": "string",
                                "description": "1-2 sentence explanation of why this verdict.",
                            },
                            "cited_fact_id": {
                                "type": "string",
                                "description": "ID of the benchmark fact used (e.g. cs_tier1_deflection), or 'none'.",
                            },
                        },
                        "required": ["claim", "verdict", "reasoning", "cited_fact_id"],
                    },
                }
            },
            "required": ["verdicts"],
        },
    },
}


def _company_docs(company: dict[str, Any], branch_value: str) -> list[str]:
    """Build document strings from company profile for rerank grounding.

    Works for any category by iterating over all current_operations and
    proposed_project fields. Falls back to generic key-value formatting
    for fields not specific to Customer Support AI.
    """
    ops = company.get("current_operations", {})
    proj = company.get("proposed_project", {})
    docs = [
        f"Company: {company.get('company_name', '?')}; industry: {company.get('industry', '?')}; size: {company.get('size', '?')}.",
    ]
    for k, v in ops.items():
        if isinstance(v, list):
            docs.append(f"{k.replace('_', ' ').title()}: {', '.join(str(x) for x in v)}.")
        else:
            docs.append(f"{k.replace('_', ' ').title()}: {v}.")
    for k, v in proj.items():
        if k == "name":
            docs.append(f"Project: {v} — {company.get('project_description', '')}.")
        else:
            docs.append(f"{k.replace('_', ' ').title()}: {v}.")
    docs.append(f"Branch assumption for this run: {branch_value}.")
    docs.append(f"Unknown fields on file: {json.dumps(company.get('unknown_fields', {}))}.")
    docs.append(f"Notes: {company.get('notes', '')}")
    return docs


def _benchmark_docs(benchmarks: dict[str, Any]) -> list[str]:
    docs: list[str] = []
    for fact in benchmarks.get("facts", []):
        docs.append(
            f"[{fact['id']}] {fact['claim']} (source: {fact['source']})"
        )
    return docs


def _build_claim_descriptions(
    claims: dict[str, Any], corpus_fact_ids: set[str]
) -> tuple[str, set[str]]:
    """Build LLM-facing claim descriptions based on whatever fields are present.

    Only references benchmark fact IDs that actually exist in the current
    category's corpus (``corpus_fact_ids``). Returns the description text and
    the set of fact IDs actually referenced (so the caller can validate the
    model's citations against what it was genuinely shown).
    """
    descs: list[str] = []
    referenced: set[str] = set()
    claim_num = 1

    def _ref(fact_id: str, phrasing: str) -> str:
        """Return ' (phrasing (fact_id))' only if the fact exists in the corpus."""
        if fact_id in corpus_fact_ids:
            referenced.add(fact_id)
            return f"{phrasing} ({fact_id})"
        return ""

    # Customer Support AI claims
    if "claimed_overall_deflection_rate" in claims:
        r = _ref("cs_tier1_deflection", "typical 20-35% overall, tier1-only ~68%")
        ref_txt = f"Ref: {r}." if r else "No matching deflection benchmark is in the provided set."
        descs.append(
            f"{claim_num}. Deflection: {claims['claimed_overall_deflection_rate']:.0%} overall "
            f"(tier1_share={claims.get('tier1_ticket_share', 0):.0%}, "
            f"implied tier1={claims.get('claimed_tier1_deflection_rate', 0):.1%}). {ref_txt}"
        )
        claim_num += 1

    # Marketing AI claims
    if "claimed_conversion_lift_rate" in claims:
        parts = [
            p for p in (
                _ref("realistic_marketing_roi_range", "realistic range is 20-25% campaign lift"),
                _ref("integrated_workflow_performance", "32% is the absolute ceiling for deep integrations"),
            ) if p
        ]
        ref_txt = f"Ref: {'; '.join(parts)}." if parts else "No matching conversion-lift benchmark is in the provided set."
        descs.append(
            f"{claim_num}. Conversion lift: {claims['claimed_conversion_lift_rate']:.0%} claimed. {ref_txt}"
        )
        claim_num += 1

    # Predictive Maintenance AI claims
    if "claimed_maintenance_spend_reduction_rate" in claims:
        parts = [
            p for p in (
                _ref("mid_market_realistic_target_range", "realistic mid-market range 11-18% total spend reduction"),
                _ref("mid_market_savings_reality", "independent baseline lower than single-asset case studies"),
            ) if p
        ]
        ref_txt = f"Ref: {'; '.join(parts)}." if parts else "No matching maintenance-savings benchmark is in the provided set."
        descs.append(
            f"{claim_num}. Maintenance spend reduction: {claims['claimed_maintenance_spend_reduction_rate']:.0%} claimed. {ref_txt}"
        )
        claim_num += 1

    # Universal: inference/operating budget vs build cost — category-specific op-cost fact.
    if "initial_build_cost_usd" in claims and "annual_inference_budget_usd" in claims:
        op_ref = (
            _ref("htec_true_op_cost", "true op cost often 3-5x build")
            or _ref("mid_market_implementation_tco", "recurring op cost typically 15-25% of build/yr")
        )
        if op_ref:
            ref_txt = f"Ref: {op_ref}."
        else:
            ref_txt = (
                "No operating-cost benchmark is in the provided set — judge with "
                "general cost-structure reasoning and cite 'none' for this claim."
            )
        descs.append(
            f"{claim_num}. Inference/operating budget: ${claims['annual_inference_budget_usd']:,.0f} vs "
            f"build ${claims['initial_build_cost_usd']:,.0f}. {ref_txt}"
        )

    return "\n".join(descs), referenced


def _fact_id_from_doc(doc: str) -> str | None:
    """Parse the leading ``[fact_id]`` token from a benchmark doc string."""
    if doc.startswith("[") and "]" in doc:
        return doc[1 : doc.index("]")]
    return None


def _llm_validate_claims(
    claims: dict[str, Any],
    bench_hits: list[dict[str, Any]],
    justify_hits: list[dict[str, Any]],
    fact_index: dict[str, Any],
) -> list[dict[str, Any]]:
    """Use Kimi-K2.6 to judge each claim against benchmark + justification evidence.

    Applies a hard guard: any ``cited_fact_id`` the model returns that was NOT
    actually shown to it (not in the retrieved benchmark set nor referenced in
    the claim descriptions) is rejected — reset to 'none' and scrubbed from the
    reasoning text — to prevent hallucinated citations.
    """
    corpus_fact_ids = set(fact_index)
    bench_docs_shown = [h["document"] for h in bench_hits[:6] if h.get("document")]
    justify_lines = [h["document"] for h in justify_hits[:3] if h.get("document")]
    claim_text, claim_ref_ids = _build_claim_descriptions(claims, corpus_fact_ids)

    # Any fact explicitly referenced in the claim descriptions must actually be
    # visible in the BENCHMARKS block so the model can cite it (otherwise it
    # correctly refuses, producing an awkward "fact not in list" flag). Inject
    # referenced corpus facts the reranker didn't surface into the top hits.
    shown_ids_in_docs = {
        fid for doc in bench_docs_shown if (fid := _fact_id_from_doc(doc))
    }
    for fid in claim_ref_ids:
        if fid not in shown_ids_in_docs and fid in fact_index:
            fact = fact_index[fid]
            bench_docs_shown.append(
                f"[{fid}] {fact['claim']} (source: {fact['source']})"
            )
            shown_ids_in_docs.add(fid)

    # Set of fact IDs genuinely available to this call = benchmark docs shown
    # (retrieved + injected) + fact IDs referenced in the claim descriptions.
    shown_fact_ids: set[str] = set(claim_ref_ids) | shown_ids_in_docs

    prompt = (
        "Validate company claims. Call validate_claims.\n\n"
        "BENCHMARKS (only these fact IDs may be cited):\n"
        + "\n".join(f"- {b}" for b in bench_docs_shown) + "\n\n"
        "COMPANY DOCS (look for pilots/measured/validated evidence):\n"
        + "\n".join(f"- {j}" for j in justify_lines) + "\n\n"
        f"CLAIMS:\n{claim_text}\n\n"
        "Judge each: defensible or flagged. Weigh benchmark fit AND company evidence.\n"
        "CITATION RULE: cited_fact_id MUST be one of the bracketed [fact_id] shown "
        "above, or exactly 'none'. Never cite a fact_id that is not shown above."
    )

    client = vultr_client()
    last_err: Exception | None = None
    for model in (CLAIM_VALIDATION_MODEL, CLAIM_VALIDATION_MODEL_FALLBACK):
        try:
            completion = chat_text(
                client=client,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=CLAIM_VALIDATION["max_tokens"],
                temperature=0.2,
                tools=[VALIDATE_CLAIMS_TOOL],
                tool_choice="required",
            )
            message = completion.choices[0].message
            tool_calls = message.tool_calls or []
            if tool_calls and tool_calls[0].function.name == "validate_claims":
                args = json.loads(tool_calls[0].function.arguments)
                verdicts = args.get("verdicts", [])
                if verdicts:
                    return _guard_citations(verdicts, shown_fact_ids)
            raise RuntimeError(
                f"validate_claims not called or empty: "
                f"finish={completion.choices[0].finish_reason}, "
                f"n_tool_calls={len(tool_calls)}"
            )
        except Exception as exc:
            last_err = exc
            logger.warning("claim validation failed on %s, trying next model: %s", model, exc)
            continue

    raise RuntimeError(f"LLM claim validation failed on all models: {last_err}")


def _guard_citations(
    verdicts: list[dict[str, Any]], shown_fact_ids: set[str]
) -> list[dict[str, Any]]:
    """Reject any cited_fact_id not actually shown to the model.

    Invalid citations are reset to 'none', recorded under 'rejected_fact_id',
    and scrubbed from the reasoning text so they never surface in the memo.
    """
    for v in verdicts:
        fid = (v.get("cited_fact_id") or "").strip()
        if fid and fid != "none" and fid not in shown_fact_ids:
            v["rejected_fact_id"] = fid
            v["cited_fact_id"] = "none"
            reasoning = v.get("reasoning") or ""
            if fid in reasoning:
                v["reasoning"] = reasoning.replace(fid, "[benchmark not in provided set]")
    return verdicts


def _build_rerank_query(claims: dict[str, Any], company: dict[str, Any]) -> str:
    """Build a category-appropriate rerank query for benchmark retrieval."""
    category = company.get("project_category", "")

    if "claimed_overall_deflection_rate" in claims:
        return (
            f"Company claims {claims['claimed_overall_deflection_rate']:.0%} deflection across "
            f"ALL tickets (Tier-1 share is {claims['tier1_ticket_share']:.0%}). "
            "What do industry benchmarks say about typical Tier-1 and overall deflection, "
            "true operating cost multiples, and ROI formulas for customer support AI?"
        )
    elif "claimed_conversion_lift_rate" in claims:
        return (
            f"Company claims {claims['claimed_conversion_lift_rate']:.0%} conversion lift "
            f"from AI-driven ad personalization. "
            "What do industry benchmarks say about realistic marketing AI conversion lift, "
            "ROI multiples by use case, payback timelines, and true operating costs?"
        )
    elif "claimed_maintenance_spend_reduction_rate" in claims:
        return (
            f"Company claims {claims['claimed_maintenance_spend_reduction_rate']:.0%} "
            "maintenance spend reduction from predictive AI. "
            "What do industry benchmarks say about realistic mid-market maintenance savings, "
            "downtime cost reduction, payback periods, and implementation TCO?"
        )
    return f"What do industry benchmarks say about AI ROI for {category}?"


def _build_justify_query(claims: dict[str, Any]) -> str:
    """Build a category-appropriate rerank query for justification retrieval."""
    if "claimed_overall_deflection_rate" in claims:
        return (
            "Does the company documentation justify an optimistic deflection rate "
            "or unusually low inference budget? Look for evidence, pilots, or "
            "measured results — not just claims."
        )
    elif "claimed_conversion_lift_rate" in claims:
        return (
            "Does the company documentation justify an optimistic conversion lift rate "
            "or unusually low inference budget? Look for pilot results, A/B tests, "
            "or measured evidence — not just projected claims."
        )
    elif "claimed_maintenance_spend_reduction_rate" in claims:
        return (
            "Does the company documentation justify an optimistic maintenance spend "
            "reduction rate or unusually low inference budget? Look for measured results, "
            "pilot deployments, or validated evidence — not just vendor promises."
        )
    return (
        "Does the company documentation justify its AI benefit claims "
        "or low operating budget? Look for evidence — not just claims."
    )


def run_retrieval_dialogue(
    *,
    company: dict[str, Any],
    benchmarks: dict[str, Any],
    claims: dict[str, Any],
    branch_field: str,
    branch_value: str,
    branch_id: str,
) -> dict[str, Any]:
    """Internal ⇄ Benchmark dialogue for one scenario branch.

    *claims* is the single-source-of-truth extraction from pipeline.claims —
    the same dict the Modeling Tool will compute with.

    Round 0: Internal reports company claims (grounded via rerank).
    Round 1: LLM validates claims against benchmark evidence + company
             justification docs in a single reasoning call.
    """
    transcript: list[dict[str, Any]] = []
    flagged: list[str] = []

    company_docs = _company_docs(company, branch_value)
    bench_docs = _benchmark_docs(benchmarks)
    fact_index = {f["id"]: f for f in benchmarks.get("facts", [])}

    # --- Internal Retrieval: pull company numbers ---
    internal_hits = rerank(
        model=INTERNAL_RETRIEVAL_MODEL,
        query=(
            "Extract company operating volumes, unit costs, claimed benefit rates, "
            "build cost, and inference budget for ROI modeling."
        ),
        documents=company_docs,
        top_n=8,
    )
    transcript.append(
        {
            "speaker": "internal_retrieval",
            "round": 0,
            "message": "Company-claimed operating numbers for this branch.",
            "claims": claims,
            "grounding": internal_hits[:5],
        }
    )

    # --- Benchmark Retrieval: retrieve relevant benchmarks ---
    claim_query = _build_rerank_query(claims, company)
    bench_hits = rerank(
        model=BENCHMARK_RETRIEVAL_MODEL,
        query=claim_query,
        documents=bench_docs,
        top_n=6,
    )

    # --- Justification retrieval: search company docs for evidence ---
    justify_query = _build_justify_query(claims)
    justify_hits = rerank(
        model=INTERNAL_RETRIEVAL_MODEL,
        query=justify_query,
        documents=company_docs,
        top_n=4,
    )

    # --- LLM validates claims using both evidence sources ---
    verdicts = _llm_validate_claims(
        claims, bench_hits, justify_hits, fact_index=fact_index
    )

    pushbacks: list[str] = []
    cited_ids: list[str] = []
    for v in verdicts:
        cited = (v.get("cited_fact_id") or "none").strip()
        if cited and cited != "none" and cited in fact_index and cited not in cited_ids:
            cited_ids.append(cited)
        if v.get("verdict") == "flagged":
            reasoning = v.get("reasoning", "")
            claim_label = v.get("claim", "unknown claim")
            pushback_msg = f"{claim_label}: {reasoning}"
            if cited and cited != "none":
                pushback_msg += f" (ref: {cited})"
            pushbacks.append(pushback_msg)

    # Citations reflect facts GENUINELY cited in this branch's reasoning — not a
    # fixed top-N of retrieved docs. This keeps the memo's Citations list honest
    # and consistent with the pushback (ref: ...) markers.
    branch_citations = [
        f"[{fid}] {fact_index[fid]['claim']} (source: {fact_index[fid]['source']})"
        for fid in cited_ids
    ]

    transcript.append(
        {
            "speaker": "benchmark_retrieval",
            "round": 1,
            "message": "LLM-judged claim validation against benchmark evidence and company justification docs.",
            "verdicts": verdicts,
            "pushbacks": pushbacks,
            "grounding": bench_hits,
            "justification_grounding": justify_hits,
            "citations": branch_citations,
        }
    )

    if pushbacks:
        for pb in pushbacks:
            flagged.append(f"assumption, not validated: {pb}")
        transcript.append(
            {
                "speaker": "internal_retrieval",
                "round": 1,
                "message": (
                    "LLM found no justifying evidence for disputed claims. "
                    "Claims passed downstream as unvalidated assumptions."
                ),
                "auto_flagged": list(flagged),
            }
        )

    flagged.append(
        f"assumption, not validated: {branch_field}={branch_value} "
        f"(user unknown; branch {branch_id})"
    )

    citations = []
    for turn in transcript:
        for c in turn.get("citations") or []:
            if c not in citations:
                citations.append(c)

    return {
        "branch_id": branch_id,
        "branch_field": branch_field,
        "branch_value": branch_value,
        "reconciled_inputs": claims,
        "flagged_assumptions": flagged,
        "transcript": transcript,
        "citations": citations,
    }
