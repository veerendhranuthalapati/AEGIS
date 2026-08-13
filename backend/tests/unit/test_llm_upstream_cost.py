"""LLM upstream cost and concurrency controls."""
from __future__ import annotations

import pytest

from app.config import Settings
from app.llm.base import ChatCompletionRequest, LLMProviderError
from app.llm.cost import LLMCostController


async def test_session_limit_blocks() -> None:
    cost = LLMCostController(Settings(llm_max_session_requests=2, llm_max_concurrent_requests=5))
    await cost.acquire("sess1", "actor1")
    await cost.acquire("sess1", "actor1")
    with pytest.raises(LLMProviderError, match="session"):
        await cost.acquire("sess1", "actor1")


async def test_concurrent_semaphore() -> None:
    cost = LLMCostController(Settings(llm_max_concurrent_requests=1))
    await cost.acquire("a", "u1")
    with pytest.raises(Exception):
        import asyncio

        async def blocked() -> None:
            await cost.acquire("b", "u2")

        await asyncio.wait_for(blocked(), timeout=0.05)
    cost.release("a")
    await cost.acquire("b", "u2")
    cost.release("b")


async def test_input_token_limit_on_real_settings() -> None:
    from app.llm.real import RealProvider

    settings = Settings(
        llm_provider="real",
        llm_api_key="sk-test-key-12345678",
        llm_max_input_tokens=10,
        llm_max_prompt_chars=50_000,
    )
    long_prompt = "token " * 100
    provider = RealProvider(settings)
    with pytest.raises(LLMProviderError, match="token"):
        await provider.chat_completion(ChatCompletionRequest(prompt=long_prompt))
