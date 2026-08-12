"""Tool / agent security regression tests."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base, Tool
from app.security.agents.engine import ToolSecurityEngine


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
        session.add(
            Tool(
                name="execute_payment",
                description="pay",
                category="payment",
                default_allowed_roles=["operator", "admin"],
                requires_approval=True,
                enabled=True,
            )
        )
        await session.commit()
        yield session
    await engine.dispose()


async def test_operator_cannot_delete_user_without_approval_flow(engine_session):
    svc = ToolSecurityEngine(engine_session)
    decision = await svc.evaluate(
        actor_id="op-1",
        actor_role="operator",
        actor_permissions=["agents:invoke"],
        tool_name="delete_user",
        arguments={"user_id": 5},
    )
    assert decision.decision == "REQUIRE_APPROVAL"


async def test_cross_subject_tool_access_blocked(engine_session):
    svc = ToolSecurityEngine(engine_session)
    decision = await svc.evaluate(
        actor_id="user-a",
        actor_role="operator",
        actor_permissions=["agents:invoke"],
        tool_name="execute_payment",
        arguments={"amount": 100},
        resource_owner_id="user-b",
    )
    assert decision.decision == "BLOCK"
    assert "Cross-subject" in decision.reasons[-1]


async def test_unprivileged_user_blocked(engine_session):
    svc = ToolSecurityEngine(engine_session)
    decision = await svc.evaluate(
        actor_id="user-1",
        actor_role="user",
        actor_permissions=["agents:invoke"],
        tool_name="delete_user",
        arguments={"user_id": 2},
    )
    assert decision.decision == "BLOCK"


async def test_missing_invoke_permission_blocked(engine_session):
    svc = ToolSecurityEngine(engine_session)
    decision = await svc.evaluate(
        actor_id="user-1",
        actor_role="user",
        actor_permissions=[],
        tool_name="get_user",
        arguments={"user_id": 1},
    )
    assert decision.decision == "BLOCK"


async def test_unknown_tool_blocked(engine_session):
    svc = ToolSecurityEngine(engine_session)
    decision = await svc.evaluate(
        actor_id="admin-1",
        actor_role="admin",
        actor_permissions=["agents:invoke"],
        tool_name="nonexistent_tool",
        arguments={},
    )
    assert decision.decision == "BLOCK"
