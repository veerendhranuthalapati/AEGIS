"""Unit tests for incident correlation windowing."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base, Incident
from app.services.incidents import find_open_incident


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


async def _add_incident(
    session,
    *,
    attacker_key: str,
    attack_type: str,
    status: str = "OPEN",
    updated_at: datetime | None = None,
) -> Incident:
    incident = Incident(
        incident_number=1,
        title="Probe incident",
        attack_type=attack_type,
        attacker_key=attacker_key,
        status=status,
    )
    if updated_at is not None:
        incident.updated_at = updated_at
    session.add(incident)
    await session.commit()
    await session.refresh(incident)
    return incident


async def test_stale_open_incident_not_reused(session):
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    await _add_incident(
        session, attacker_key="attacker-a", attack_type="prompt-injection", updated_at=old
    )
    found = await find_open_incident(
        session, "attacker-a", "prompt-injection", window_seconds=900
    )
    assert found is None


async def test_recent_open_incident_reused(session):
    fresh = datetime.now(timezone.utc)
    await _add_incident(
        session, attacker_key="attacker-b", attack_type="sql-injection", updated_at=fresh
    )
    found = await find_open_incident(
        session, "attacker-b", "sql-injection", window_seconds=900
    )
    assert found is not None
    assert found.status in ("OPEN", "INVESTIGATING")


async def test_closed_incident_never_reused(session):
    fresh = datetime.now(timezone.utc)
    await _add_incident(
        session,
        attacker_key="attacker-c",
        attack_type="brute-force",
        status="RESOLVED",
        updated_at=fresh,
    )
    found = await find_open_incident(
        session, "attacker-c", "brute-force", window_seconds=900
    )
    assert found is None


async def test_missing_attacker_key_returns_none(session):
    assert await find_open_incident(session, None, "any") is None
