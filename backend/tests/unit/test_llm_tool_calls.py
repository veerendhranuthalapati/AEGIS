"""Tool-call security when emitted by LLM model output."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.llm.base import ToolCall
from app.llm.tool_calls import inspect_llm_tool_calls
from app.models import Base, Tool
from tests.conftest import make_ctx


@pytest.fixture
async def engine_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            Tool(
                name="delete_user",
                description="delete",
                category="destructive",
                default_allowed_roles=["operator", "admin"],
                requires_approval=True,
                enabled=True,
            )
        )
        await session.commit()
        yield session
    await engine.dispose()


async def test_unknown_tool_blocked(engine_session) -> None:
    ctx = make_ctx(
        actor_id="user-alice",
        actor_role="user",
        actor_permissions=["agents:invoke"],
        actor_subject_id=1,
    )
    calls = [ToolCall(id="1", name="grant_admin", arguments={"user_id": 2})]
    results = await inspect_llm_tool_calls(engine_session, ctx, calls, max_depth=3)
    assert results[0].blocked
    assert results[0].decision == "BLOCK"


async def test_tool_depth_limit(engine_session) -> None:
    ctx = make_ctx(actor_id="u1", actor_role="user", actor_permissions=[])
    calls = [ToolCall(id=str(i), name="delete_user", arguments={}) for i in range(5)]
    results = await inspect_llm_tool_calls(engine_session, ctx, calls, max_depth=2)
    assert results[0].blocked
    assert "depth" in results[0].reasons[0].lower()
