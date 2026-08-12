"""Live threat feed endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, require_permission
from app.auth.permissions import EVENTS_READ
from app.database import get_session
from app.models import IpBlock, SecurityEvent

router = APIRouter(prefix="/threats", tags=["threats"])


@router.get("/live")
async def live_threats(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(EVENTS_READ))],
    minutes: int = 60,
    limit: int = 50,
):
    since = datetime.now(timezone.utc) - timedelta(minutes=min(minutes, 1440))
    result = await session.execute(
        select(SecurityEvent)
        .where(
            SecurityEvent.timestamp >= since,
            SecurityEvent.severity.in_(["MEDIUM", "HIGH", "CRITICAL"]),
        )
        .order_by(SecurityEvent.timestamp.desc())
        .limit(min(limit, 200))
    )
    return [
        {
            "event_id": e.event_id,
            "timestamp": e.timestamp,
            "event_type": e.event_type,
            "severity": e.severity,
            "actor_id": e.actor_id,
            "source_ip": e.source_ip,
            "endpoint": e.endpoint,
            "risk_score": e.risk_score,
            "decision": e.decision,
            "reasons": e.reasons,
            "mitre_techniques": e.mitre_techniques,
            "incident_id": e.incident_id,
        }
        for e in result.scalars().all()
    ]


@router.get("/blocked-ips")
async def blocked_ips(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(EVENTS_READ))],
):
    result = await session.execute(
        select(IpBlock).where(IpBlock.is_active == True).order_by(IpBlock.created_at.desc())  # noqa: E712
    )
    return [
        {
            "id": block.id,
            "ip": block.ip,
            "reason": block.reason,
            "created_at": block.created_at,
            "expires_at": block.expires_at,
        }
        for block in result.scalars().all()
    ]
