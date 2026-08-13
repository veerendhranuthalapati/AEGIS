"""Secret handling — API keys must not appear in logs, errors, or sanitized output."""
from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.core.redact import sanitize_known_secrets
from app.llm.base import ChatCompletionRequest, LLMProviderError
from app.llm.real import RealProvider


SECRET = "sk-live-abcdefghijklmnop1234567890"


async def test_sanitize_known_secrets() -> None:
    raw = f"Connection failed: Bearer {SECRET} invalid"
    safe = sanitize_known_secrets(raw, SECRET)
    assert SECRET not in safe
    assert "[SECRET REDACTED]" in safe


async def test_provider_error_never_contains_api_key() -> None:
    settings = Settings(
        llm_provider="real",
        llm_api_key=SECRET,
        llm_base_url="http://llm.mock",
    )
    provider = RealProvider(settings)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"Invalid key {SECRET}")

    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(LLMProviderError) as exc:
        await provider.chat_completion(ChatCompletionRequest(prompt="test"))
    assert SECRET not in str(exc.value)
    await provider.close()


async def test_http_error_log_sanitized(caplog: pytest.LogCaptureFixture) -> None:
    settings = Settings(
        llm_provider="real",
        llm_api_key=SECRET,
        llm_base_url="http://llm.mock",
    )
    provider = RealProvider(settings)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"auth failed for {SECRET}")

    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(LLMProviderError):
        await provider.chat_completion(ChatCompletionRequest(prompt="x"))
    await provider.close()
