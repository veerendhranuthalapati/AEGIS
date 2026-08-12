"""User management endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import UserCreate, UserOut
from app.auth.dependencies import CurrentUser, require_permission
from app.auth.password import hash_password
from app.auth.permissions import USERS_READ, USERS_WRITE
from app.database import get_session
from app.models import Role, User
from app.services.audit import log_audit

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
async def list_users(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(USERS_READ))],
):
    result = await session.execute(select(User).order_by(User.username))
    users = list(result.scalars().all())
    out = []
    for user in users:
        role = await session.get(Role, user.role_id)
        out.append(
            UserOut(
                id=user.id,
                username=user.username,
                email=user.email,
                full_name=user.full_name,
                role=role.name if role else None,
                is_active=user.is_active,
                is_locked=user.is_locked,
                created_at=user.created_at,
            )
        )
    return out


@router.post("", response_model=UserOut)
async def create_user(
    body: UserCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[CurrentUser, Depends(require_permission(USERS_WRITE))],
):
    existing = await session.execute(
        select(User).where(
            (User.username == body.username) | (User.email == body.email)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username or email already in use")

    role_result = await session.execute(
        select(Role).where(Role.name == body.role_name)
    )
    role = role_result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=422, detail="Unknown role")

    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        subject_id=body.subject_id,
        role_id=role.id,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await log_audit(
        session,
        action="users.create",
        actor_id=actor.id,
        target_type="user",
        target_id=user.username,
    )
    await session.commit()
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=role.name,
        is_active=user.is_active,
        is_locked=user.is_locked,
        created_at=user.created_at,
    )


@router.patch("/{user_id}/disable")
async def disable_user(
    user_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[CurrentUser, Depends(require_permission(USERS_WRITE))],
):
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == actor.id:
        raise HTTPException(status_code=409, detail="Cannot disable yourself")
    user.is_active = False
    await log_audit(
        session,
        action="users.disable",
        actor_id=actor.id,
        target_type="user",
        target_id=user.username,
    )
    await session.commit()
    return {"detail": "disabled", "user": user.username}


@router.patch("/{user_id}/enable")
async def enable_user(
    user_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[CurrentUser, Depends(require_permission(USERS_WRITE))],
):
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    user.is_locked = False
    user.locked_at = None
    user.failed_login_count = 0
    await log_audit(
        session,
        action="users.enable",
        actor_id=actor.id,
        target_type="user",
        target_id=user.username,
    )
    await session.commit()
    return {"detail": "enabled", "user": user.username}
