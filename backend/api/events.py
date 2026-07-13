"""Pipeline progress event types for SSE streaming."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class EventEmitter(Protocol):
    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None: ...


class CallbackEmitter:
    """Synchronous callback-based emitter."""

    def __init__(self, callback: Callable[[str, dict[str, Any]], None] | None = None):
        self._callback = callback

    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        if self._callback:
            self._callback(event_type, data or {})


class NullEmitter:
    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        pass
