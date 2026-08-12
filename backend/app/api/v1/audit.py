"""Audit log endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AuditLogOut
from app.auth.dependencies import CurrentUser, require_permission
from app.auth.permissions import AUDIT_READ
from app.database import get_session
from app.models import AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
async def list_audit(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(AUDIT_READ))],
    action: str | None = None,
    actor_id: str | None = None,
    limit: int = 200,
):
    query = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(min(limit, 1000))
    if action:
        query = query.where(AuditLog.action == action)
    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)
    result = await session.execute(query)
    return list(result.scalars().all())
