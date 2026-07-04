"""Explainability Agent — nemotron-3-ultra via NVIDIA (project-plan §3a stage 4).

Fallback to Vultr GLM-5.2-fp8 if NVIDIA is rate-limited/flaky (plan §3b).
"""

from __future__ import annotations

import json
import time
from typing import Any

from agents.json_util import message_text
from config.models import EXPLAINABILITY_FALLBACK_MODEL, EXPLAINABILITY_MODEL
from config.token_budgets import EXPLAINABILITY, EXPLAINABILITY_FALLBACK
from llm.clients import chat_text, nvidia_stream_text, vultr_client

# Slalom dimensions relevant to Customer Support AI (subset of §4)
CS_SLALOM_DIMENSIONS = [
    "Cost impact",
    "Quality impact",
    "Speed to value",
    "Process impact",
    "Technology impact",
]


def _prompt(
    *,
    branch: dict[str, Any],
    retrieval: dict[str, Any],
    modeling: dict[str, Any],
    roi_dimensions: list[str],
) -> str:
    dims = [d for d in roi_dimensions if d in CS_SLALOM_DIMENSIONS] or CS_SLALOM_DIMENSIONS
    flagged = retrieval.get("flagged_assumptions") or modeling.get("flagged_assumptions") or []
    real_fields = [
        k
        for k in (modeling.get("inputs") or {})
        if k != "hosting_architecture"
    ]
    return (
        "You are the Explainability Agent for an AI ROI memo.\n"
        "Break down which inputs drove which parts of the projection.\n"
        f"Use ONLY these Slalom ROI dimensions: {dims}.\n"
        "Assign a confidence score (0–100) based on how much input was real company "
        "data vs flagged-as-assumption from the retrieval dialogue.\n"
        "Do NOT recompute ROI numbers — use the Modeling Tool outputs as given.\n"
        "Be concise and CFO-readable. Cite flagged assumptions explicitly.\n\n"
        "FORMAT CONSTRAINT: For each Slalom dimension, write at most 2-3 sentences "
        "covering: (a) which inputs drove the number, (b) any flagged assumptions "
        "affecting it, and (c) the confidence score. End with a 1-sentence overall "
        "confidence summary. Total output must not exceed 1500 characters. Do NOT "
        "use markdown tables — use a short heading per dimension followed by prose.\n\n"
        f"Branch: {json.dumps(branch)}\n"
        f"Real numeric fields from company data: {real_fields}\n"
        f"Flagged assumptions: {json.dumps(flagged)}\n"
        f"Modeling outputs (deterministic): {json.dumps(modeling)}\n"
        f"Retrieval dialogue summary: {json.dumps(retrieval.get('transcript', []), default=str)[:3000]}\n"
    )


def explain_branch(
    *,
    branch: dict[str, Any],
    retrieval: dict[str, Any],
    modeling: dict[str, Any],
    roi_dimensions: list[str],
) -> str:
    prompt = _prompt(
        branch=branch,
        retrieval=retrieval,
        modeling=modeling,
        roi_dimensions=roi_dimensions,
    )
    messages = [{"role": "user", "content": prompt}]

    # Primary: NVIDIA nemotron (plan §3c). Retry once on transient rate limits.
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            text = nvidia_stream_text(
                model=EXPLAINABILITY_MODEL,
                messages=messages,
                max_tokens=EXPLAINABILITY["max_tokens"],
                reasoning_budget=EXPLAINABILITY["reasoning_budget"],
            )
            if text.strip():
                return text
        except Exception as exc:
            last_err = exc
            time.sleep(5 * (attempt + 1))

    # Fallback: Vultr GLM-5.2-fp8 (plan §3b)
    print(f"  [explainability] NVIDIA unavailable ({last_err}); using Vultr fallback")
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
    # Drop instruction-echo preambles if present
    for marker in ("Confidence score", "Cost impact", "**Cost impact**", "Branch:"):
        idx = text.find(marker)
        if idx > 40:
            # keep full text if marker is late; only strip long preambles
            pass
    if text.lower().startswith("the user wants") or text.lower().startswith("i need to"):
        # Prefer content after the last blank-line-separated block if it looks like notes
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(parts) > 1:
            text = parts[-1]
    return text
