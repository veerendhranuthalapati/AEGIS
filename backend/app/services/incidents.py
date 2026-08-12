"""Incident persistence helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.metrics import observe_incident
from app.models import Incident


async def next_incident_number(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.coalesce(func.max(Incident.incident_number), 0))
    )
    return int(result.scalar_one()) + 1


async def find_open_incident(
    session: AsyncSession,
    attacker_key: str | None,
    attack_type: str | None,
    window_seconds: int = 900,
) -> Incident | None:
    """Find a recently-active open incident for this attacker/type.

    Only incidents updated within ``window_seconds`` are considered so a stale
    incident never suppresses a new correlation window for the same subject.
    """
    if not attacker_key:
        return None
    since = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    result = await session.execute(
        select(Incident).where(
            Incident.attacker_key == attacker_key,
            Incident.attack_type == attack_type,
            Incident.status.in_(["OPEN", "INVESTIGATING"]),
            Incident.updated_at >= since,
        )
    )
    return result.scalar_one_or_none()


async def create_incident(
    session: AsyncSession,
    *,
    title: str,
    attack_type: str,
    severity: str,
    confidence: float,
    description: str | None,
    timeline: list,
    mitre: list[str],
    related_event_ids: list[str],
    attacker_key: str | None,
) -> Incident:
    incident = Incident(
        incident_number=await next_incident_number(session),
        title=title[:256],
        description=description,
        severity=severity,
        status="OPEN",
        confidence=confidence,
        attack_type=attack_type,
        attacker_key=attacker_key,
        timeline=timeline,
        mitre_techniques=mitre,
        related_event_ids=related_event_ids,
        last_seen=datetime.now(timezone.utc),
    )
    session.add(incident)
    await session.flush()
    observe_incident(severity, +1)
    return incident
