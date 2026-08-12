"""Integration tests for the security-event worker correlation path."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base, Incident, SecurityEvent
from app.worker.main import _process_batch


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


def _event(event_id: str, event_type: str, correlation_key: str) -> SecurityEvent:
    event = SecurityEvent(
        event_id=event_id,
        event_type=event_type,
        severity="HIGH",
        correlation_key=correlation_key,
        endpoint="/api/gateway/v1/chat",
        mitre_techniques=["T1078"],
    )
    event.timestamp = datetime.now(timezone.utc)
    return event


async def _incident_count(session) -> int:
    result = await session.execute(select(func.count(Incident.id)))
    return int(result.scalar_one())


async def test_recent_incident_suppresses_duplicate(session):
    settings = SimpleNamespace(correlation_window_seconds=900)
    events = [
        _event("ev-1", "PROMPT_INJECTION", "attacker-1"),
        _event("ev-2", "JAILBREAK_ATTEMPT", "attacker-1"),
        _event("ev-3", "SYSTEM_PROMPT_EXTRACTION", "attacker-1"),
    ]
    await _process_batch(session, events, settings)
    assert await _incident_count(session) == 1

    # A second burst for the same attacker within the window must NOT create
    # a second incident.
    more = [
        _event("ev-4", "PROMPT_INJECTION", "attacker-1"),
        _event("ev-5", "SENSITIVE_EXTRACTION", "attacker-1"),
        _event("ev-6", "TOOL_ABUSE", "attacker-1"),
    ]
    await _process_batch(session, more, settings)
    assert await _incident_count(session) == 1


async def test_stale_incident_opens_new_window(session):
    settings = SimpleNamespace(correlation_window_seconds=900)
    events = [
        _event("ev-1", "PROMPT_INJECTION", "attacker-2"),
        _event("ev-2", "JAILBREAK_ATTEMPT", "attacker-2"),
        _event("ev-3", "SYSTEM_PROMPT_EXTRACTION", "attacker-2"),
    ]
    await _process_batch(session, events, settings)
    assert await _incident_count(session) == 1

    # Age the existing incident past the correlation window.
    result = await session.execute(select(Incident))
    incident = result.scalar_one()
    incident.updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
    incident.last_seen = datetime.now(timezone.utc) - timedelta(hours=1)
    await session.commit()

    more = [
        _event("ev-4", "PROMPT_INJECTION", "attacker-2"),
        _event("ev-5", "SENSITIVE_EXTRACTION", "attacker-2"),
        _event("ev-6", "TOOL_ABUSE", "attacker-2"),
    ]
    await _process_batch(session, more, settings)
    assert await _incident_count(session) == 2
