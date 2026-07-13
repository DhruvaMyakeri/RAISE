"""VultronRetriever via /v1/rerank (only supported route for these models)."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

logger = logging.getLogger(__name__)

RERANK_URL = "https://api.vultrinference.com/v1/rerank"
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3

# One client per process: connection pooling avoids a TCP+TLS handshake per call.
_client = httpx.Client(timeout=60.0)


def rerank(
    *,
    model: str,
    query: str,
    documents: list[str],
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    """Return documents ordered by relevance with scores.

    Each item: {"index": int, "document": str, "relevance_score": float}
    Retries transient upstream failures with backoff.
    """
    key = os.environ.get("VULTR_API_KEY")
    if not key:
        raise RuntimeError("VULTR_API_KEY not set in .env")

    payload: dict[str, Any] = {
        "model": model,
        "query": query,
        "documents": documents,
    }
    if top_n is not None:
        payload["top_n"] = top_n

    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            resp = _client.post(
                RERANK_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code in _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS - 1:
                logger.warning(
                    "rerank got %d, retrying (attempt %d)", resp.status_code, attempt + 1
                )
                time.sleep(1.5 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            break
        except httpx.TransportError as exc:
            last_exc = exc
            if attempt < _MAX_ATTEMPTS - 1:
                logger.warning("rerank transport error, retrying: %s", exc)
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    else:  # pragma: no cover - loop always breaks or raises
        raise RuntimeError(f"rerank failed: {last_exc}")

    # Normalize common response shapes
    results = data.get("results") or data.get("data") or data
    if not isinstance(results, list):
        raise RuntimeError(f"unexpected rerank response: {data!r}")

    out: list[dict[str, Any]] = []
    for item in results:
        idx = item.get("index", item.get("document_index"))
        score = item.get("relevance_score", item.get("score"))
        doc = item.get("document")
        if isinstance(doc, dict):
            doc = doc.get("text") or doc.get("content") or str(doc)
        if doc is None and idx is not None:
            doc = documents[int(idx)]
        out.append(
            {
                "index": idx,
                "document": doc,
                "relevance_score": float(score) if score is not None else 0.0,
            }
        )
    return out
