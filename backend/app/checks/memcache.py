"""Speed helpers for the link lookups (backend flow B3).

The database (Supabase) is far away: every query costs about 0.15-0.3 s and a pooled connection about 0.6 s. So:
- MemoryCache keeps lookup answers in the server's memory too; a repeated link is answered without the database.
- save_later() writes a cache row in the background, so the user's check never waits for the database save.
The database cache stays the long-term store (it survives restarts)."""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Any, Callable

log = logging.getLogger("checkscam.cache")

_saver = ThreadPoolExecutor(max_workers=3, thread_name_prefix="cachesave")
_pending: set[Future] = set()
_pending_lock = threading.Lock()


class MemoryCache:
    """Small thread-safe key -> value store with a time limit per entry. Oldest entries go first when full."""

    def __init__(self, max_items: int = 5000):
        self.max_items = max_items
        self._items: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            if item[0] <= time.monotonic():
                del self._items[key]
                return None
            return item[1]

    def put(self, key: str, value: Any, seconds: float) -> None:
        if seconds <= 0:
            return
        with self._lock:
            self._items.pop(key, None)
            self._items[key] = (time.monotonic() + seconds, value)
            while len(self._items) > self.max_items:
                del self._items[next(iter(self._items))]

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


def save_later(fn: Callable[[], None]) -> None:
    """Runs a database save in the background; errors are logged, never raised."""
    def run():
        try:
            fn()
        except Exception:
            log.exception("background cache save failed")

    future = _saver.submit(run)
    with _pending_lock:
        _pending.add(future)
    future.add_done_callback(lambda f: _discard(f))


def _discard(future: Future) -> None:
    with _pending_lock:
        _pending.discard(future)


def flush(timeout: float = 10.0) -> None:
    """Waits until all background saves are done (tests, shutdown)."""
    with _pending_lock:
        pending = list(_pending)
    if pending:
        wait(pending, timeout=timeout)
