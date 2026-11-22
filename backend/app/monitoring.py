"""Server health numbers for the admin dashboard (Phase 10A step A2): start time and recent server errors.

Errors are kept in memory only (the last 50, counted since the server started) - no message text, only the
path, status and error type, so nothing personal is kept."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger("checkscam.errors")


class ErrorRecorder:
    def __init__(self, keep: int = 50):
        self.started_at = datetime.now(timezone.utc)
        self._start = time.monotonic()
        self.total = 0
        self.recent: deque[dict] = deque(maxlen=keep)
        self._lock = threading.Lock()

    @property
    def uptime_seconds(self) -> int:
        return int(time.monotonic() - self._start)

    def record(self, method: str, path: str, status: int, error: str = "") -> None:
        with self._lock:
            self.total += 1
            self.recent.appendleft({"at": datetime.now(timezone.utc).isoformat(), "method": method,
                                    "path": path[:200], "status": status, "error": error[:120]})

    def since(self, start: datetime) -> int:
        with self._lock:
            return sum(1 for e in self.recent if datetime.fromisoformat(e["at"]) >= start)


class ErrorMiddleware(BaseHTTPMiddleware):
    """Counts 5xx answers and crashes; a crash becomes a plain 500 answer instead of a broken connection."""

    def __init__(self, app, recorder: ErrorRecorder):
        super().__init__(app)
        self.recorder = recorder

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001 - every crash is recorded, then answered with 500
            log.exception("Unhandled error on %s %s", request.method, request.url.path)
            self.recorder.record(request.method, request.url.path, 500, type(exc).__name__)
            return JSONResponse({"detail": "Server error. Please try again later."}, status_code=500)
        if response.status_code >= 500:
            self.recorder.record(request.method, request.url.path, response.status_code)
        return response
