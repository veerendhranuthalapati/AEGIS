"""Tool invoke HTTP status semantics."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest.fixture
async def tool_client(monkeypatch):
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
        role = Role(name="user", description="user")
        session.add(role)
        await session.flush()
        for perm in ROLES["user"]["permissions"]:
            session.add(RolePermission(role_id=role.id, permission=str(perm)))
        session.add(
            User(
                username="u1",
                email="u1@test",
                password_hash=hash_password("User@12345"),
                role_id=role.id,
                subject_id=5,
                is_active=True,
            )
        )
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

    monkeypatch.setenv("AEGIS_IN_PROCESS_WORKER", "false")
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


async def test_tool_block_returns_403(tool_client):
    login = await tool_client.post(
        "/api/auth/login", json={"username": "u1", "password": "User@12345"}
    )
    token = login.json()["access_token"]
    resp = await tool_client.post(
        "/api/tools/invoke",
        headers={"Authorization": f"Bearer {token}"},
        json={"tool": "delete_user", "arguments": {"user_id": 2}},
    )
    assert resp.status_code == 403
    assert resp.json()["decision"] == "BLOCK"
