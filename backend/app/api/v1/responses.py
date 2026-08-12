"""Response actions endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ResponseActionOut
from app.auth.dependencies import CurrentUser, require_permission
from app.auth.permissions import AUDIT_READ
from app.database import get_session
from app.models import ResponseAction

router = APIRouter(prefix="/responses", tags=["responses"])


@router.get("", response_model=list[ResponseActionOut])
async def list_responses(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(AUDIT_READ))],
    limit: int = 200,
):
    result = await session.execute(
        select(ResponseAction)
        .order_by(ResponseAction.timestamp.desc())
        .limit(min(limit, 1000))
    )
    return list(result.scalars().all())
