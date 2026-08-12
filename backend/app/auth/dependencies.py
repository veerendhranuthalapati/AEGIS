"""FastAPI dependencies for authentication and authorization.

Every security-sensitive endpoint must go through these dependencies.
Authorization is always enforced server-side.
"""
from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import TokenError, decode_token
from app.auth.permissions import ROLES
from app.auth.service import ensure_token_valid
from app.database import get_session
from app.models import Role, User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
        user = await ensure_token_valid(session, payload)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    from sqlalchemy import select as _select
    from sqlalchemy.orm import selectinload as _selectinload

    result = await session.execute(
        _select(User)
        .options(_selectinload(User.role).selectinload(Role.permissions))
        .where(User.id == user.id)
    )
    user = result.scalar_one_or_none() or user
    request.state.current_user = user
    request.state.token_payload = payload
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def _user_permissions(user: User) -> set[str]:
    if user.role is not None:
        return {p.permission for p in user.role.permissions}
    return set()


def require_permission(permission: str):
    """Dependency factory: requires ``permission`` on the current user."""

    def _checker(user: CurrentUser) -> User:
        if permission not in _user_permissions(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission}",
            )
        return user

    return _checker


def require_role(role_name: str):
    """Dependency factory: requires an exact role on the current user."""

    def _checker(user: CurrentUser) -> User:
        role = user.role
        if role is None or role.name != role_name:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role_name}' required",
            )
        return user

    return _checker


async def resolve_user_permissions(
    session: AsyncSession, user: User
) -> list[str]:
    """Load effective permissions (from DB role, falling back to defaults)."""
    role = user.role
    if role is None:
        result = await session.execute(select(Role).where(Role.id == user.role_id))
        role = result.scalar_one_or_none()
    if role is not None and role.permissions:
        return [p.permission for p in role.permissions]
    default = cast(list[str], ROLES.get(role.name if role else "user", {}).get("permissions", []))
    return list(default)
