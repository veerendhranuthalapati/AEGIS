"""Runtime settings endpoints (secrets never exposed)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser, require_permission
from app.auth.permissions import SETTINGS_WRITE
from app.config import get_settings

router = APIRouter(prefix="/settings", tags=["settings"])


class RiskThresholds(BaseModel):
    risk_low_max: int = Field(ge=0, le=100)
    risk_medium_max: int = Field(ge=0, le=100)
    risk_high_max: int = Field(ge=0, le=100)


class RuntimeSettings(BaseModel):
    ml_enabled: bool | None = None
    auto_block_ip: bool | None = None
    llm_analyzer_enabled: bool | None = None


@router.get("")
async def get_settings_public(
    _: Annotated[CurrentUser, Depends(require_permission(SETTINGS_WRITE))],
):
    settings = get_settings()
    return {
        "app_name": settings.app_name,
        "environment": settings.environment,
        "version": settings.version,
        "risk_thresholds": {
            "low_max": settings.risk_low_max,
            "medium_max": settings.risk_medium_max,
            "high_max": settings.risk_high_max,
            "critical_min": settings.risk_critical_min,
        },
        "ml_enabled": settings.ml_enabled,
        "auto_block_ip": settings.auto_block_ip,
        "llm_analyzer_enabled": settings.llm_analyzer_enabled,
        "llm_provider": settings.llm_provider,
        "gateway_rate_limit_auth_per_min": settings.gateway_rate_limit_auth_per_min,
        "gateway_rate_limit_anon_per_min": settings.gateway_rate_limit_anon_per_min,
        "login_rate_limit_per_min": settings.login_rate_limit_per_min,
        "max_request_body_bytes": settings.max_request_body_bytes,
        "max_response_body_bytes": settings.max_response_body_bytes,
        "correlation_window_seconds": settings.correlation_window_seconds,
    }


@router.patch("/risk-thresholds")
async def set_risk_thresholds(
    body: RiskThresholds,
    _: Annotated[CurrentUser, Depends(require_permission(SETTINGS_WRITE))],
):
    settings = get_settings()
    if not (body.risk_low_max < body.risk_medium_max < body.risk_high_max <= 100):
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="Thresholds must be strictly increasing")
    settings.risk_low_max = body.risk_low_max
    settings.risk_medium_max = body.risk_medium_max
    settings.risk_high_max = body.risk_high_max
    return {"detail": "updated", **body.model_dump()}


@router.patch("/runtime")
async def set_runtime(
    body: RuntimeSettings,
    _: Annotated[CurrentUser, Depends(require_permission(SETTINGS_WRITE))],
):
    settings = get_settings()
    if body.ml_enabled is not None:
        settings.ml_enabled = body.ml_enabled
    if body.auto_block_ip is not None:
        settings.auto_block_ip = body.auto_block_ip
    if body.llm_analyzer_enabled is not None:
        settings.llm_analyzer_enabled = body.llm_analyzer_enabled
    return {"detail": "updated"}
