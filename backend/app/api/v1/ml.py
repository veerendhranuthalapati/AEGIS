"""ML model management + training endpoints."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ModelVersionOut, TrainRequest
from app.auth.dependencies import CurrentUser, require_permission
from app.auth.permissions import MODELS_READ, MODELS_TRAIN
from app.config import get_settings
from app.database import get_session
from app.ml.dataset import generate_synthetic_dataset
from app.ml.features import REQUEST_FEATURES
from app.ml.registry import activate_version, list_versions, set_status
from app.models import ModelPrediction, ModelVersion
from app.services.audit import log_audit

router = APIRouter(prefix="/ml", tags=["ml"])
settings = get_settings()
logger = structlog.get_logger("aegis.ml_api")

_training: dict[str, bool] = {}


@router.get("/models", response_model=list[ModelVersionOut])
async def list_models(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(MODELS_READ))],
):
    return await list_versions(session)


@router.get("/models/latest")
async def latest_model(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(MODELS_READ))],
):
    result = await session.execute(
        select(ModelVersion)
        .where(ModelVersion.status == "active")
        .order_by(ModelVersion.version.desc())
        .limit(1)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="No active model")
    return version


@router.post("/train")
async def train(
    body: TrainRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require_permission(MODELS_TRAIN))],
):
    max_size = settings.ml_max_train_size
    if body.size is not None and not (1 <= body.size <= max_size):
        raise HTTPException(
            status_code=422,
            detail=f"Training size must be between 1 and {max_size}",
        )
    if _training.get("in_progress"):
        raise HTTPException(status_code=409, detail="Training already in progress")
    _training["in_progress"] = True

    result = await session.execute(select(func.max(ModelVersion.version)))
    next_version = (result.scalar_one() or 0) + 1

    await log_audit(
        session,
        action="ml.train_start",
        actor_id=user.id,
        details={"size": body.size, "version": next_version},
    )
    await session.commit()

    def _run() -> dict[str, Any]:
        from app.ml.pipeline import save_models, train_models

        df = generate_synthetic_dataset(size=body.size, seed=body.seed)
        trained = train_models(df, version=next_version)
        artifact_dir = Path(settings.ml_model_dir)
        paths = save_models(trained, artifact_dir)
        return {"trained": trained, "paths": paths}

    try:
        train_out = await asyncio.to_thread(_run)
        trained = train_out["trained"]
        paths = train_out["paths"]
    except Exception as exc:  # noqa: BLE001
        _training["in_progress"] = False
        logger.error("ml.train_failed", error=str(exc))
        raise HTTPException(
            status_code=500,
            detail="Training failed. Check server logs for details.",
        ) from exc
    finally:
        _training["in_progress"] = False

    from datetime import datetime, timezone

    record = ModelVersion(
        name=f"aegis-{trained.version}",
        algorithm="isolation_forest+random_forest",
        version=trained.version,
        status="active",
        metrics=trained.metrics,
        feature_names=REQUEST_FEATURES,
        artifact_path=Path(paths["isolation_forest"]).parent.as_posix(),
        training_size=trained.metrics["training_size"],
        description="Synthetic dataset (documented). Unsupervised Isolation Forest + supervised Random Forest.",
        trained_at=datetime.now(timezone.utc),
    )
    session.add(record)
    await session.flush()
    await activate_version(session, record.id)
    return record


@router.post("/models/{version_id}/activate")
async def activate(
    version_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require_permission(MODELS_TRAIN))],
):
    await activate_version(session, version_id)
    await log_audit(
        session,
        action="ml.activate",
        actor_id=user.id,
        target_type="model",
        target_id=version_id,
    )
    await session.commit()
    return {"detail": "activated"}


@router.post("/models/{version_id}/deprecate")
async def deprecate(
    version_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require_permission(MODELS_TRAIN))],
):
    await set_status(session, version_id, "deprecated")
    await log_audit(
        session,
        action="ml.deprecate",
        actor_id=user.id,
        target_type="model",
        target_id=version_id,
    )
    await session.commit()
    return {"detail": "deprecated"}


@router.get("/predictions")
async def list_predictions(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(MODELS_READ))],
    limit: int = 100,
):
    result = await session.execute(
        select(ModelPrediction)
        .order_by(ModelPrediction.created_at.desc())
        .limit(min(limit, 500))
    )
    return list(result.scalars().all())
