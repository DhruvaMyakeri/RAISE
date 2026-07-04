"""FastAPI entrypoint — thin wrapper over the existing Vantage pipeline."""

from __future__ import annotations

import json
import queue
import sys
import threading
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
from api.events import CallbackEmitter  # noqa: E402
from api.pipeline_runner import run_pipeline  # noqa: E402
from pipeline.run_category import CATEGORIES  # noqa: E402

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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
