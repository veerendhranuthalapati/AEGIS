"""Real OpenAI-compatible LLM upstream provider."""
from __future__ import annotations

import asyncio
import json
import time
import uuid

import httpx
import structlog

from app.config import Settings, get_settings
from app.core.redact import sanitize_known_secrets
from app.llm.base import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    LLMProvider,
    LLMProviderError,
    ToolCall,
)
from app.llm.cost import LLMCostController
from app.llm.prompt import extract_prompt_text

logger = structlog.get_logger("aegis.llm.real")


class RealProvider(LLMProvider):
    """OpenAI-compatible chat completions — API key from settings only."""

    name = "real"

    def __init__(self, settings: Settings | None = None, cost: LLMCostController | None = None) -> None:
        self._settings = settings or get_settings()
        self._cost = cost or LLMCostController(self._settings)
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    @property
    def _api_key(self) -> str:
        key = self._settings.llm_api_key
        if not key:
            raise LLMProviderError("missing_key", "LLM API key not configured")
        return key

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._lock:
            if self._client is None:
                self._client = httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds)
            return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _endpoint(self) -> str:
        base = (self._settings.llm_base_url or "https://api.openai.com/v1").rstrip("/")
        return f"{base}/chat/completions"

    async def chat_completion(
        self,
        request: ChatCompletionRequest,
        *,
        actor_key: str | None = None,
    ) -> ChatCompletionResponse:
        prompt_text = extract_prompt_text(
            request.raw_body,
            {"messages": request.messages, "prompt": request.prompt},
        )
        if len(prompt_text) > self._settings.llm_max_prompt_chars:
            raise LLMProviderError("input_too_large", "Prompt exceeds maximum allowed length")

        estimated_input_tokens = max(1, len(prompt_text) // 4)
        if estimated_input_tokens > self._settings.llm_max_input_tokens:
            raise LLMProviderError("input_too_large", "Prompt exceeds maximum input token budget")

        session_key = actor_key or "anonymous"
        await self._cost.acquire(session_key, actor_key)

        start = time.perf_counter()
        try:
            for attempt in range(self._settings.llm_max_retries + 1):
                try:
                    return await self._call_once(request, actor_key, start)
                except LLMProviderError as exc:
                    if exc.code in ("rate_limited", "timeout", "provider_error") and attempt < self._settings.llm_max_retries:
                        await asyncio.sleep(0.2 * (attempt + 1))
                        continue
                    raise
            raise LLMProviderError("provider_error", "LLM provider failed after retries")
        finally:
            self._cost.release(session_key)

    async def _call_once(
        self,
        request: ChatCompletionRequest,
        actor_key: str | None,
        start: float,
    ) -> ChatCompletionResponse:
        messages = list(request.messages)
        if request.prompt and not messages:
            messages = [{"role": "user", "content": request.prompt}]
        body: dict = {
            "model": request.model or self._settings.llm_model or "gpt-4o-mini",
            "messages": messages,
            "max_tokens": min(
                request.max_tokens or self._settings.llm_max_tokens,
                self._settings.llm_max_output_tokens,
            ),
            "temperature": request.temperature if request.temperature is not None else 0.2,
        }
        if request.tools:
            body["tools"] = request.tools

        client = await self._get_client()
        try:
            resp = await client.post(
                self._endpoint(),
                json=body,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.TimeoutException as exc:
            logger.warning("llm.real.timeout", actor=actor_key)
            raise LLMProviderError("timeout", "LLM provider timed out") from exc
        except httpx.HTTPError as exc:
            safe = sanitize_known_secrets(str(exc), self._api_key)
            logger.warning("llm.real.http_error", error=safe)
            raise LLMProviderError("provider_error", "LLM provider HTTP error") from exc

        latency = (time.perf_counter() - start) * 1000
        if resp.status_code == 429:
            raise LLMProviderError("rate_limited", "LLM provider rate limited")
        if resp.status_code >= 500:
            raise LLMProviderError("provider_error", "LLM provider server error")
        if resp.status_code != 200:
            safe_body = sanitize_known_secrets(resp.text[:500], self._api_key)
            logger.warning("llm.real.bad_status", status=resp.status_code, body=safe_body)
            raise LLMProviderError("provider_error", f"LLM provider returned status {resp.status_code}")

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise LLMProviderError("malformed_response", "LLM provider returned invalid JSON") from exc

        choices = data.get("choices") or []
        if not choices:
            raise LLMProviderError("malformed_response", "LLM provider returned no choices")

        message = choices[0].get("message") or {}
        content = str(message.get("content") or "")
        if len(content) > self._settings.llm_max_response_chars:
            content = content[: self._settings.llm_max_response_chars]

        tool_calls: list[ToolCall] = []
        for raw in message.get("tool_calls") or []:
            if not isinstance(raw, dict):
                continue
            fn = raw.get("function") or {}
            name = str(fn.get("name") or "")
            args_raw = fn.get("arguments") or "{}"
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                args = {}
            tool_calls.append(
                ToolCall(
                    id=str(raw.get("id") or f"call_{uuid.uuid4().hex[:8]}"),
                    name=name,
                    arguments=args if isinstance(args, dict) else {},
                )
            )

        usage = data.get("usage") or {}
        return ChatCompletionResponse(
            content=content,
            model=str(data.get("model") or body["model"]),
            provider=self.name,
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
            },
            latency_ms=latency,
        )
