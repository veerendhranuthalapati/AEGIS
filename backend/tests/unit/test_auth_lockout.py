"""Account lockout tests: permanent-lockout DoS regression.

Requires: a failed login locks the account, but the lock auto-expires
after ``auth_lockout_minutes`` so an attacker cannot permanently lock a
target account (CWE-307 / account lockout DoS).
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.password import hash_password
from app.auth.service import AuthError, authenticate_user
from app.config import get_settings
from app.models import Base, Role, User

settings = get_settings()


@pytest.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as ses:
        yield ses
    await engine.dispose()


async def _make_user(session, username: str = "target") -> User:
    role = Role(name="user", description="standard user")
    session.add(role)
    await session.flush()
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=hash_password("Correct@1234"),
        full_name="Target User",
        role_id=role.id,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    return user


async def test_wrong_password_increments_then_locks(session):
    await _make_user(session)
    for i in range(settings.auth_lockout_max_failed - 1):
        with pytest.raises(AuthError):
            await authenticate_user(session, "target", f"wrong-{i}")
    with pytest.raises(AuthError):
        await authenticate_user(session, "target", "wrong-final")
    from sqlalchemy import select

    result = await session.execute(select(User).where(User.username == "target"))
    user = result.scalar_one()
    assert user.is_locked is True
    assert user.locked_at is not None


async def test_correct_password_rejected_while_locked(session):
    await _make_user(session)
    for i in range(settings.auth_lockout_max_failed):
        with pytest.raises(AuthError):
            await authenticate_user(session, "target", f"wrong-{i}")
    with pytest.raises(AuthError):
        await authenticate_user(session, "target", "Correct@1234")


async def test_lockout_auto_expires_after_window(session):
    await _make_user(session)
    for i in range(settings.auth_lockout_max_failed):
        with pytest.raises(AuthError):
            await authenticate_user(session, "target", f"wrong-{i}")

    from sqlalchemy import select

    result = await session.execute(select(User).where(User.username == "target"))
    user = result.scalar_one()
    user.locked_at = datetime.now(timezone.utc) - timedelta(
        minutes=settings.auth_lockout_minutes + 1
    )
    await session.commit()

    user = await authenticate_user(session, "target", "Correct@1234")
    assert user.is_locked is False
    assert user.locked_at is None
    assert user.failed_login_count == 0


async def test_lockout_reset_on_success(session):
    await _make_user(session)
    user = await authenticate_user(session, "target", "Correct@1234")
    assert user.is_locked is False
    assert user.locked_at is None
    assert user.failed_login_count == 0
