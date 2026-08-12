"""Analytics endpoints — all values computed from real stored data."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import OverviewStats
from app.auth.dependencies import CurrentUser, require_permission
from app.auth.permissions import EVENTS_READ
from app.database import get_session
from app.models import ApiRequest, Approval, Incident, SecurityEvent

router = APIRouter(prefix="/analytics", tags=["analytics"])

_NOW = datetime.now(timezone.utc)


@router.get("/overview", response_model=OverviewStats)
async def overview(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(EVENTS_READ))],
):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    total = await session.execute(select(func.count(ApiRequest.id)))
    blocked = await session.execute(
        select(func.count(ApiRequest.id)).where(ApiRequest.decision == "BLOCK")
    )
    incidents = await session.execute(
        select(func.count(Incident.id)).where(
            Incident.status.in_(["OPEN", "INVESTIGATING"])
        )
    )
    approvals = await session.execute(
        select(func.count(Approval.id)).where(Approval.status == "pending")
    )
    recent_risk = await session.execute(
        select(func.avg(ApiRequest.risk_score)).where(
            ApiRequest.timestamp >= now - timedelta(minutes=15)
        )
    )

    # requests per hour (24h)
    hourly = await session.execute(
        select(
            func.date_trunc("hour", ApiRequest.timestamp).label("hour"),
            func.count(ApiRequest.id),
        )
        .where(ApiRequest.timestamp >= day_ago)
        .group_by("hour")
        .order_by("hour")
    )
    requests_24h = [
        {"hour": h.isoformat(), "count": c} for h, c in hourly.all()
    ]

    # top attacking IPs (non-allowed decisions)
    top_ips = await session.execute(
        select(
            ApiRequest.source_ip,
            func.count(ApiRequest.id).label("count"),
            func.count(
                func.nullif(ApiRequest.decision.in_(["BLOCK", "REQUIRE_REVIEW", "WARN"]), True)
            ).label("threat_count"),
        )
        .where(ApiRequest.source_ip.isnot(None), ApiRequest.timestamp >= day_ago)
        .group_by(ApiRequest.source_ip)
        .order_by(func.count(ApiRequest.id).desc())
        .limit(10)
    )
    top_attacking_ips = [
        {"ip": ip, "requests": count, "threats": threat}
        for ip, count, threat in top_ips.all()
    ]

    # riskiest users
    top_users = await session.execute(
        select(
            ApiRequest.actor_id,
            func.avg(ApiRequest.risk_score).label("avg_risk"),
            func.count(ApiRequest.id).label("count"),
        )
        .where(ApiRequest.actor_id.isnot(None), ApiRequest.timestamp >= day_ago)
        .group_by(ApiRequest.actor_id)
        .order_by(func.avg(ApiRequest.risk_score).desc())
        .limit(10)
    )
    top_risk_users = [
        {"actor_id": uid, "avg_risk": round(float(risk or 0), 1), "requests": count}
        for uid, risk, count in top_users.all()
    ]

    # event counts by type (24h)
    event_counts = await session.execute(
        select(SecurityEvent.event_type, func.count(SecurityEvent.id))
        .where(SecurityEvent.timestamp >= day_ago)
        .group_by(SecurityEvent.event_type)
        .order_by(func.count(SecurityEvent.id).desc())
    )
    event_counts_by_type = [
        {"event_type": t, "count": c} for t, c in event_counts.all()
    ]

    # decisions today
    decisions = await session.execute(
        select(ApiRequest.decision, func.count(ApiRequest.id))
        .where(
            ApiRequest.timestamp >= day_ago, ApiRequest.decision.isnot(None)
        )
        .group_by(ApiRequest.decision)
    )
    decisions_today = [
        {"decision": d, "count": c} for d, c in decisions.all()
    ]

    # attack type breakdown from incident attack_type
    attack_types = await session.execute(
        select(Incident.attack_type, func.count(Incident.id))
        .where(Incident.attack_type.isnot(None))
        .group_by(Incident.attack_type)
        .order_by(func.count(Incident.id).desc())
    )
    attack_types_list = [
        {"attack_type": t, "count": c} for t, c in attack_types.all()
    ]

    return OverviewStats(
        total_requests=int(total.scalar_one() or 0),
        blocked_requests=int(blocked.scalar_one() or 0),
        active_incidents=int(incidents.scalar_one() or 0),
        open_approvals=int(approvals.scalar_one() or 0),
        current_risk=round(float(recent_risk.scalar_one() or 0), 1),
        requests_24h=requests_24h,
        top_attacking_ips=top_attacking_ips,
        top_risk_users=top_risk_users,
        attack_types=attack_types_list,
        event_counts_by_type=event_counts_by_type,
        decisions_today=decisions_today,
    )


@router.get("/requests")
async def requests_timeseries(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(EVENTS_READ))],
    hours: int = 24,
):
    since = datetime.now(timezone.utc) - timedelta(hours=min(hours, 168))
    result = await session.execute(
        select(
            func.date_trunc("hour", ApiRequest.timestamp).label("hour"),
            func.count(ApiRequest.id).label("count"),
            func.count(func.nullif(ApiRequest.decision == "BLOCK", False)).label("blocked"),
            func.avg(ApiRequest.risk_score).label("avg_risk"),
        )
        .where(ApiRequest.timestamp >= since)
        .group_by("hour")
        .order_by("hour")
    )
    return [
        {
            "hour": h.isoformat(),
            "count": count,
            "blocked": int(blocked),
            "avg_risk": round(float(avg_risk or 0), 2),
        }
        for h, count, blocked, avg_risk in result.all()
    ]


@router.get("/attack-timeline")
async def attack_timeline(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(EVENTS_READ))],
    limit: int = 50,
):
    """Chronological attack activity stream used by the Attack Timeline page."""
    result = await session.execute(
        select(SecurityEvent)
        .where(
            SecurityEvent.severity.in_(["MEDIUM", "HIGH", "CRITICAL"])
        )
        .order_by(SecurityEvent.timestamp.desc())
        .limit(min(limit, 200))
    )
    events = list(result.scalars().all())
    incidents = await session.execute(
        select(Incident).order_by(Incident.created_at.desc()).limit(20)
    )
    items = []
    for event in events:
        items.append(
            {
                "timestamp": event.timestamp,
                "kind": "event",
                "label": event.event_type,
                "severity": event.severity,
                "actor": event.actor_id,
                "ip": event.source_ip,
                "endpoint": event.endpoint,
                "risk": event.risk_score,
                "incident_id": event.incident_id,
            }
        )
    for incident in list(incidents.scalars().all()):
        items.append(
            {
                "timestamp": incident.created_at,
                "kind": "incident",
                "label": incident.title,
                "severity": incident.severity,
                "actor": incident.attacker_key,
                "ip": None,
                "endpoint": None,
                "risk": incident.confidence,
                "incident_id": incident.id,
            }
        )
    items.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
    return items[:limit]
