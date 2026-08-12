"""Behavioral analytics over stored gateway telemetry.

These aggregates feed the deterministic rules, the ML feature vector and the
risk engine. They are computed from real ``api_requests`` data.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApiRequest, Session, User

_RATE_WINDOW_24H = timedelta(hours=24)
_BURST_WINDOW = timedelta(minutes=5)
_STATS_WINDOW = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def collect_request_stats(
    session: AsyncSession,
    *,
    actor_id: str | None,
    source_ip: str | None,
    current_endpoint: str,
) -> dict:
    """Compute behavioral aggregates for rules, features and risk."""
    now = _now()
    stats: dict = {
        "request_rate_per_min": 0.0,
        "baseline_rate_per_min": 0.0,
        "request_rate_ratio": 0.0,
        "unique_endpoints_1h": 0,
        "auth_failures_5min": 0,
        "not_found_5min": 0,
        "distinct_endpoints_5min": 0,
        "new_device": False,
        "geo_change": False,
        "token_age_hours": None,
        "account_age_days": 0,
        "endpoint_rarity": 1.0,
        "device_count_7d": 0,
    }

    if actor_id is None:
        return stats

    # request rate (last 5 min) vs baseline (prior 24h minus 5 min)
    burst_start = now - _BURST_WINDOW
    base_end = now - _BURST_WINDOW
    base_start = now - _RATE_WINDOW_24H

    burst_count = await _count_requests(session, actor_id, burst_start, now)
    base_count = await _count_requests(session, actor_id, base_start, base_end)
    burst_mins = _BURST_WINDOW.total_seconds() / 60
    base_mins = max(1.0, (base_end - base_start).total_seconds() / 60)
    rate = burst_count / max(burst_mins, 0.01)
    baseline = base_count / base_mins
    stats["request_rate_per_min"] = rate
    stats["baseline_rate_per_min"] = baseline
    stats["request_rate_ratio"] = rate / max(baseline, 1.0)

    stats["unique_endpoints_1h"] = await _unique_endpoints(
        session, actor_id, now - timedelta(hours=1)
    )

    # auth failures over 5 min (login attempts that produced 401)
    failed = await session.execute(
        select(func.count(ApiRequest.id)).where(
            ApiRequest.actor_id.is_(None),
            ApiRequest.source_ip == source_ip,
            ApiRequest.timestamp >= burst_start,
            ApiRequest.status_code == 401,
        )
    )
    stats["auth_failures_5min"] = failed.scalar_one() or 0

    not_found = await session.execute(
        select(func.count(ApiRequest.id)).where(
            (ApiRequest.actor_id == actor_id)
            | (ApiRequest.source_ip == source_ip),
            ApiRequest.timestamp >= burst_start,
            ApiRequest.status_code.in_([404, 403]),
        )
    )
    stats["not_found_5min"] = not_found.scalar_one() or 0

    distinct = await session.execute(
        select(func.count(func.distinct(ApiRequest.endpoint))).where(
            (ApiRequest.actor_id == actor_id)
            | (ApiRequest.source_ip == source_ip),
            ApiRequest.timestamp >= burst_start,
        )
    )
    stats["distinct_endpoints_5min"] = distinct.scalar_one() or 0

    # endpoint rarity: how often this endpoint appears in the last 24h
    rarity = await session.execute(
        select(func.count(ApiRequest.id)).where(
            (ApiRequest.actor_id == actor_id),
            ApiRequest.endpoint == current_endpoint,
            ApiRequest.timestamp >= now - timedelta(hours=24),
        )
    )
    count = rarity.scalar_one() or 0
    stats["endpoint_rarity"] = 1.0 / (1.0 + count)

    # device / geo signals
    recent = await session.execute(
        select(func.count(func.distinct(ApiRequest.device_id))).where(
            ApiRequest.actor_id == actor_id,
            ApiRequest.timestamp >= now - timedelta(days=7),
        )
    )
    stats["device_count_7d"] = recent.scalar_one() or 0

    ses_result = await session.execute(
        select(Session).where(
            Session.user_id == actor_id, Session.is_active == True  # noqa: E712
        )
    )
    sessions = list(ses_result.scalars().all())
    if sessions:
        stats["new_device"] = stats["device_count_7d"] == 0

    user = await session.get(User, actor_id)
    if user and user.created_at:
        stats["account_age_days"] = max(
            0, (now - user.created_at).total_seconds() / 86400
        )

    return stats


async def _count_requests(
    session: AsyncSession, actor_id: str, start: datetime, end: datetime
) -> int:
    result = await session.execute(
        select(func.count(ApiRequest.id)).where(
            ApiRequest.actor_id == actor_id,
            ApiRequest.timestamp >= start,
            ApiRequest.timestamp < end,
        )
    )
    return result.scalar_one() or 0


async def _unique_endpoints(
    session: AsyncSession, actor_id: str, since: datetime
) -> int:
    result = await session.execute(
        select(func.count(func.distinct(ApiRequest.endpoint))).where(
            ApiRequest.actor_id == actor_id,
            ApiRequest.timestamp >= since,
        )
    )
    return result.scalar_one() or 0


def token_age_hours(created_at: datetime | None) -> float | None:
    if created_at is None:
        return None
    return (datetime.now(timezone.utc) - created_at).total_seconds() / 3600
