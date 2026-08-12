"""JWT creation and verification.

Tokens are signed with HS256. Each access token is recorded in the database
(``access_tokens``) so it can be revoked and so replay of revoked tokens is
detected.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.config import get_settings

settings = get_settings()

_JWT_EXP_LEEWAY_SECONDS = 10


class TokenError(Exception):
    """Raised when a token is invalid, expired or revoked."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_token(
    *,
    subject: str,
    token_type: str,
    role: str,
    username: str,
    permissions: list[str],
    expires_delta: timedelta,
    jti: str | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[str, str, datetime]:
    jti = jti or str(uuid.uuid4())
    now = _now()
    exp = now + expires_delta
    payload: dict[str, Any] = {
        "sub": subject,
        "jti": jti,
        "type": token_type,
        "role": role,
        "username": username,
        "permissions": permissions,
        "iat": now,
        "nbf": now,
        "exp": exp,
        "iss": settings.token_issuer,
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, jti, exp


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.token_issuer,
            leeway=_JWT_EXP_LEEWAY_SECONDS,
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid token") from exc

    if expected_type and payload.get("type") != expected_type:
        raise TokenError("unexpected token type")
    if not payload.get("sub"):
        raise TokenError("token missing subject")
    return payload
