"""LLM upstream provider interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class LLMProviderError(Exception):
    """Sanitized provider failure — never embed API keys in messages."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatCompletionRequest:
    messages: list[dict[str, Any]] = field(default_factory=list)
    prompt: str | None = None
    model: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    tools: list[dict[str, Any]] | None = None
    raw_body: str | None = None


@dataclass
class ChatCompletionResponse:
    content: str
    model: str
    provider: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0

    def to_gateway_json(self) -> dict[str, Any]:
        """OpenAI-compatible envelope for gateway clients."""
        message: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": __import__("json").dumps(tc.arguments),
                    },
                }
                for tc in self.tool_calls
            ]
        return {
            "choices": [{"message": message, "finish_reason": "stop"}],
            "model": self.model,
            "provider": self.provider,
            "usage": self.usage,
        }


class LLMProvider(ABC):
    """Upstream LLM — invoked only after AEGIS input security passes."""

    name: str = "base"

    @abstractmethod
    async def chat_completion(
        self,
        request: ChatCompletionRequest,
        *,
        actor_key: str | None = None,
    ) -> ChatCompletionResponse:
        raise NotImplementedError

    async def close(self) -> None:
        return None
