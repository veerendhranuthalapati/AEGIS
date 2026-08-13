"""Parse LLM chat request bodies for provider invocation."""
from __future__ import annotations

import json
from typing import Any

from app.llm.base import ChatCompletionRequest


def extract_prompt_text(body_text: str | None, body_json: Any = None) -> str:
    """Extract user-visible prompt text for scanning (may be full JSON string)."""
    if body_json is None and body_text:
        try:
            body_json = json.loads(body_text)
        except (json.JSONDecodeError, ValueError):
            return body_text or ""
    if not isinstance(body_json, dict):
        return body_text or ""
    if body_json.get("prompt"):
        return str(body_json["prompt"])
    messages = body_json.get("messages")
    if isinstance(messages, list):
        parts: list[str] = []
        for msg in messages:
            if isinstance(msg, dict):
                parts.append(str(msg.get("content", "")))
        return " ".join(parts)
    return body_text or ""


def parse_chat_request(
    body_text: str | None,
    body_json: Any = None,
    *,
    default_model: str = "mock-llm",
    max_tokens: int | None = None,
) -> ChatCompletionRequest:
    if body_json is None and body_text:
        try:
            body_json = json.loads(body_text)
        except (json.JSONDecodeError, ValueError):
            body_json = None
    data: dict[str, Any] = body_json if isinstance(body_json, dict) else {}
    messages = data.get("messages")
    if not isinstance(messages, list):
        messages = []
    prompt = data.get("prompt")
    if prompt is not None:
        prompt = str(prompt)
    tools = data.get("tools") if isinstance(data.get("tools"), list) else None
    return ChatCompletionRequest(
        messages=messages,
        prompt=prompt,
        model=str(data.get("model") or default_model),
        max_tokens=int(data["max_tokens"]) if data.get("max_tokens") else max_tokens,
        temperature=float(data["temperature"]) if data.get("temperature") is not None else None,
        tools=tools,
        raw_body=body_text,
    )
