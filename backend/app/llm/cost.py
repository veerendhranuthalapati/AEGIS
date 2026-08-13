"""LLM upstream cost and concurrency controls."""
from __future__ import annotations

import asyncio
import time

from app.config import Settings, get_settings
from app.llm.base import LLMProviderError


class LLMCostController:
    """Limits concurrent, per-session, and per-actor LLM upstream calls."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._semaphore = asyncio.Semaphore(max(1, self._settings.llm_max_concurrent_requests))
        self._session_counts: dict[str, tuple[float, int]] = {}
        self._actor_counts: dict[str, tuple[float, int]] = {}
        self._lock = asyncio.Lock()

    def _window_start(self) -> float:
        return time.monotonic()

    async def acquire(self, session_key: str, actor_key: str | None) -> None:
        await self._semaphore.acquire()
        async with self._lock:
            now = self._window_start()
            sk = session_key or "anon"
            prev = self._session_counts.get(sk)
            count = 1 if prev is None or now - prev[0] > 3600 else prev[1] + 1
            if count > self._settings.llm_max_session_requests:
                self._semaphore.release()
                raise LLMProviderError("session_limit", "LLM session request limit exceeded")
            self._session_counts[sk] = (now, count)

            if actor_key:
                ap = self._actor_counts.get(actor_key)
                ac = 1 if ap is None or now - ap[0] > 3600 else ap[1] + 1
                if ac > self._settings.llm_max_actor_requests_per_hour:
                    self._semaphore.release()
                    raise LLMProviderError("actor_limit", "LLM actor request limit exceeded")
                self._actor_counts[actor_key] = (now, ac)

    def release(self, session_key: str) -> None:
        self._semaphore.release()


_shared_cost: LLMCostController | None = None


def get_cost_controller(settings=None) -> LLMCostController:
    global _shared_cost
    if _shared_cost is None:
        _shared_cost = LLMCostController(settings)
    return _shared_cost
