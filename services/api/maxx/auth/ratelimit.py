"""In-process sliding-window limiter. The API runs as one worker (see docs/deployment.md)."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException

_hits: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def reset() -> None:
    with _lock:
        _hits.clear()


def hit(key: str, limit: int, window_seconds: int) -> None:
    """Record one attempt; raise 429 with Retry-After when the window is already full."""
    now = time.monotonic()
    with _lock:
        window = _hits[key]
        while window and now - window[0] > window_seconds:
            window.popleft()
        if len(window) >= limit:
            retry = max(1, int(window_seconds - (now - window[0])))
            raise HTTPException(
                429,
                "Too many attempts. Wait a moment and try again.",
                headers={"Retry-After": str(retry)},
            )
        window.append(now)
        if len(_hits) > 50000:  # bound memory under key-spraying
            for stale in [k for k, v in _hits.items() if not v][:10000]:
                _hits.pop(stale, None)


def check(key: str, limit: int, window_seconds: int) -> None:
    """Raise 429 if `key` already has `limit` recorded attempts, without recording a new one."""
    now = time.monotonic()
    with _lock:
        window = _hits.get(key)
        if not window:
            return
        while window and now - window[0] > window_seconds:
            window.popleft()
        if len(window) >= limit:
            retry = max(1, int(window_seconds - (now - window[0])))
            raise HTTPException(
                429,
                "Too many attempts. Wait a moment and try again.",
                headers={"Retry-After": str(retry)},
            )


def record(key: str) -> None:
    with _lock:
        _hits[key].append(time.monotonic())


def count(key: str, window_seconds: int) -> int:
    """Attempts recorded for `key` in the window, without recording one."""
    now = time.monotonic()
    with _lock:
        window = _hits.get(key)
        if not window:
            return 0
        while window and now - window[0] > window_seconds:
            window.popleft()
        return len(window)
