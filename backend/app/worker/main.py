"""Asynchronous security-event worker.

Claims unprocessed security events, correlates them into incidents, and
records the result. Runs as its own process (``python -m app.worker.main``)
or in-process via the FastAPI lifespan.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.database.session import async_session_factory, dispose_engine
from app.metrics import observe_worker
from app.models import SecurityEvent
from app.security.correlation.engine import EventLike, correlate
from app.services.incidents import create_incident, find_open_incident

logger = structlog.get_logger("aegis.worker")

_STALE_CLAIM_SECONDS = 300
_WORKER_ID = f"worker-{uuid.uuid4().hex[:8]}"


async def _claim_events(
    session: AsyncSession, limit: int
) -> list[SecurityEvent]:
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(seconds=_STALE_CLAIM_SECONDS)
    result = await session.execute(
        select(SecurityEvent)
        .where(
            SecurityEvent.processed == False,  # noqa: E712
            SecurityEvent.worker_claim.is_(None)
            | (SecurityEvent.claimed_at < stale_before),
        )
        .order_by(SecurityEvent.timestamp.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    events = list(result.scalars().all())
    if events:
        for event in events:
            event.worker_claim = _WORKER_ID
            event.claimed_at = now
        await session.commit()
    return events


async def _process_batch(session: AsyncSession, events: list[SecurityEvent], settings) -> None:
    if not events:
        return
    batch_start = time.perf_counter()

    event_like = [
        EventLike(
            event_id=e.event_id,
            event_type=e.event_type,
            timestamp=e.timestamp,
            severity=e.severity,
            actor_id=e.actor_id,
            source_ip=e.source_ip,
            endpoint=e.endpoint,
            correlation_key=e.correlation_key,
            mitre=e.mitre_techniques or [],
        )
        for e in events
    ]

    corr_start = time.perf_counter()
    suggestions = correlate(event_like)
    correlation_ms = (time.perf_counter() - corr_start) * 1000

    for suggestion in suggestions:
        # Skip if a recently-active open incident already exists for this
        # subject/type; a stale incident opens a new correlation window.
        existing = await find_open_incident(
            session,
            attacker_key=suggestion.attacker_key,
            attack_type=suggestion.attack_type,
            window_seconds=settings.correlation_window_seconds,
        )
        if existing is not None:
            continue

        incident = await create_incident(
            session,
            title=suggestion.title,
            attack_type=suggestion.attack_type,
            severity=suggestion.severity,
            confidence=suggestion.confidence,
            description=suggestion.description,
            timeline=suggestion.timeline,
            mitre=suggestion.mitre,
            related_event_ids=suggestion.related_event_ids,
            attacker_key=suggestion.attacker_key,
        )
        logger.info(
            "incident.created",
            incident_number=incident.incident_number,
            attack_type=suggestion.attack_type,
            severity=suggestion.severity,
            confidence=suggestion.confidence,
        )

        event_ids = set(suggestion.related_event_ids)
        for event in events:
            if event.event_id in event_ids:
                event.incident_id = incident.id

    for event in events:
        event.processed = True
        event.worker_claim = None
        event.claimed_at = None
    await session.commit()
    observe_worker(
        correlation_ms=correlation_ms,
        batch_ms=(time.perf_counter() - batch_start) * 1000,
        processed=len(events),
    )


async def run_worker_forever(session_factory: async_sessionmaker[AsyncSession], settings) -> None:
    logger.info("worker.start", worker_id=_WORKER_ID)
    while True:
        try:
            async with session_factory() as session:
                events = await _claim_events(session, settings.event_batch_size)
                if events:
                    await _process_batch(session, events, settings)
        except Exception:  # noqa: BLE001
            logger.exception("worker.batch_error")
        await asyncio.sleep(settings.event_poll_interval_seconds)


async def main() -> None:
    settings = get_settings()
    await run_worker_forever(async_session_factory, settings)
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
