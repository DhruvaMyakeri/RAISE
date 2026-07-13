"""Eval: does live claim validation catch each profile's intentionally
optimistic claim, and does the model cite only facts it was shown?

Each demo profile carries exactly one fabricated-optimistic claim
(``_test_notes.optimistic_claim_field``). A correct validator must flag it.
Citation discipline is measured pre-guard: ``rejected_fact_id`` on a verdict
means the model invented a citation and the guard caught it.
"""

from __future__ import annotations

from agents.retrieval import run_retrieval_dialogue
from pipeline.claims import extract_claims
from pipeline.core import CATEGORIES, _load_json, load_default_company

from ._common import EvalCase, EvalResult

# Map each category's optimistic claim to the claim-description keyword the
# verdict should reference.
_CLAIM_KEYWORDS = {
    "customer_support": ("deflection",),
    "marketing": ("conversion", "lift"),
    "maintenance": ("maintenance", "reduction", "spend"),
}


def run_eval() -> EvalResult:
    cases: list[EvalCase] = []
    for category_key, cfg in CATEGORIES.items():
        company = load_default_company(category_key)
        benchmarks = _load_json(cfg["benchmarks"])
        branch_field = cfg["branch_field"]
        branch_value = cfg["branch_options"][0]
        claims = extract_claims(company, branch_value, category_key)

        retrieval = run_retrieval_dialogue(
            company=company,
            benchmarks=benchmarks,
            claims=claims,
            branch_field=branch_field,
            branch_value=branch_value,
            branch_id=f"A_{branch_value}",
        )
        verdicts = []
        for turn in retrieval["transcript"]:
            if turn.get("speaker") == "benchmark_retrieval":
                verdicts = turn.get("verdicts") or []

        corpus_ids = {f["id"] for f in benchmarks.get("facts", [])}
        keywords = _CLAIM_KEYWORDS[category_key]
        optimistic_flagged = any(
            v.get("verdict") == "flagged"
            and any(k in (v.get("claim", "") + v.get("reasoning", "")).lower() for k in keywords)
            for v in verdicts
        )
        hallucinated = [v.get("rejected_fact_id") for v in verdicts if v.get("rejected_fact_id")]
        post_guard_valid = all(
            (v.get("cited_fact_id") or "none") == "none" or v["cited_fact_id"] in corpus_ids
            for v in verdicts
        )
        schema_ok = bool(verdicts) and all(
            {"claim", "verdict", "reasoning", "cited_fact_id"} <= set(v) for v in verdicts
        )

        cases.append(
            EvalCase(
                name=f"{category_key}: optimistic claim flagged",
                passed=optimistic_flagged,
                details={"n_verdicts": len(verdicts),
                         "verdicts": [(v.get("claim"), v.get("verdict")) for v in verdicts]},
            )
        )
        cases.append(
            EvalCase(
                name=f"{category_key}: citations valid post-guard",
                passed=post_guard_valid,
                details={"hallucinated_pre_guard": hallucinated},
            )
        )
        cases.append(
            EvalCase(
                name=f"{category_key}: verdict schema compliance",
                passed=schema_ok,
                details={},
            )
        )
    return EvalResult("claim_validation", cases)
