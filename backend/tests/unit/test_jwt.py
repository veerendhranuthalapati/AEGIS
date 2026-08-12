"""JWT creation / verification tests."""
import uuid
from datetime import timedelta

import pytest

from app.auth.jwt import TokenError, create_token, decode_token


def _token(**kwargs):
    return create_token(
        subject="user-123",
        token_type="access",
        role="user",
        username="alice",
        permissions=["events:read"],
        expires_delta=timedelta(minutes=30),
        **kwargs,
    )


def test_create_and_decode_roundtrip():
    token, jti, exp = _token()
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "user-123"
    assert payload["jti"] == jti
    assert payload["role"] == "user"
    assert payload["username"] == "alice"
    assert payload["permissions"] == ["events:read"]
    assert payload["type"] == "access"


def test_expired_token_rejected():
    token, _, _ = _token()
    # No direct control over clock without monkeypatching; verify the error type
    # by decoding a token with a far-past exp via a manual payload.
    import jwt as pyjwt

    from app.config import get_settings

    settings = get_settings()
    payload = {
        "sub": "u1",
        "jti": str(uuid.uuid4()),
        "type": "access",
        "exp": 1,  # 1970
        "nbf": 1,
        "iat": 1,
        "iss": settings.token_issuer,
    }
    expired = pyjwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(TokenError):
        decode_token(expired)


def test_wrong_type_rejected():
    refresh, _, _ = create_token(
        subject="user-123",
        token_type="refresh",
        role="user",
        username="alice",
        permissions=[],
        expires_delta=timedelta(minutes=60),
    )
    with pytest.raises(TokenError):
        decode_token(refresh, expected_type="access")


def test_tampered_token_rejected():
    token, _, _ = _token()
    tampered = token[:-4] + "AAAA"
    with pytest.raises(TokenError):
        decode_token(tampered)
