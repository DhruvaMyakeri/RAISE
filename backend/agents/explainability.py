"""Explainability Agent — per-dimension ROI breakdown with confidence scores.

Primary: NVIDIA nemotron (streaming). Fallback: Vultr GLM (non-streaming,
re-chunked for UI parity).

Structured-output contract: the model writes CFO-readable prose, then a final
line ``===DATA=== {...single-line JSON...}`` carrying the per-dimension and
overall confidence scores. ``parse_explanation()`` reads that JSON as the
primary channel; a legacy regex parse of the prose is the fallback when a
model ignores the format. The data tail is never streamed to the UI
(``_MarkerGate`` withholds it).
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

from agents.json_util import message_text
from config.models import EXPLAINABILITY_FALLBACK_MODEL, EXPLAINABILITY_MODEL
from config.token_budgets import EXPLAINABILITY, EXPLAINABILITY_FALLBACK
from llm.clients import chat_text, nvidia_client, vultr_client

logger = logging.getLogger(__name__)

DATA_MARKER = "===DATA==="

KNOWN_DIMENSIONS = [
    "Cost impact",
    "Quality impact",
    "Revenue impact",
    "Speed to value",
    "Process impact",
    "Technology impact",
]

_DEFAULT_DIMENSIONS = [
    "Cost impact",
    "Quality impact",
    "Speed to value",
    "Process impact",
    "Technology impact",
]

_CONF_IN_DIM_RE = re.compile(r"Confidence:\s*(\d{1,3})\s*%?", re.IGNORECASE)
_OVERALL_CONF_RE = re.compile(r"overall\s+confidence[^\d]{0,40}?(\d{1,3})", re.IGNORECASE)


def _prompt(
    *,
    branch: dict[str, Any],
    retrieval: dict[str, Any],
    modeling: dict[str, Any],
    roi_dimensions: list[str],
) -> str:
    dims = list(roi_dimensions) or list(_DEFAULT_DIMENSIONS)
    flagged = retrieval.get("flagged_assumptions") or modeling.get("flagged_assumptions") or []
    real_fields = [k for k in (modeling.get("inputs") or {}) if k != "branch_value"]
    dims_json = json.dumps(dims)
    return (
        "You are the Explainability Agent for an AI ROI memo.\n"
        "Break down which inputs drove which parts of the projection.\n"
        f"Use ONLY these ROI dimensions: {dims}.\n"
        "Assign a confidence score (0-100) per dimension based on how much input was "
        "real company data vs flagged-as-assumption from the retrieval dialogue.\n"
        "Do NOT recompute ROI numbers — use the Modeling Tool outputs as given.\n"
        "Be concise and CFO-readable. Cite flagged assumptions explicitly.\n\n"
        "FORMAT CONSTRAINT: For each dimension, write a short heading line followed "
        "by at most 2-3 sentences of prose covering: (a) which inputs drove the "
        "number, (b) any flagged assumptions affecting it, and (c) 'Confidence: NN%'. "
        "End the prose with a one-sentence overall confidence summary "
        "('Overall confidence: NN%'). Prose must not exceed 1500 characters. "
        "No markdown tables.\n\n"
        "MACHINE-READABLE TAIL (required): after the prose, output exactly one final "
        f"line starting with {DATA_MARKER} followed by single-line JSON of the form\n"
        f'{DATA_MARKER} {{"overall_confidence": NN, "dimensions": '
        f'[{{"name": <one of {dims_json}>, "confidence": NN}}, ...]}}\n'
        "with one entry per dimension, scores matching the prose.\n\n"
        f"Branch: {json.dumps(branch)}\n"
        f"Real numeric fields from company data: {real_fields}\n"
        f"Flagged assumptions: {json.dumps(flagged)}\n"
        f"Modeling outputs (deterministic): {json.dumps(modeling)}\n"
        f"Retrieval dialogue summary: {json.dumps(retrieval.get('transcript', []), default=str)[:3000]}\n"
    )


class _MarkerGate:
    """Forwards stream chunks to a callback, withholding everything from
    DATA_MARKER onward — even when the marker is split across chunks."""

    def __init__(self, on_chunk: Callable[[str], None] | None):
        self._on_chunk = on_chunk
        self._buffer = ""
        self._closed = False

    def feed(self, chunk: str) -> None:
        if self._closed or not self._on_chunk:
            return
        self._buffer += chunk
        idx = self._buffer.find(DATA_MARKER)
        if idx != -1:
            if idx > 0:
                self._on_chunk(self._buffer[:idx])
            self._closed = True
            self._buffer = ""
            return
        # Emit all but a marker-length tail that could still become the marker.
        holdback = len(DATA_MARKER) - 1
        if len(self._buffer) > holdback:
            self._on_chunk(self._buffer[:-holdback])
            self._buffer = self._buffer[-holdback:]

    def flush(self) -> None:
        if not self._closed and self._on_chunk and self._buffer:
            self._on_chunk(self._buffer)
        self._buffer = ""


def parse_explanation(raw: str) -> dict[str, Any]:
    """Parse an explanation into {text, overall_confidence, dimensions}.

    Primary channel: the DATA_MARKER JSON tail. Fallback: legacy regex parse of
    the prose (kept for models that ignore the format constraint). Returns
    prose with the data tail stripped in all cases.
    """
    raw = (raw or "").strip()
    prose, _, tail = raw.partition(DATA_MARKER)
    prose = prose.strip()

    if tail:
        try:
            data = json.loads(tail.strip())
            dims = [
                {
                    "name": str(d.get("name", "")),
                    "confidence": _as_score(d.get("confidence")),
                    "text": _dimension_prose(prose, str(d.get("name", ""))),
                }
                for d in data.get("dimensions", [])
                if d.get("name")
            ]
            overall = _as_score(data.get("overall_confidence"))
            if dims or overall is not None:
                return {"text": prose, "overall_confidence": overall, "dimensions": dims}
        except (json.JSONDecodeError, AttributeError, TypeError) as exc:
            logger.warning("explanation data tail unparseable, using legacy parse: %s", exc)

    return {
        "text": prose,
        "overall_confidence": parse_overall_confidence(prose),
        "dimensions": _legacy_parse_dimensions(prose),
    }


def _as_score(value: Any) -> int | None:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return v if 0 <= v <= 100 else None


def parse_overall_confidence(explanation: str) -> int | None:
    """Legacy prose parse: last 'overall confidence NN' mention in the text."""
    if not explanation:
        return None
    matches = list(_OVERALL_CONF_RE.finditer(explanation))
    if matches:
        val = int(matches[-1].group(1))
        if 0 <= val <= 100:
            return val
    return None


def _dimension_prose(text: str, dim: str) -> str:
    """Best-effort extraction of the prose block for one dimension heading."""
    if not text or not dim:
        return ""
    others = [d for d in KNOWN_DIMENSIONS if d.lower() != dim.lower()]
    stop = "|".join(re.escape(d) for d in others)
    pattern = re.compile(
        rf"(?:\*\*)?{re.escape(dim)}(?:\*\*)?\s*[:\n](.*?)(?=(?:\*\*)?(?:{stop})(?:\*\*)?\s*[:\n]|Overall confidence|$)",
        re.IGNORECASE | re.DOTALL,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def _legacy_parse_dimensions(text: str) -> list[dict[str, Any]]:
    dimensions: list[dict[str, Any]] = []
    for dim in KNOWN_DIMENSIONS:
        body = _dimension_prose(text, dim)
        if not body:
            continue
        conf_m = _CONF_IN_DIM_RE.search(body)
        dimensions.append(
            {
                "name": dim,
                "text": body,
                "confidence": int(conf_m.group(1)) if conf_m else None,
            }
        )
    return dimensions


def explain_branch(
    *,
    branch: dict[str, Any],
    retrieval: dict[str, Any],
    modeling: dict[str, Any],
    roi_dimensions: list[str],
    on_chunk: Callable[[str], None] | None = None,
) -> str:
    """Generate the explanation (raw text incl. data tail). Streams prose chunks
    to *on_chunk* when provided; the data tail is withheld from the stream."""
    prompt = _prompt(
        branch=branch,
        retrieval=retrieval,
        modeling=modeling,
        roi_dimensions=roi_dimensions,
    )
    messages = [{"role": "user", "content": prompt}]

    last_err: Exception | None = None
    for attempt in range(2):
        try:
            # The gate sits here — above the provider call — so the data tail is
            # withheld from the UI stream no matter which source produced it.
            gate = _MarkerGate(on_chunk)
            text = _stream_with_callback(
                model=EXPLAINABILITY_MODEL,
                messages=messages,
                max_tokens=EXPLAINABILITY["max_tokens"],
                reasoning_budget=EXPLAINABILITY["reasoning_budget"],
                on_chunk=gate.feed,
            )
            if text.strip():
                gate.flush()
                return text
        except Exception as exc:
            last_err = exc
            logger.warning("explainability primary attempt %d failed: %s", attempt + 1, exc)
            time.sleep(5 * (attempt + 1))

    logger.warning("explainability falling back to %s (%s)", EXPLAINABILITY_FALLBACK_MODEL, last_err)
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
        # Drop reasoning-echo preamble blocks if the model leaked them.
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(parts) > 1:
            text = parts[-1]
    if on_chunk and text:
        gate = _MarkerGate(on_chunk)
        chunk_size = 24
        for i in range(0, len(text), chunk_size):
            gate.feed(text[i : i + chunk_size])
        gate.flush()
    return text


def _stream_with_callback(
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
            if on_chunk:
                on_chunk(delta.content)
    return "".join(parts).strip()
