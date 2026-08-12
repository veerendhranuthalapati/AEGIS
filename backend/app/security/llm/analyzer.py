"""Optional external LLM security analyzer with strict cost controls.

The external analyzer is never authoritative: it only adds a contextual
signal on high-risk requests, behind rate limits, a timeout, a circuit
breaker, prompt-size caps, per-actor and daily budget caps and a
deterministic fallback. An attacker can never drive unbounded LLM spend
through this gateway.

Cost abuse defenses are enforced on a process-wide shared analyzer instance
(``get_shared_analyzer``) so rate-limit, circuit-breaker and budget state
persist across requests instead of being recreated per request.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx
import structlog

from app.config import get_settings
from app.metrics import observe_llm, observe_llm_cost

logger = structlog.get_logger("aegis.llm_analyzer")


@dataclass
class AnalyzerResult:
    label: str  # benign | prompt_injection | jailbreak | sensitive_extraction | unclear
    confidence: float
    reason: str
    used_llm: bool
    latency_ms: float


class RateLimitExceeded(Exception):
    pass


class CircuitOpen(Exception):
    pass


class BudgetExceeded(Exception):
    pass


class _TokenBucket:
    def __init__(self, rate_per_minute: int) -> None:
        self._rate = max(1, rate_per_minute) / 60.0
        self._tokens = float(max(1, rate_per_minute))
        self._updated = time.monotonic()

    def try_acquire(self) -> bool:
        """Consume one token if available without blocking.

        Fail-fast: a gateway must not stall request processing waiting for
        LLM capacity; when the bucket is empty the caller falls back to the
        deterministic analyzer instead.
        """
        now = time.monotonic()
        self._tokens = min(
            self._rate * 60, self._tokens + (now - self._updated) * self._rate
        )
        self._updated = now
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 60.0) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._failures = 0
        self._opened_at: float | None = None

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._failure_threshold:
            self._opened_at = time.monotonic()

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at > self._cooldown:
            self._opened_at = None
            self._failures = 0
            return False
        return True


def _utc_today() -> date:
    return datetime.fromtimestamp(time.time(), tz=timezone.utc).date()


class LlmAnalyzer:
    """Deterministic fallback + optional external LLM analysis.

    One instance must be shared process-wide (see ``get_shared_analyzer``)
    so that rate, circuit and budget state persist across requests.
    """

    def __init__(self, settings=None) -> None:
        self._settings = settings or get_settings()
        self._bucket = _TokenBucket(self._settings.llm_max_calls_per_minute)
        self._breaker = CircuitBreaker()
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        # --- cost-abuse accounting --------------------------------------- #
        self._spend_date: date = _utc_today()
        self._spend_today = 0.0
        self._total_spend = 0.0
        self._actor_spend: dict[str, tuple[date, float]] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._lock:
            if self._client is None:
                self._client = httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds)
            return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def enabled(self) -> bool:
        return (
            self._settings.llm_analyzer_enabled
            and self._settings.llm_provider != "none"
            and bool(self._settings.llm_api_key)
        )

    # ------------------------------------------------------------------ #
    # cost accounting
    # ------------------------------------------------------------------ #
    def _cost_usd(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (
            prompt_tokens / 1000.0 * self._settings.llm_price_per_1k_prompt_tokens
            + completion_tokens / 1000.0 * self._settings.llm_price_per_1k_completion_tokens
        )

    def _record_spend(self, cost: float, actor_key: str | None) -> None:
        today = _utc_today()
        if self._spend_date != today:
            self._spend_date = today
            self._spend_today = 0.0
        self._spend_today += cost
        self._total_spend += cost
        if actor_key:
            prev = self._actor_spend.get(actor_key)
            self._actor_spend[actor_key] = (
                (today, cost) if prev is None or prev[0] != today else (today, prev[1] + cost)
            )
        observe_llm_cost(cost)

    def _budget_exceeded(self, actor_key: str | None) -> bool:
        today = _utc_today()
        if self._spend_date != today:
            self._spend_date = today
            self._spend_today = 0.0
        if self._spend_today >= self._settings.llm_daily_budget_usd:
            return True
        if actor_key:
            prev = self._actor_spend.get(actor_key)
            if prev is not None and prev[0] == today and prev[1] >= self._settings.llm_actor_budget_usd:
                return True
        return False

    @property
    def spend_today_usd(self) -> float:
        return self._spend_today

    @property
    def total_spend_usd(self) -> float:
        return self._total_spend

    # ------------------------------------------------------------------ #
    def _deterministic(self, text: str) -> AnalyzerResult:
        from app.security.llm.scanner import LlmScanner

        findings = LlmScanner().scan(text)
        high = [f for f in findings if f.severity == "HIGH"]
        if high:
            label = "prompt_injection"
            if any("jailbreak" in r.lower() for f in high for r in f.reasons):
                label = "jailbreak"
            if any("extraction" in r.lower() for f in high for r in f.reasons):
                label = "sensitive_extraction"
            return AnalyzerResult(
                label=label,
                confidence=0.75,
                reason="; ".join(f.reasons[0] for f in high[:3]),
                used_llm=False,
                latency_ms=0.0,
            )
        return AnalyzerResult(
            label="benign", confidence=0.5, reason="no deterministic signal",
            used_llm=False, latency_ms=0.0,
        )

    async def analyze(self, text: str | None, actor_key: str | None = None) -> AnalyzerResult:
        if not text:
            observe_llm(False, "empty", 0.0)
            return AnalyzerResult(
                "benign", 0.5, "empty prompt", False, 0.0
            )
        text = text[: self._settings.llm_max_prompt_chars]

        if not self.enabled:
            observe_llm(False, "fallback", 0.0)
            return self._deterministic(text)

        if self._budget_exceeded(actor_key):
            logger.warning(
                "llm_analyzer.budget_exceeded",
                actor=actor_key,
                spend_today_usd=round(self._spend_today, 4),
                daily_budget_usd=self._settings.llm_daily_budget_usd,
            )
            observe_llm(False, "budget", 0.0)
            return self._deterministic(text)

        if not self._bucket.try_acquire():
            observe_llm(False, "rate_limited", 0.0)
            return self._deterministic(text)

        if self._breaker.is_open:
            logger.warning("llm_analyzer.circuit_open", reason="circuit breaker open")
            observe_llm(False, "circuit_open", 0.0)
            return self._deterministic(text)

        start = time.perf_counter()
        try:
            client = await self._get_client()
            body = {
                "model": self._settings.llm_model,
                "max_tokens": self._settings.llm_max_tokens,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a security classifier. Classify the user prompt as "
                            "exactly one of: benign, prompt_injection, jailbreak, "
                            "sensitive_extraction, indirect_prompt_injection. "
                            "Reply with JSON {\"label\": ..., \"confidence\": 0..1, "
                            "\"reason\": \"short\"}."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
            }
            url = (
                f"{self._settings.llm_base_url}/chat/completions"
                if self._settings.llm_base_url
                else "https://api.openai.com/v1/chat/completions"
            )
            resp = await client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {self._settings.llm_api_key}"},
            )
            latency = (time.perf_counter() - start) * 1000
            if resp.status_code != 200:
                self._breaker.record_failure()
                logger.warning("llm_analyzer.http_error", status=resp.status_code)
                observe_llm(True, "http_error", latency)
                return self._deterministic(text)
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens") or max(1, len(text) // 4))
            completion_tokens = int(
                usage.get("completion_tokens") or max(1, len(content) // 4)
            )
            label, confidence, reason = self._parse(content)
            self._breaker.record_success()
            self._record_spend(
                self._cost_usd(prompt_tokens, completion_tokens), actor_key
            )
            observe_llm(
                True, "success", latency, prompt_tokens, completion_tokens
            )
            return AnalyzerResult(
                label, confidence, reason, used_llm=True, latency_ms=latency
            )
        except httpx.TimeoutException:
            latency = (time.perf_counter() - start) * 1000
            self._breaker.record_failure()
            logger.warning("llm_analyzer.timeout")
            observe_llm(True, "timeout", latency)
            return self._deterministic(text)
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - start) * 1000
            self._breaker.record_failure()
            logger.warning("llm_analyzer.error", error=str(exc))
            observe_llm(True, "error", latency)
            return self._deterministic(text)

    @staticmethod
    def _parse(content: str) -> tuple[str, float, str]:
        import json
        import re

        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                label = str(data.get("label", "unclear"))
                conf = float(data.get("confidence", 0.5))
                reason = str(data.get("reason", ""))[:200]
                return label, min(1.0, max(0.0, conf)), reason
            except (ValueError, TypeError):
                pass
        lowered = content.lower()
        for label in ("prompt_injection", "jailbreak", "sensitive_extraction",
                      "indirect_prompt_injection", "benign"):
            if label.replace("_", " ") in lowered:
                return label, 0.6, "parsed from free text"
        return "unclear", 0.5, "unparseable response"


_shared_analyzer: LlmAnalyzer | None = None
_shared_lock = asyncio.Lock()


def get_shared_analyzer(settings=None) -> LlmAnalyzer:
    """Return the process-wide analyzer (rate/budget state persists across requests)."""
    global _shared_analyzer
    if _shared_analyzer is None:
        raise RuntimeError("shared LLM analyzer not initialized; call init_llm_analyzer()")
    return _shared_analyzer


def init_llm_analyzer(settings=None) -> LlmAnalyzer:
    """Create the process-wide analyzer once (idempotent)."""
    global _shared_analyzer
    if _shared_analyzer is None:
        _shared_analyzer = LlmAnalyzer(settings)
    return _shared_analyzer


async def close_llm_analyzer() -> None:
    """Close the shared analyzer's HTTP client (call at shutdown)."""
    global _shared_analyzer
    if _shared_analyzer is not None:
        await _shared_analyzer.close()
        _shared_analyzer = None
