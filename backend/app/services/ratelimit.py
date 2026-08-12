"""Persistent fixed-window rate limiting backed by the database.

Increments are performed with a single atomic ``UPDATE ... RETURNING`` so
concurrent requests cannot race past the limit (TOCTOU-safe). The upsert
falls back to the SQLite dialect so the app runs identically on the local
dev database.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RateLimitState


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def check_rate_limit(
    session: AsyncSession,
    *,
    key: str,
    limit: int,
    window_seconds: int = 60,
) -> tuple[bool, int, int]:
    """Return (allowed, current_count, reset_seconds)."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=window_seconds)

    # Atomic increment of an existing, unexpired bucket.
    stmt = (
        update(RateLimitState)
        .where(
            RateLimitState.bucket_key == key,
            RateLimitState.window_start >= window_start,
        )
        .values(count=RateLimitState.count + 1)
        .returning(RateLimitState.count, RateLimitState.window_start)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is not None:
        count, start = row
        if count > limit:
            elapsed = (now - _as_utc(start)).total_seconds()
            reset = max(1, int(window_seconds - elapsed))
            await session.commit()
            return False, count - 1, reset
        await session.commit()
        return True, count, window_seconds

    # No live bucket: create one (or reset an expired bucket atomically).
    dialect = session.get_bind().dialect.name
    insert_cls = sqlite_insert if dialect == "sqlite" else pg_insert
    ins = (
        insert_cls(RateLimitState)
        .values(
            bucket_key=key,
            window_start=now,
            count=1,
            limit=limit,
        )
        .on_conflict_do_update(
            index_elements=[RateLimitState.bucket_key],
            set_={
                "window_start": now,
                "count": 1,
                "limit": limit,
            },
        )
        .returning(RateLimitState.count)
    )
    result = await session.execute(ins)
    count = result.scalar_one_or_none() or 1
    await session.commit()
    return True, count, window_seconds
