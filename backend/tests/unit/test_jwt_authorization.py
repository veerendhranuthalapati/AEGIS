"""Extended JWT and authorization boundary tests."""
from __future__ import annotations

import uuid
from datetime import timedelta

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.jwt import TokenError, create_token, decode_token
from app.config import get_settings

settings = get_settings()


def test_modified_role_rejected_at_decode():
    token, _, _ = create_token(
        subject="user-1",
        token_type="access",
        role="user",
        username="alice",
        permissions=["events:read"],
        expires_delta=timedelta(minutes=30),
    )
    parts = token.split(".")
    # Tamper payload segment
    tampered = parts[0] + "." + parts[1][:-2] + "XX." + parts[2]
    with pytest.raises(TokenError):
        decode_token(tampered, expected_type="access")


def test_missing_signature_rejected():
    token, _, _ = create_token(
        subject="user-1",
        token_type="access",
        role="admin",
        username="alice",
        permissions=["*"],
        expires_delta=timedelta(minutes=30),
    )
    unsigned = token.rsplit(".", 1)[0] + "."
    with pytest.raises(TokenError):
        decode_token(unsigned, expected_type="access")


def test_wrong_algorithm_rejected():
    payload = {
        "sub": "user-1",
        "jti": str(uuid.uuid4()),
        "type": "access",
        "role": "admin",
        "exp": 9999999999,
        "nbf": 1,
        "iat": 1,
        "iss": settings.token_issuer,
    }
    token = pyjwt.encode(payload, settings.secret_key, algorithm="HS256")
    # Re-sign with different key simulating substitution
    forged = pyjwt.encode(payload, "wrong-key", algorithm="HS256")
    with pytest.raises(TokenError):
        decode_token(forged, expected_type="access")
    decode_token(token, expected_type="access")


@pytest.mark.asyncio
async def test_gateway_rejects_missing_auth():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/gateway/api/users/1")
        assert r.status_code == 401
        assert r.json()["decision"] == "BLOCK"


@pytest.mark.asyncio
async def test_gateway_rejects_invalid_token():
    from app.main import app

    transport = ASGITransport(app=app)
    headers = {"Authorization": "Bearer not.a.valid.jwt"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/gateway/api/users/1", headers=headers)
        assert r.status_code == 401
