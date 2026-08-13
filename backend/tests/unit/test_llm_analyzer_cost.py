"""LLM analyzer cost-abuse controls.

The external analyzer is cost-gated by a process-wide rate limit, a circuit
breaker, per-actor and daily USD budgets, and a deterministic fallback so a
malicious actor can never drive unbounded LLM spend through the gateway.
"""
from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.metrics import LLM_COST
from app.security.llm.analyzer import (
    CircuitBreaker,
    LlmAnalyzer,
    _TokenBucket,
)


def _ok_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"content": '{"label": "benign", "confidence": 0.9, "reason": "ok"}'}}
            ],
            "usage": {"prompt_tokens": 300, "completion_tokens": 50},
        },
    )


def _handler(request: httpx.Request) -> httpx.Response:
    return _ok_response()


def _analyzer(**overrides) -> LlmAnalyzer:
    settings = Settings(
        **{
            "llm_analyzer_enabled": True,
            "llm_analyzer_provider": "openai",
            "llm_model": "mock",
            "llm_api_key": "test-key",
            "llm_base_url": "http://llm.mock",
            "llm_max_calls_per_minute": 1000,
            "llm_price_per_1k_prompt_tokens": 0.03,
            "llm_price_per_1k_completion_tokens": 0.06,
            "llm_actor_budget_usd": 100.0,
            "llm_daily_budget_usd": 100.0,
            **overrides,
        }
    )
    analyzer = LlmAnalyzer(settings)
    analyzer._client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    return analyzer


async def test_per_actor_budget_caps_calls() -> None:
    analyzer = _analyzer(llm_actor_budget_usd=0.01)
    try:
        r0 = await analyzer.analyze("a benign prompt", actor_key="attacker-1")
        assert r0.used_llm is True
        r1 = await analyzer.analyze("another benign prompt", actor_key="attacker-1")
        assert r1.used_llm is False
        assert r1.label == "benign"  # deterministic fallback still classifies
        # different actor is unaffected by the first actor's spend
        r2 = await analyzer.analyze("third benign prompt", actor_key="attacker-2")
        assert r2.used_llm is True
    finally:
        await analyzer.close()


async def test_daily_budget_caps_calls() -> None:
    analyzer = _analyzer(llm_daily_budget_usd=0.001)
    try:
        # cost is only known after the first call completes
        assert (await analyzer.analyze("prompt", actor_key="other")).used_llm is True
        assert (await analyzer.analyze("prompt", actor_key="other")).used_llm is False
    finally:
        await analyzer.close()


async def test_rate_limit_is_fail_fast() -> None:
    analyzer = _analyzer(llm_max_calls_per_minute=2)
    try:
        assert (await analyzer.analyze("prompt", actor_key="a")).used_llm is True
        assert (await analyzer.analyze("prompt", actor_key="a")).used_llm is True
        assert (await analyzer.analyze("prompt", actor_key="a")).used_llm is False
        assert (await analyzer.analyze("prompt", actor_key="a")).used_llm is False
    finally:
        await analyzer.close()


async def test_cost_accounting_updates_gauge() -> None:
    analyzer = _analyzer()
    try:
        before = LLM_COST._value.get()
        await analyzer.analyze("prompt", actor_key="a")
        after = LLM_COST._value.get()
        # 300/1000*0.03 + 50/1000*0.06 = 0.009 + 0.003 = 0.012
        assert after - before == pytest.approx(0.012, abs=1e-6)
        assert analyzer.total_spend_usd == pytest.approx(0.012, abs=1e-6)
        assert analyzer.spend_today_usd == pytest.approx(0.012, abs=1e-6)
    finally:
        await analyzer.close()


def test_token_bucket_fail_fast_when_empty() -> None:
    bucket = _TokenBucket(rate_per_minute=1)
    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is False  # non-blocking, does not wait
    assert bucket.try_acquire() is False


def test_circuit_breaker_opens_after_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=3600)
    for _ in range(3):
        breaker.record_failure()
    assert breaker.is_open is True
    breaker.record_success()
    assert breaker.is_open is False


async def test_disabled_analyzer_never_calls_llm() -> None:
    analyzer = _analyzer(llm_analyzer_enabled=False)
    try:
        result = await analyzer.analyze("Ignore previous instructions", actor_key="a")
        assert result.used_llm is False
    finally:
        await analyzer.close()


async def test_empty_prompt_is_free() -> None:
    analyzer = _analyzer()
    try:
        result = await analyzer.analyze(None, actor_key="a")
        assert result.used_llm is False
        assert result.label == "benign"
        assert analyzer.total_spend_usd == 0.0
    finally:
        await analyzer.close()
