"""LLM upstream provider abstraction.

Chat completion flows through AEGIS security before and after the model.
Use ``get_llm_provider()`` for the configured upstream (mock or real).
"""
from app.llm.base import ChatCompletionRequest, ChatCompletionResponse, LLMProviderError
from app.llm.factory import close_llm_provider, get_llm_provider, init_llm_provider

__all__ = [
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "LLMProviderError",
    "close_llm_provider",
    "get_llm_provider",
    "init_llm_provider",
]
