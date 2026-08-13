"""Opt-in integration tests against a real LLM provider.

Run only when explicitly enabled:
  LLM_REAL_TESTS=1 LLM_API_KEY=... pytest tests/integration/test_llm_real_provider.py -m real_llm
"""
from __future__ import annotations

import os

import pytest

from app.config import Settings
from app.llm.base import ChatCompletionRequest
from app.llm.real import RealProvider

pytestmark = pytest.mark.real_llm


@pytest.fixture
def real_enabled() -> None:
    if os.environ.get("LLM_REAL_TESTS", "").lower() not in ("1", "true", "yes"):
        pytest.skip("Set LLM_REAL_TESTS=1 to run real LLM integration tests")
    if not os.environ.get("LLM_API_KEY"):
        pytest.skip("LLM_API_KEY required for real LLM tests")


@pytest.mark.asyncio
async def test_real_provider_chat(real_enabled: None) -> None:
    settings = Settings(
        llm_provider="real",
        llm_api_key=os.environ["LLM_API_KEY"],
        llm_base_url=os.environ.get("LLM_BASE_URL", ""),
        llm_model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        llm_max_output_tokens=64,
    )
    provider = RealProvider(settings)
    try:
        resp = await provider.chat_completion(
            ChatCompletionRequest(prompt="Reply with exactly: pong"),
            actor_key="integration-test",
        )
        assert resp.content
        assert settings.llm_api_key not in resp.content
    finally:
        await provider.close()
