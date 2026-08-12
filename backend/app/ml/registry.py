"""Model registry (database-backed)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModelVersion


async def get_latest_active(session: AsyncSession) -> ModelVersion | None:
    result = await session.execute(
        select(ModelVersion)
        .where(ModelVersion.status == "active")
        .order_by(ModelVersion.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_version(
    session: AsyncSession,
    *,
    name: str,
    algorithm: str,
    version: int,
    metrics: dict,
    artifact_path: str | None,
    feature_names: list[str],
    training_size: int,
    description: str | None = None,
) -> ModelVersion:
    record = ModelVersion(
        name=name,
        algorithm=algorithm,
        version=version,
        status="training",
        metrics=metrics,
        artifact_path=artifact_path,
        feature_names=feature_names,
        training_size=training_size,
        description=description,
    )
    session.add(record)
    await session.flush()
    return record


async def set_status(
    session: AsyncSession, version_id: str, status: str
) -> None:
    record = await session.get(ModelVersion, version_id)
    if record is None:
        return
    record.status = status
    if status == "active":
        record.trained_at = datetime.now(timezone.utc)
    await session.commit()


async def activate_version(
    session: AsyncSession, version_id: str
) -> None:
    """Set all versions to deprecated except the chosen one (active)."""
    result = await session.execute(select(ModelVersion))
    for record in result.scalars().all():
        if record.id == version_id:
            record.status = "active"
            record.trained_at = datetime.now(timezone.utc)
        else:
            record.status = "deprecated"
    await session.commit()


async def list_versions(session: AsyncSession) -> list[ModelVersion]:
    result = await session.execute(
        select(ModelVersion).order_by(ModelVersion.version.desc())
    )
    return list(result.scalars().all())
