"""LLM provider failure modes — AEGIS fails safely."""
from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.llm.base import ChatCompletionRequest, LLMProviderError
from app.llm.real import RealProvider


async def test_malformed_json_response() -> None:
    provider = RealProvider(
        Settings(llm_provider="real", llm_api_key="sk-test-key-12345678", llm_base_url="http://llm.mock")
    )
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="not-json"))
    )
    with pytest.raises(LLMProviderError, match="invalid JSON"):
        await provider.chat_completion(ChatCompletionRequest(prompt="hi"))
    await provider.close()


async def test_empty_choices() -> None:
    provider = RealProvider(
        Settings(llm_provider="real", llm_api_key="sk-test-key-12345678", llm_base_url="http://llm.mock")
    )
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": []}))
    )
    with pytest.raises(LLMProviderError, match="no choices"):
        await provider.chat_completion(ChatCompletionRequest(prompt="hi"))
    await provider.close()


async def test_rate_limit_429() -> None:
    provider = RealProvider(
        Settings(llm_provider="real", llm_api_key="sk-test-key-12345678", llm_base_url="http://llm.mock")
    )
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(429, json={"error": "rate limit"}))
    )
    with pytest.raises(LLMProviderError, match="rate limited"):
        await provider.chat_completion(ChatCompletionRequest(prompt="hi"))
    await provider.close()


async def test_unexpected_tool_call_parsed() -> None:
    provider = RealProvider(
        Settings(llm_provider="real", llm_api_key="sk-test-key-12345678", llm_base_url="http://llm.mock")
    )
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "c1",
                                        "function": {"name": "unknown_tool_xyz", "arguments": "{}"},
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        )
    )
    resp = await provider.chat_completion(ChatCompletionRequest(prompt="run tool"))
    assert resp.tool_calls[0].name == "unknown_tool_xyz"
    await provider.close()
