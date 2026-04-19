"""Process-wide throttling for LLM calls to reduce provider rate-limit failures.

Uses a bounded semaphore (max concurrent in-flight requests) plus a sliding
window on request *starts* for requests-per-minute (RPM). Optional minimum
spacing between starts. Thread-safe for sync LangGraph nodes.
"""

from __future__ import annotations

import logging
import math
import random
import threading
import time
from collections import deque
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)


def is_rate_limit_error(exc: BaseException) -> bool:
    """Detect HTTP 429 / provider rate-limit errors across common client stacks."""
    try:
        import httpx
    except ImportError:
        httpx = None  # type: ignore[assignment]

    cur: BaseException | None = exc
    visited: set[int] = set()
    while cur is not None and id(cur) not in visited:
        visited.add(id(cur))
        if httpx is not None and isinstance(cur, httpx.HTTPStatusError):
            return cur.response.status_code == 429
        name = cur.__class__.__name__
        if name in ("RateLimitError", "APIStatusError"):
            code = getattr(cur, "status_code", None) or getattr(cur, "code", None)
            if code == 429:
                return True
        cur = cur.__cause__ or cur.__context__

    text = str(exc).lower()
    if "429" in text and ("rate" in text or "limit" in text or "too many" in text):
        return True
    if "too many requests" in text or "rate limit" in text or "rate_limit" in text:
        return True
    return False


class _LLMRateGate:
    """Singleton gate; configuration read lazily from get_settings()."""

    _instance: _LLMRateGate | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._starts: deque[float] = deque()
        self._sem: threading.Semaphore | None = None
        self._last_start: float = 0.0
        self._cfg_id: int | None = None

    @classmethod
    def instance(cls) -> _LLMRateGate:
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _refresh_config(self) -> tuple[int, float, float]:
        from app.core.config import get_settings

        s = get_settings()
        concurrent = max(1, int(s.llm_max_concurrent_calls))
        rpm = float(s.llm_max_requests_per_minute)
        interval = max(0.0, float(s.llm_min_interval_seconds))
        cfg_id = id(s)  # settings cached; same object → stable
        if self._sem is None or self._cfg_id != cfg_id:
            self._sem = threading.Semaphore(concurrent)
            self._cfg_id = cfg_id
        return concurrent, rpm, interval

    @contextmanager
    def acquire(self) -> Any:
        _, rpm, interval = self._refresh_config()
        if self._sem is None:
            yield
            return
        self._sem.acquire()
        try:
            self._wait_for_slot(rpm, interval)
            yield
        finally:
            self._sem.release()

    def _wait_for_slot(self, rpm: float, interval: float) -> None:
        """Block until an RPM slot and optional min-interval are satisfied."""
        window = 60.0
        max_starts = max(1, math.ceil(rpm)) if rpm > 0 else 0

        def prune(old: deque[float], now_ts: float) -> None:
            while old and old[0] < now_ts - window:
                old.popleft()

        with self._lock:
            now = time.monotonic()
            if max_starts > 0:
                prune(self._starts, now)
                while len(self._starts) >= max_starts:
                    wait = window - (now - self._starts[0]) + 0.05
                    if wait > 0:
                        logger.debug("LLM RPM gate sleeping %.2fs (window full)", wait)
                        time.sleep(wait)
                    now = time.monotonic()
                    prune(self._starts, now)

            if interval > 0:
                elapsed = now - self._last_start
                if self._last_start > 0 and elapsed < interval:
                    time.sleep(interval - elapsed)
                now = time.monotonic()

            if max_starts > 0:
                self._starts.append(now)
            self._last_start = now


@contextmanager
def llm_request_slot() -> Any:
    """Context manager: hold while performing one LLM invoke/ainvoke."""
    with _LLMRateGate.instance().acquire():
        yield


def llm_429_retry_delay(attempt: int, base: float, cap: float) -> float:
    """Exponential backoff with jitter for 429 retries."""
    exp = min(cap, base * (2**attempt))
    return exp + random.uniform(0, min(1.0, exp * 0.25))
