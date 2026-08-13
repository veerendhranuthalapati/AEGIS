"""Duplicate approval and idempotency regression tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest.fixture
async def approval_client(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        from app.models import Base

        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    import app.database.session as db_session

    monkeypatch.setattr(db_session, "async_session_factory", factory)
    monkeypatch.setattr(db_session, "engine", engine)

    from app.auth.password import hash_password
    from app.auth.permissions import ROLES
    from app.models import Role, RolePermission, Tool, User

    async with factory() as session:
        role_op = Role(name="operator", description="op")
        role_admin = Role(name="admin", description="admin")
        session.add_all([role_op, role_admin])
        await session.flush()
        for role_obj, role_name in ((role_op, "operator"), (role_admin, "admin")):
            for perm in ROLES[role_name]["permissions"]:
                session.add(RolePermission(role_id=role_obj.id, permission=str(perm)))
        operator = User(
            username="op1",
            email="op1@test",
            password_hash=hash_password("Op@12345"),
            role_id=role_op.id,
            subject_id=10,
            is_active=True,
        )
        admin = User(
            username="adm1",
            email="adm1@test",
            password_hash=hash_password("Adm@12345"),
            role_id=role_admin.id,
            subject_id=1,
            is_active=True,
        )
        session.add_all([operator, admin])
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

    monkeypatch.setenv("AEGIS_IN_PROCESS_WORKER", "false")
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


async def _login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


async def test_duplicate_approval_returns_409_and_executes_once(approval_client):
    op_token = await _login(approval_client, "op1", "Op@12345")
    admin_token = await _login(approval_client, "adm1", "Adm@12345")

    exec_mock = AsyncMock(return_value={"status": "success", "result": {"paid": True}})
    with patch("app.api.v1.tools.ToolExecutor") as executor_cls:
        executor_cls.return_value.execute = exec_mock
        executor_cls.return_value.close = AsyncMock()

        invoke = await approval_client.post(
            "/api/tools/invoke",
            headers={"Authorization": f"Bearer {op_token}"},
            json={"tool": "execute_payment", "arguments": {"amount": 500000}},
        )
        assert invoke.status_code == 200
        body = invoke.json()
        assert body["decision"] == "REQUIRE_APPROVAL"
        approval_id = body["approval_id"]
        assert approval_id

        first = await approval_client.post(
            f"/api/tools/approvals/{approval_id}/decide",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"approve": True},
        )
        assert first.status_code == 200
        assert first.json()["status"] == "approved"
        assert exec_mock.await_count == 1

        second = await approval_client.post(
            f"/api/tools/approvals/{approval_id}/decide",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"approve": True},
        )
        assert second.status_code == 409
        assert exec_mock.await_count == 1


async def test_deny_then_approve_rejected(approval_client):
    op_token = await _login(approval_client, "op1", "Op@12345")
    admin_token = await _login(approval_client, "adm1", "Adm@12345")

    exec_mock = AsyncMock(return_value={"status": "success"})
    with patch("app.api.v1.tools.ToolExecutor") as executor_cls:
        executor_cls.return_value.execute = exec_mock
        executor_cls.return_value.close = AsyncMock()

        invoke = await approval_client.post(
            "/api/tools/invoke",
            headers={"Authorization": f"Bearer {op_token}"},
            json={"tool": "execute_payment", "arguments": {"amount": 500000}},
        )
        approval_id = invoke.json()["approval_id"]

        deny = await approval_client.post(
            f"/api/tools/approvals/{approval_id}/decide",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"approve": False},
        )
        assert deny.status_code == 200
        assert deny.json()["status"] == "denied"
        assert exec_mock.await_count == 0

        retry = await approval_client.post(
            f"/api/tools/approvals/{approval_id}/decide",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"approve": True},
        )
        assert retry.status_code == 409
        assert exec_mock.await_count == 0
