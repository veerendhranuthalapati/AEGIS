"""Deterministic mock LLM provider for tests and local development."""
from __future__ import annotations

import uuid

from app.llm.base import ChatCompletionRequest, ChatCompletionResponse, LLMProvider, ToolCall
from app.llm.prompt import extract_prompt_text


class MockProvider(LLMProvider):
    """Echo provider mirroring attack-lab mock-api behaviour — fully deterministic."""

    name = "mock"

    async def chat_completion(
        self,
        request: ChatCompletionRequest,
        *,
        actor_key: str | None = None,
    ) -> ChatCompletionResponse:
        prompt = extract_prompt_text(request.raw_body, {"messages": request.messages, "prompt": request.prompt})
        lowered = prompt.lower()

        if "tool:" in lowered or "call_tool" in lowered:
            tool_name = "delete_user"
            if "payment" in lowered or "execute_payment" in lowered:
                tool_name = "execute_payment"
            elif "get_user" in lowered:
                tool_name = "get_user"
            return ChatCompletionResponse(
                content="",
                model=request.model or "mock-llm",
                provider=self.name,
                tool_calls=[
                    ToolCall(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        name=tool_name,
                        arguments={"user_id": 2, "amount": 500000} if tool_name == "execute_payment" else {"user_id": 2},
                    )
                ],
                usage={"prompt_tokens": max(1, len(prompt) // 4), "completion_tokens": 20},
            )

        if any(k in lowered for k in ("internal", "secret", "api.key", "exfiltrate")):
            content = (
                "Here is the internal data: db_host=10.0.4.12, "
                "api_key=sk-mock-internal-key-999, admin_email=admin@corp.internal, "
                "ssn=123-45-6789"
            )
        else:
            content = f"Echo: {prompt[:120]}"

        return ChatCompletionResponse(
            content=content,
            model=request.model or "mock-llm",
            provider=self.name,
            usage={
                "prompt_tokens": max(1, len(prompt) // 4),
                "completion_tokens": max(1, len(content) // 4),
            },
        )

    @staticmethod
    def malformed_json_response() -> str:
        return "{not valid json completion"
