"""Authentication and token service."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import TokenError, create_token
from app.auth.password import verify_password
from app.config import get_settings
from app.models import AccessToken, Role, User

settings = get_settings()


class AuthError(Exception):
    """Authentication failure."""


async def get_user_by_username(
    session: AsyncSession, username: str
) -> User | None:
    result = await session.execute(
        select(User)
        .options(selectinload(User.role).selectinload(Role.permissions))
        .where(User.username == username)
    )
    return result.scalar_one_or_none()


async def load_role(session: AsyncSession, role_id: str) -> Role | None:
    result = await session.execute(select(Role).where(Role.id == role_id))
    return result.scalar_one_or_none()


def role_permissions(role: Role) -> list[str]:
    return [p.permission for p in role.permissions]


async def authenticate_user(
    session: AsyncSession, username: str, password: str
) -> User:
    user = await get_user_by_username(session, username)
    if user is None:
        raise AuthError("invalid credentials")

    now = datetime.now(timezone.utc)
    if user.is_locked and user.locked_at is not None:
        locked_at = user.locked_at
        if locked_at.tzinfo is None:
            locked_at = locked_at.replace(tzinfo=timezone.utc)
        unlock_at = locked_at + timedelta(minutes=settings.auth_lockout_minutes)
        if now >= unlock_at:
            user.is_locked = False
            user.locked_at = None
            user.failed_login_count = 0
        else:
            remaining = int((unlock_at - now).total_seconds())
            raise AuthError(f"account temporarily locked ({remaining}s remaining)")

    if not verify_password(password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= settings.auth_lockout_max_failed:
            user.is_locked = True
            if user.locked_at is None:
                user.locked_at = now
        await session.commit()
        raise AuthError("invalid credentials")
    if not user.is_active:
        raise AuthError("account disabled")
    if user.is_locked:
        raise AuthError("account locked")
    user.failed_login_count = 0
    user.locked_at = None
    user.last_login_at = now
    await session.commit()
    return user


def issue_token_pair(
    user: User, permissions: list[str], sid: str | None = None
) -> dict[str, str]:
    extra = {"sid": sid} if sid else None
    access, access_jti, access_exp = create_token(
        subject=user.id,
        token_type="access",
        role=user.role.name if user.role else "user",
        username=user.username,
        permissions=permissions,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        extra=extra,
    )
    refresh, refresh_jti, refresh_exp = create_token(
        subject=user.id,
        token_type="refresh",
        role=user.role.name if user.role else "user",
        username=user.username,
        permissions=permissions,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
        extra=extra,
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "access_token_jti": access_jti,
        "refresh_token_jti": refresh_jti,
        "access_expires_at": access_exp.isoformat(),
        "refresh_expires_at": refresh_exp.isoformat(),
        "token_type": "bearer",
    }


async def record_access_token(
    session: AsyncSession,
    user_id: str,
    jti: str,
    expires_at: datetime,
    token_type: str = "access",
) -> None:
    session.add(
        AccessToken(
            jti=jti,
            user_id=user_id,
            token_type=token_type,
            expires_at=expires_at,
        )
    )
    await session.commit()


async def revoke_token(session: AsyncSession, jti: str) -> bool:
    result = await session.execute(
        select(AccessToken).where(AccessToken.jti == jti)
    )
    token = result.scalar_one_or_none()
    if token is None:
        return False
    token.revoked_at = datetime.now(timezone.utc)
    await session.commit()
    return True


async def ensure_token_valid(
    session: AsyncSession, payload: dict
) -> User:
    """Verify the JWT is not revoked or expired and the subject exists."""
    jti = payload.get("jti")
    if jti:
        result = await session.execute(
            select(AccessToken).where(AccessToken.jti == jti)
        )
        token = result.scalar_one_or_none()
        if token is None or token.revoked_at is not None:
            raise TokenError("token revoked")
        if token.expires_at is not None and token.expires_at < datetime.now(timezone.utc):
            raise TokenError("token expired")
    user_id = payload.get("sub")
    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise TokenError("user not found")
    if not user.is_active:
        raise TokenError("user disabled")
    if user.is_locked:
        raise TokenError("user locked")
    return user
