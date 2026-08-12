"""Security events endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import SecurityEventOut
from app.auth.dependencies import CurrentUser, require_permission
from app.auth.permissions import EVENTS_READ
from app.database import get_session
from app.models import SecurityEvent

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[SecurityEventOut])
async def list_events(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(EVENTS_READ))],
    event_type: str | None = None,
    severity: str | None = None,
    limit: int = 200,
):
    query = (
        select(SecurityEvent)
        .order_by(SecurityEvent.timestamp.desc())
        .limit(min(limit, 1000))
    )
    if event_type:
        query = query.where(SecurityEvent.event_type == event_type)
    if severity:
        query = query.where(SecurityEvent.severity == severity)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/summary")
async def event_summary(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(EVENTS_READ))],
):
    result = await session.execute(
        select(
            SecurityEvent.event_type,
            func.count(SecurityEvent.id),
            func.max(SecurityEvent.risk_score),
        ).group_by(SecurityEvent.event_type)
    )
    return [
        {"event_type": t, "count": c, "max_risk": r}
        for t, c, r in result.all()
    ]
