"""LLM provider factory and lifecycle."""
from __future__ import annotations

from app.config import Settings, get_settings
from app.llm.base import LLMProvider
from app.llm.mock import MockProvider
from app.llm.real import RealProvider

_provider: LLMProvider | None = None


def init_llm_provider(settings: Settings | None = None) -> LLMProvider:
    global _provider
    settings = settings or get_settings()
    mode = (settings.llm_provider or "mock").lower()
    if mode == "real":
        _provider = RealProvider(settings)
    else:
        _provider = MockProvider()
    return _provider


def get_llm_provider() -> LLMProvider:
    if _provider is None:
        raise RuntimeError("LLM provider not initialized; call init_llm_provider()")
    return _provider


async def close_llm_provider() -> None:
    global _provider
    if _provider is not None:
        await _provider.close()
        _provider = None
