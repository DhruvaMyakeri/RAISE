"""Pipeline progress events, emitters, and cooperative cancellation.

The pipeline core emits typed events through an EventEmitter; consumers choose
how to surface them (SSE queue for the API, stdout for the CLI, list capture
for tests).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import Any, Protocol


class PipelineCancelled(Exception):
    """Raised inside a run when the caller has requested cancellation."""


class CancelToken:
    """Cooperative cancellation flag checked between pipeline stages."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise PipelineCancelled("pipeline run cancelled by caller")


class EventEmitter(Protocol):
    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None: ...


class CallbackEmitter:
    """Synchronous callback-based emitter (thread-safe for list/queue targets)."""

    def __init__(self, callback: Callable[[str, dict[str, Any]], None] | None = None):
        self._callback = callback

    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        if self._callback:
            self._callback(event_type, data or {})


class NullEmitter:
    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        pass


class PrintingEmitter:
    """CLI emitter — renders pipeline events as the sectioned terminal log."""

    _SECTION_EVENTS = {
        "planner_result": "PLAN + BRANCHES",
        "retrieval_complete": "RETRIEVAL",
        "modeling_result": "MODELING",
        "explainability_complete": "EXPLAINABILITY",
        "recommendation_result": "RECOMMENDATION",
    }

    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        if event_type == "explainability_chunk":
            print((data or {}).get("chunk", ""), end="", flush=True)
            return
        if event_type == "explainability_started":
            print("\n" + "=" * 72)
            print(f"EXPLAINABILITY — {(data or {}).get('branch_id', '?')}")
            print("=" * 72)
            return
        section = self._SECTION_EVENTS.get(event_type)
        if section is None:
            return
        branch = (data or {}).get("branch_id")
        print("\n" + "=" * 72)
        print(f"{section}{f' — {branch}' if branch else ''}")
        print("=" * 72)
        if data:
            print(json.dumps(data, indent=2, default=str))
