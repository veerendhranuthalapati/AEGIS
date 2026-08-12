"""Incidents endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import IncidentOut, IncidentUpdate
from app.auth.dependencies import CurrentUser, require_permission
from app.auth.permissions import INCIDENTS_READ, INCIDENTS_WRITE
from app.database import get_session
from app.metrics import observe_incident
from app.models import Incident
from app.services.audit import log_audit

router = APIRouter(prefix="/incidents", tags=["incidents"])

_CLOSED_STATUSES = {"RESOLVED", "CLOSED"}


@router.get("", response_model=list[IncidentOut])
async def list_incidents(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(INCIDENTS_READ))],
    status_filter: str | None = None,
    severity: str | None = None,
    limit: int = 100,
):
    query = select(Incident).order_by(Incident.created_at.desc()).limit(limit)
    if status_filter:
        query = query.where(Incident.status == status_filter)
    if severity:
        query = query.where(Incident.severity == severity)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/{incident_id}", response_model=IncidentOut)
async def get_incident(
    incident_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(INCIDENTS_READ))],
):
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.patch("/{incident_id}", response_model=IncidentOut)
async def update_incident(
    incident_id: str,
    body: IncidentUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require_permission(INCIDENTS_WRITE))],
):
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    was_open = incident.status not in _CLOSED_STATUSES
    if body.status is not None:
        incident.status = body.status
    if body.severity is not None:
        incident.severity = body.severity
    if body.description is not None:
        incident.description = body.description
    now_open = incident.status not in _CLOSED_STATUSES
    if was_open and not now_open:
        observe_incident(incident.severity, -1)
    elif not was_open and now_open:
        observe_incident(incident.severity, +1)
    await log_audit(
        session,
        action="incidents.update",
        actor_id=user.id,
        target_type="incident",
        target_id=incident_id,
        details={"status": incident.status, "severity": incident.severity},
    )
    await session.commit()
    return incident
