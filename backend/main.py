"""Vantage API — FastAPI entrypoint (API layer only; pipeline logic lives in
pipeline/core.py).

Security posture:
- Optional shared bearer token (VANTAGE_API_TOKEN). When set, mutating and
  LLM-spending endpoints require it; when unset (local demo), auth is off.
  The SSE endpoint also accepts ?token= because EventSource cannot set headers.
- Per-IP rate limits on every endpoint that spends provider credits or
  writes to disk.
- CORS origins come from CORS_ORIGINS (comma-separated); defaults to the
  local Next.js dev origin — never "*".
- 500s return a generic message; full tracebacks go to the server log only.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import secrets
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Ensure backend package imports resolve (same pattern as run_category.py)
BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agents.intake import (  # noqa: E402
    DocumentTooThin,
    extract_profile_fields,
    prepare_document_text,
)
from api.companies import (  # noqa: E402
    list_companies,
    load_benchmark_corpus,
    load_company_profile,
    resolve_run_inputs,
)
from api.intake_fields import INTAKE_FIELDS, build_profile  # noqa: E402
from api.schemas import validate_company_profile  # noqa: E402
from pipeline.core import CATEGORIES, run_pipeline  # noqa: E402
from pipeline.events import CallbackEmitter, CancelToken, PipelineCancelled  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("vantage.api")

RUN_RATE_LIMIT = os.environ.get("VANTAGE_RUN_RATE_LIMIT", "6/minute")
SIGNUP_RATE_LIMIT = os.environ.get("VANTAGE_SIGNUP_RATE_LIMIT", "5/minute")
_SSE_QUEUE_POLL_SECONDS = 15.0

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Vantage API",
    description="Multi-agent ROI prediction pipeline",
    version="0.2.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def _cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["http://localhost:3000", "http://127.0.0.1:3000"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


def require_token(request: Request) -> None:
    """Shared bearer-token gate. No-op when VANTAGE_API_TOKEN is unset (local demo)."""
    expected = os.environ.get("VANTAGE_API_TOKEN", "").strip()
    if not expected:
        return
    auth = request.headers.get("authorization", "")
    supplied = ""
    if auth.lower().startswith("bearer "):
        supplied = auth[7:].strip()
    if not supplied:
        # EventSource cannot set headers; allow ?token= for the SSE endpoint.
        supplied = request.query_params.get("token", "")
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API token.")


# --- Early-access email capture (simple flat-file store, no external service) ---
DATA_DIR = BACKEND.parent / "data"
EARLY_ACCESS_FILE = DATA_DIR / "early_access_signups.jsonl"
_EARLY_ACCESS_LOCK = threading.Lock()
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_EMAIL_LEN = 254

# Loaded once, kept in memory; the file is only ever appended to by this process.
_signup_emails: set[str] | None = None


def _load_signup_emails() -> set[str]:
    emails: set[str] = set()
    if not EARLY_ACCESS_FILE.exists():
        return emails
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


class EarlyAccessRequest(BaseModel):
    email: str = Field(..., max_length=_MAX_EMAIL_LEN)


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


class PrepareRunRequest(BaseModel):
    category: str = Field(..., description="customer_support | marketing | maintenance")
    values: dict[str, Any] = Field(
        ..., description="Flat intake-form values (see GET /api/intake/fields)"
    )


# --- Prepared custom runs (EventSource cannot POST a profile) -----------------
# A validated custom profile is staged under a one-time run_id, then streamed
# via GET /api/run/stream?run_id=... Entries expire after 15 minutes.
_PREPARED_RUNS: dict[str, tuple[float, str, dict[str, Any]]] = {}
_PREPARED_LOCK = threading.Lock()
_PREPARED_TTL_SECONDS = 15 * 60


def _stage_prepared_run(category_key: str, company: dict[str, Any]) -> str:
    run_id = uuid.uuid4().hex
    now = time.monotonic()
    with _PREPARED_LOCK:
        for key, (created, _, _) in list(_PREPARED_RUNS.items()):
            if now - created > _PREPARED_TTL_SECONDS:
                del _PREPARED_RUNS[key]
        _PREPARED_RUNS[run_id] = (now, category_key, company)
    return run_id


def _pop_prepared_run(run_id: str) -> tuple[str, dict[str, Any]]:
    with _PREPARED_LOCK:
        entry = _PREPARED_RUNS.pop(run_id, None)
    if entry is None or time.monotonic() - entry[0] > _PREPARED_TTL_SECONDS:
        raise KeyError("Unknown or expired run_id — prepare the run again.")
    return entry[1], entry[2]


def _resolve_and_validate(
    category: str | None, company_id: str | None, company: dict[str, Any] | None
) -> tuple[str, dict[str, Any]]:
    """Resolve run inputs; inline profiles are schema-validated before any LLM call."""
    try:
        category_key, resolved = resolve_run_inputs(
            category=category, company_id=company_id, company=company
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if category_key not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category: {category_key}")

    if company is not None:
        try:
            validate_company_profile(category_key, resolved)
        except ValidationError as exc:
            errors = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            raise HTTPException(
                status_code=422, detail=f"Invalid company profile: {errors}"
            ) from exc
    return category_key, resolved


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


@app.get("/api/intake/fields")
def get_intake_fields() -> dict[str, Any]:
    """Field specs the frontend uses to render the custom-intake form."""
    return INTAKE_FIELDS


@app.post("/api/extract-profile", dependencies=[Depends(require_token)])
@limiter.limit(RUN_RATE_LIMIT)
async def post_extract_profile(
    request: Request, file: Annotated[UploadFile, File(...)]
) -> dict[str, Any]:
    """Extract intake-form fields from an uploaded PDF/TXT document (LLM).

    Returns a draft — the user reviews and edits it on the form before the
    profile is validated and run. Nothing extracted here runs unreviewed.
    """
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (10 MB max).")
    try:
        text = prepare_document_text(file.filename or "", data)
    except DocumentTooThin as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("document parsing failed (%s)", file.filename)
        raise HTTPException(
            status_code=422, detail="Could not read that document. Is it a valid PDF?"
        ) from None
    try:
        return extract_profile_fields(text)
    except Exception:
        logger.exception("intake extraction failed")
        raise HTTPException(
            status_code=502,
            detail="Extraction failed. Enter the numbers manually instead.",
        ) from None


@app.post("/api/run/prepare", dependencies=[Depends(require_token)])
@limiter.limit(RUN_RATE_LIMIT)
def post_run_prepare(request: Request, body: PrepareRunRequest) -> dict[str, Any]:
    """Validate a custom intake profile and stage it for streaming.

    Returns {run_id, company} — start the stream with
    GET /api/run/stream?run_id=<id>.
    """
    if body.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category: {body.category}")
    try:
        company = build_profile(body.category, body.values)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid field value: {exc}") from exc
    try:
        validate_company_profile(body.category, company)
    except ValidationError as exc:
        errors = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise HTTPException(status_code=422, detail=f"Invalid company profile: {errors}") from exc
    run_id = _stage_prepared_run(body.category, company)
    return {"run_id": run_id, "category": body.category, "company": company}


@app.post("/api/run", dependencies=[Depends(require_token)])
@limiter.limit(RUN_RATE_LIMIT)
def post_run(request: Request, body: RunRequest) -> dict[str, Any]:
    category_key, company = _resolve_and_validate(body.category, body.company_id, body.company)
    try:
        return run_pipeline(category_key, company)
    except Exception:
        logger.exception("pipeline run failed (category=%s)", category_key)
        raise HTTPException(
            status_code=500,
            detail="Pipeline run failed. See server logs for details.",
        ) from None


@app.get("/api/run/stream", dependencies=[Depends(require_token)])
@limiter.limit(RUN_RATE_LIMIT)
def get_run_stream(
    request: Request,
    category: str | None = Query(None),
    company_id: str | None = Query(None),
    run_id: str | None = Query(None, description="Prepared custom run (POST /api/run/prepare)"),
) -> StreamingResponse:
    if run_id:
        try:
            category_key, company = _pop_prepared_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    else:
        category_key, company = _resolve_and_validate(category, company_id, None)

    def event_stream():
        q: queue.Queue[tuple[str, dict[str, Any] | None]] = queue.Queue()
        cancel = CancelToken()

        def on_event(event_type: str, data: dict[str, Any]) -> None:
            q.put((event_type, data))

        def worker() -> None:
            try:
                emitter = CallbackEmitter(on_event)
                run_pipeline(category_key, company, emitter=emitter, cancel=cancel)
            except PipelineCancelled:
                logger.info("pipeline run cancelled (category=%s)", category_key)
            except Exception:
                logger.exception("pipeline stream failed (category=%s)", category_key)
                q.put(
                    (
                        "error",
                        {"message": "Pipeline run failed. See server logs for details."},
                    )
                )
            finally:
                q.put(("__done__", None))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        try:
            while True:
                try:
                    event_type, data = q.get(timeout=_SSE_QUEUE_POLL_SECONDS)
                except queue.Empty:
                    # Keep-alive comment; also lets a dead connection surface as
                    # a write error so the finally-block cancels the worker.
                    yield ": keep-alive\n\n"
                    continue
                if event_type == "__done__":
                    break
                payload = {"event": event_type, "data": data}
                yield f"data: {json.dumps(payload, default=str)}\n\n"
        finally:
            # Client disconnected or stream finished — stop spending tokens.
            cancel.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/early-access", dependencies=[Depends(require_token)])
@limiter.limit(SIGNUP_RATE_LIMIT)
def post_early_access(request: Request, body: EarlyAccessRequest) -> dict[str, str]:
    """Register an email for early access (append-only JSONL, dedupe by email)."""
    global _signup_emails
    email = body.email.strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    normalized = email.lower()
    with _EARLY_ACCESS_LOCK:
        if _signup_emails is None:
            _signup_emails = _load_signup_emails()
        if normalized in _signup_emails:
            return {"status": "already_registered", "email": email}
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "email": email,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with EARLY_ACCESS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        _signup_emails.add(normalized)
    return {"status": "registered", "email": email}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
