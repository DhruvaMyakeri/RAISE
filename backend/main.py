"""FastAPI entrypoint — thin wrapper over the existing Vantage pipeline."""

from __future__ import annotations

import json
import queue
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Ensure backend package imports resolve (same pattern as run_category.py)
BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from api.companies import (  # noqa: E402
    list_companies,
    load_benchmark_corpus,
    load_company_profile,
    resolve_run_inputs,
)
from pipeline.core import CATEGORIES, run_pipeline  # noqa: E402
from pipeline.events import CallbackEmitter  # noqa: E402

app = FastAPI(
    title="Vantage API",
    description="Multi-agent ROI prediction pipeline",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Early-access email capture (simple flat-file store, no external service) ---
DATA_DIR = BACKEND.parent / "data"
EARLY_ACCESS_FILE = DATA_DIR / "early_access_signups.jsonl"
_EARLY_ACCESS_LOCK = threading.Lock()
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EarlyAccessRequest(BaseModel):
    email: str = Field(..., description="Email address to register for early access")


def _existing_signup_emails() -> set[str]:
    if not EARLY_ACCESS_FILE.exists():
        return set()
    emails: set[str] = set()
    with EARLY_ACCESS_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            email = str(rec.get("email", "")).strip().lower()
            if email:
                emails.add(email)
    return emails


class RunRequest(BaseModel):
    category: str | None = Field(
        None,
        description="customer_support | marketing | maintenance",
    )
    company_id: str | None = Field(None, description="Demo company profile id")
    company: dict[str, Any] | None = Field(
        None,
        description="Inline company profile JSON (optional alternative to company_id)",
    )


@app.get("/api/companies")
def get_companies() -> list[dict[str, str]]:
    return list_companies()


@app.get("/api/companies/{company_id}/source")
def get_company_source(company_id: str) -> dict[str, Any]:
    """Raw company profile JSON exactly as stored in data/companies/.

    Read-only transparency endpoint — includes the _test_notes and
    intentionally-optimistic / intentionally-unknown field metadata.
    """
    try:
        return load_company_profile(company_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/benchmarks/{category_key}")
def get_benchmarks(category_key: str) -> dict[str, Any]:
    """Full benchmark corpus JSON for a category, exactly as stored."""
    try:
        return load_benchmark_corpus(category_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/run")
def post_run(body: RunRequest) -> dict[str, Any]:
    try:
        category_key, company = resolve_run_inputs(
            category=body.category,
            company_id=body.company_id,
            company=body.company,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if category_key not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category: {category_key}")

    try:
        return run_pipeline(category_key, company)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/run/stream")
def get_run_stream(
    category: str | None = Query(None),
    company_id: str | None = Query(None),
) -> StreamingResponse:
    try:
        category_key, company = resolve_run_inputs(
            category=category,
            company_id=company_id,
            company=None,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if category_key not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category: {category_key}")

    def event_stream():
        q: queue.Queue[tuple[str, dict[str, Any] | None]] = queue.Queue()

        def on_event(event_type: str, data: dict[str, Any]) -> None:
            q.put((event_type, data))

        def worker() -> None:
            try:
                emitter = CallbackEmitter(on_event)
                run_pipeline(category_key, company, emitter=emitter)
            except Exception as exc:
                q.put(("error", {"message": str(exc), "type": type(exc).__name__}))
            finally:
                q.put(("__done__", None))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while True:
            event_type, data = q.get()
            if event_type == "__done__":
                break
            payload = {"event": event_type, "data": data}
            yield f"data: {json.dumps(payload, default=str)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/early-access")
def post_early_access(body: EarlyAccessRequest) -> dict[str, str]:
    """Register an email for early access (append-only JSONL, dedupe by email)."""
    email = body.email.strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    normalized = email.lower()
    with _EARLY_ACCESS_LOCK:
        if normalized in _existing_signup_emails():
            return {"status": "already_registered", "email": email}
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "email": email,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with EARLY_ACCESS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    return {"status": "registered", "email": email}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
