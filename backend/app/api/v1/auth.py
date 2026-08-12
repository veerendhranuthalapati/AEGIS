"""Authentication endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import LoginRequest, LoginResponse, RefreshRequest, UserOut
from app.auth.dependencies import CurrentUser
from app.auth.jwt import TokenError, decode_token
from app.auth.permissions import ROLES
from app.auth.service import (
    AuthError,
    authenticate_user,
    ensure_token_valid,
    issue_token_pair,
    record_access_token,
    revoke_token,
)
from app.config import get_settings
from app.core.client_ip import resolve_client_ip
from app.database import get_session
from app.models import Session as DbSession, User
from app.services.audit import log_audit
from app.services.events import create_security_event
from app.services.ratelimit import check_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.name if user.role else "user",
        "subject_id": user.subject_id,
        "is_active": user.is_active,
        "is_locked": user.is_locked,
        "created_at": user.created_at.isoformat(),
    }


async def _load_permissions(session: AsyncSession, user: User) -> list[str]:
    if user.role and user.role.permissions:
        return [p.permission for p in user.role.permissions]
    return list(cast(list[str], ROLES.get(user.role.name if user.role else "user", {}).get("permissions", [])))


async def _emit_auth_event(
    session: AsyncSession,
    *,
    event_type: str,
    severity: str,
    source_ip: str | None,
    reasons: list[str],
    actor_id: str | None = None,
    details: dict | None = None,
) -> None:
    await create_security_event(
        session,
        event_type=event_type,
        severity=severity,
        actor_id=actor_id,
        source_ip=source_ip,
        endpoint="/auth/login",
        method="POST",
        reasons=reasons,
        details=details,
        detection_source="auth",
        correlation_key=source_ip,
        mitre_techniques=["T1110"] if event_type == "AUTH_FAILURE_BURST" else None,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    ip = resolve_client_ip(request, settings)
    # Brute-force protection on the login endpoint itself.
    allowed, count, reset = await check_rate_limit(
        session, key=f"login:{ip}", limit=settings.login_rate_limit_per_min
    )
    if not allowed:
        await log_audit(
            session,
            action="auth.login_rate_limited",
            ip_address=ip,
            details={"attempts": count},
            status="denied",
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Retry in {reset}s.",
        )

    try:
        user = await authenticate_user(session, body.username, body.password)
    except AuthError as exc:
        await _emit_auth_event(
            session,
            event_type="AUTH_FAILURE",
            severity="LOW",
            source_ip=ip,
            actor_id=None,
            reasons=[str(exc)],
            details={"username": body.username},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        ) from exc

    permissions = await _load_permissions(session, user)

    device_id = request.headers.get("x-device-id")
    session_record = DbSession(
        user_id=user.id,
        device_id=device_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        is_active=True,
    )
    session.add(session_record)
    await session.flush()

    tokens = issue_token_pair(user, permissions, sid=session_record.id)
    await record_access_token(
        session,
        user.id,
        tokens["access_token_jti"],
        datetime.fromisoformat(tokens["access_expires_at"]),
    )
    await record_access_token(
        session,
        user.id,
        tokens["refresh_token_jti"],
        datetime.fromisoformat(tokens["refresh_expires_at"]),
        token_type="refresh",
    )
    await log_audit(
        session,
        action="auth.login",
        actor_id=user.id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        details={"username": user.username},
    )
    await session.commit()

    return LoginResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type="bearer",
        expires_at=datetime.fromisoformat(tokens["access_expires_at"]),
        user=_user_out(user),
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh(
    request: Request,
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
        user = await ensure_token_valid(session, payload)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    # Rotate: the used refresh token is single-use.
    if payload.get("jti"):
        await revoke_token(session, payload["jti"])
    permissions = await _load_permissions(session, user)
    tokens = issue_token_pair(user, permissions, sid=payload.get("sid"))
    await record_access_token(
        session, user.id, tokens["access_token_jti"],
        datetime.fromisoformat(tokens["access_expires_at"]),
    )
    await record_access_token(
        session,
        user.id,
        tokens["refresh_token_jti"],
        datetime.fromisoformat(tokens["refresh_expires_at"]),
        token_type="refresh",
    )
    await session.commit()
    return LoginResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type="bearer",
        expires_at=datetime.fromisoformat(tokens["access_expires_at"]),
        user=_user_out(user),
    )


@router.post("/logout")
async def logout(
    request: Request,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    payload = getattr(request.state, "token_payload", {})
    jti = payload.get("jti")
    sid = payload.get("sid")
    if jti:
        await revoke_token(session, jti)
    if sid:
        session_record = await session.get(DbSession, sid)
        if session_record:
            session_record.is_active = False
            session_record.revoked_at = datetime.now(timezone.utc)
    await log_audit(
        session,
        action="auth.logout",
        actor_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()
    return {"detail": "logged out"}


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    role_name = user.role.name if user.role else None
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=role_name,
        is_active=user.is_active,
        is_locked=user.is_locked,
        created_at=user.created_at,
    )
