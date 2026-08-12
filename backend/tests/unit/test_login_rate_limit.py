"""Login endpoint rate-limit regression tests.

Uses an isolated in-memory SQLite database so tests do not depend on
PostgreSQL state or interfere with other suites.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.models import Base, RateLimitState
from app.services.ratelimit import check_rate_limit

settings = get_settings()
BRUTE_FORCE_TEST_IP = "198.18.0.99"


@pytest.fixture
async def rate_db(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    import app.database.session as db_session

    monkeypatch.setattr(db_session, "async_session_factory", factory)
    monkeypatch.setattr(db_session, "engine", engine)

    yield factory
    await engine.dispose()


async def _reset_bucket(session_factory, ip: str) -> None:
    async with session_factory() as session:
        await session.execute(
            RateLimitState.__table__.delete().where(
                RateLimitState.bucket_key == f"login:{ip}"
            )
        )
        await session.commit()


async def test_service_rate_limit_blocks_after_limit(rate_db):
    key = "login:127.0.0.1"
    limit = settings.login_rate_limit_per_min
    for i in range(limit + 2):
        async with rate_db() as session:
            allowed, count, _ = await check_rate_limit(session, key=key, limit=limit)
        if i < limit:
            assert allowed is True, f"attempt {i + 1} should be allowed"
        else:
            assert allowed is False, f"attempt {i + 1} should be rate limited"
            assert count >= limit


async def test_failed_logins_eventually_return_429_postgres():
    """Integration test against the configured database (PostgreSQL in dev)."""
    from app.main import app

    await _reset_bucket_direct("198.18.0.55")
    transport = ASGITransport(app=app)
    headers = {"X-Forwarded-For": "198.18.0.55"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        codes: list[int] = []
        for i in range(settings.login_rate_limit_per_min + 2):
            r = await client.post(
                "/api/auth/login",
                headers=headers,
                json={"username": "nobody", "password": f"wrong-{i}"},
            )
            codes.append(r.status_code)
        assert 429 in codes


async def _reset_bucket_direct(ip: str) -> None:
    from app.database import async_session_factory

    async with async_session_factory() as session:
        await session.execute(
            RateLimitState.__table__.delete().where(
                RateLimitState.bucket_key == f"login:{ip}"
            )
        )
        await session.commit()


async def test_failed_logins_eventually_return_429(rate_db, monkeypatch):
    from app.main import app

    await _reset_bucket(rate_db, "127.0.0.1")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        codes: list[int] = []
        for i in range(settings.login_rate_limit_per_min + 2):
            r = await client.post(
                "/api/auth/login",
                json={"username": "nobody", "password": f"wrong-{i}"},
            )
            codes.append(r.status_code)
        assert codes[: settings.login_rate_limit_per_min] == [401] * settings.login_rate_limit_per_min
        assert 429 in codes[settings.login_rate_limit_per_min :]


async def test_isolated_ip_via_forwarded_for_gets_own_bucket(rate_db):
    from app.main import app

    await _reset_bucket(rate_db, BRUTE_FORCE_TEST_IP)
    transport = ASGITransport(app=app)
    headers = {"X-Forwarded-For": BRUTE_FORCE_TEST_IP}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        codes: list[int] = []
        for i in range(settings.login_rate_limit_per_min + 2):
            r = await client.post(
                "/api/auth/login",
                headers=headers,
                json={"username": "nobody", "password": f"wrong-{i}"},
            )
            codes.append(r.status_code)
        assert 429 in codes
        assert codes.index(429) == settings.login_rate_limit_per_min


async def test_unknown_ip_bucket(rate_db):
    async with rate_db() as session:
        allowed, _, _ = await check_rate_limit(
            session, key="login:unknown", limit=settings.login_rate_limit_per_min
        )
        assert allowed is True
