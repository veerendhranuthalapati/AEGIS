"""Gateway proxy route.

All protected traffic enters through ``/gateway/{path:path}``. The router
authenticates, inspects, decides, forwards, inspects the response and
persists telemetry/events.
"""
from __future__ import annotations

import time
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import TokenError, decode_token
from app.config import get_settings
from app.core.client_ip import resolve_client_ip
from app.core.ids import new_request_id
from app.core.redact import find_detections
from app.database import get_session
from app.gateway.models import RequestContext
from app.gateway.service import GatewayResult, GatewayService, normalize_endpoint
from app.metrics import observe_request
from app.models import User
from app.security.risk.engine import RiskAssessment
from app.services.events import create_security_event

router = APIRouter(prefix="/gateway", tags=["gateway"])
settings = get_settings()
logger = structlog.get_logger("aegis.gateway_api")

# Paths that do not require authentication when transiting the gateway.
_OPEN_PATHS = ("/health", "/public", "/auth/", "/status")


async def _read_bounded(request: Request, limit: int) -> tuple[bytes, bool]:
    """Read the request body without buffering more than ``limit`` bytes.

    Returns (body_bytes, oversized). The caller must reject when oversized.
    """
    content_length = request.headers.get("content-length")
    if content_length is not None and content_length.isdigit():
        try:
            if int(content_length) > limit:
                return b"", True
        except ValueError:
            pass
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            return b"", True
        chunks.append(chunk)
    return b"".join(chunks), False


async def _resolve_actor(
    request: Request,
    session: AsyncSession,
) -> tuple[User | None, dict]:
    """Resolve the bearer token if present; returns (user, token_payload)."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None, {}
    token = auth_header.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token, expected_type="access")
    except TokenError:
        return None, {}
    from app.auth.service import ensure_token_valid
    from app.models import Role
    from sqlalchemy import select as _select
    from sqlalchemy.orm import selectinload as _selectinload

    try:
        user = await ensure_token_valid(session, payload)
    except TokenError:
        return None, {}
    role_result = await session.execute(
        _select(Role)
        .options(_selectinload(Role.permissions))
        .where(Role.id == user.role_id)
    )
    role = role_result.scalar_one_or_none()
    setattr(user, "role", role)
    return user, payload


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
async def proxy(
    path: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    request_id = new_request_id()
    full_path = "/" + path if not path.startswith("/") else path
    _start = time.perf_counter()
    endpoint_group = normalize_endpoint(full_path)
    final_decision: str = "BLOCK"

    # --- auth resolution ---
    user, payload = await _resolve_actor(request, session)
    if user is None and not any(full_path.startswith(p) for p in _OPEN_PATHS):
        observe_request(
            "BLOCK", endpoint_group, (time.perf_counter() - _start) * 1000
        )
        return JSONResponse(
            status_code=401,
            content={
                "request_id": request_id,
                "decision": "BLOCK",
                "reason": "Authentication required to transit the gateway",
                "error": "unauthenticated",
            },
            headers={"x-aegis-decision": "BLOCK"},
        )

    # --- body handling ---
    body_bytes = 0
    body_text: str | None = None
    body_json = None
    content_type = request.headers.get("content-type", "")
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        raw, oversized = await _read_bounded(request, settings.max_request_body_bytes)
        body_bytes = len(raw) if not oversized else settings.max_request_body_bytes + 1
        if oversized or body_bytes > settings.max_request_body_bytes:
            await create_security_event(
                session,
                event_type="OVERSIZED_REQUEST",
                severity="MEDIUM",
                actor_id=user.id if user else None,
                source_ip=resolve_client_ip(request, settings),
                endpoint=normalize_endpoint(full_path),
                method=request.method,
                reasons=[f"body of {body_bytes} bytes"],
                detection_source="rules",
                correlation_key=user.id if user else (request.client.host if request.client else None),
            )
            await session.commit()
            observe_request(
                "BLOCK", endpoint_group, (time.perf_counter() - _start) * 1000
            )
            return JSONResponse(
                status_code=413,
                content={"request_id": request_id, "decision": "BLOCK", "reason": "Request body too large"},
                headers={"x-aegis-decision": "BLOCK"},
            )
        body_text = raw.decode("utf-8", errors="replace") if raw else None
        if "json" in content_type and body_text:
            import json as _json

            try:
                body_json = _json.loads(body_text)
            except (ValueError, _json.JSONDecodeError):
                body_json = None

    device_id = request.headers.get("x-device-id")

    ctx = RequestContext.build(
        request_id=request_id,
        method=request.method,
        path=full_path,
        endpoint=normalize_endpoint(full_path),
        query_string=request.url.query or None,
        headers=dict(request.headers),
        body_text=body_text,
        body_json=body_json,
        source_ip=resolve_client_ip(request, settings),
        user_agent=request.headers.get("user-agent"),
        device_id=device_id,
        body_bytes=body_bytes,
    )

    if user is not None:
        ctx.actor_id = user.id
        ctx.actor_username = user.username
        ctx.actor_role = user.role.name if user.role else "user"
        ctx.actor_subject_id = user.subject_id
        ctx.actor_permissions = [p.permission for p in (user.role.permissions if user.role else [])]
        ctx.session_id = payload.get("sid")
        ctx.auth_method = "jwt"
        ctx.extra["token_created_at"] = payload.get("iat")

    # Body sensitivity indicator for feature engineering
    if body_text:
        ctx.extra["has_sensitive"] = bool(find_detections(body_text))

    gateway = GatewayService(session)
    try:
        result = await gateway.inspect_and_decide(ctx)
        final_decision = result.decision

        if result.decision == "BLOCK":
            await gateway.persist(ctx, result, None)
            return JSONResponse(
                status_code=result.http_status,
                content={
                    "request_id": request_id,
                    "decision": "BLOCK",
                    "risk_score": result.risk.score,
                    "risk_level": result.risk.level,
                    "reasons": result.risk.reasons[:15],
                    "findings": [f.to_dict() for f in result.findings[:10]],
                },
                headers={"x-aegis-decision": "BLOCK"},
            )

        if result.decision == "REQUIRE_REVIEW":
            await gateway.persist(ctx, result, None)
            return JSONResponse(
                status_code=202,
                content={
                    "request_id": request_id,
                    "decision": "REQUIRE_REVIEW",
                    "risk_score": result.risk.score,
                    "reasons": result.risk.reasons[:15],
                    "message": "Request requires human review and was not forwarded.",
                },
                headers={"x-aegis-decision": "REQUIRE_REVIEW"},
            )

        # --- forward ---
        upstream = await gateway.forward(ctx)

        # --- post-forward ownership verification (BOLA/IDOR) ---
        bola = gateway.ownership_violation(ctx, upstream)
        if bola is not None:
            final_decision = "BLOCK"
            bol_result = GatewayResult(
                decision="BLOCK",
                risk=RiskAssessment(
                    score=80.0,
                    level="HIGH",
                    reasons=bola.reasons,
                ),
                findings=[bola],
                http_status=403,
                reason="Cross-subject resource access denied",
            )
            await gateway.persist(ctx, bol_result, upstream)
            return JSONResponse(
                status_code=403,
                content={
                    "request_id": request_id,
                    "decision": "BLOCK",
                    "risk_score": 80.0,
                    "risk_level": "HIGH",
                    "reason": "Cross-subject resource access denied",
                    "findings": [f.to_dict() for f in bol_result.findings],
                },
                headers={"x-aegis-decision": "BLOCK"},
            )

        # --- response security ---
        if is_output_inspectable(full_path):
            upstream = gateway.inspect_response(ctx, upstream)
            if ctx.extra.get("response_redacted"):
                await create_security_event(
                    session,
                    event_type="SENSITIVE_OUTPUT",
                    severity="HIGH",
                    actor_id=user.id if user else None,
                    source_ip=resolve_client_ip(request, settings),
                    endpoint=ctx.endpoint,
                    method=ctx.method,
                    risk_score=result.risk.score,
                    decision="REDACT",
                    reasons=["Sensitive data detected in upstream response and redacted"],
                    detection_source="pii",
                    correlation_key=ctx.actor_id or ctx.source_ip,
                    mitre_techniques=["T1041"],
                )
                await session.commit()

        await gateway.persist(ctx, result, upstream)

        # --- build response ---
        response_headers = {
            k: v
            for k, v in upstream.headers.items()
            if k.lower() not in {"content-length", "content-encoding", "transfer-encoding", "connection"}
        }
        response_headers["x-aegis-decision"] = result.decision
        response_headers["x-aegis-request-id"] = request_id
        if result.decision == "WARN":
            response_headers["x-aegis-warning"] = "; ".join(result.risk.reasons[:3])

        if upstream.body_text is None or upstream.body_text == "":
            return Response(
                status_code=upstream.status_code,
                headers=response_headers,
                content=b"",
            )
        if upstream.body_json is not None:
            return JSONResponse(
                status_code=upstream.status_code,
                content=upstream.body_json,
                headers=response_headers,
            )
        if "text/html" in upstream.headers.get("content-type", ""):
            return Response(
                status_code=upstream.status_code,
                content=upstream.body_text,
                media_type="text/html",
                headers=response_headers,
            )
        return Response(
            status_code=upstream.status_code,
            content=upstream.body_text,
            media_type=upstream.headers.get("content-type", "application/json"),
            headers=response_headers,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "gateway.proxy_error",
            request_id=request_id,
            path=full_path,
            error=str(exc),
        )
        return JSONResponse(
            status_code=502,
            content={
                "request_id": request_id,
                "decision": "BLOCK",
                "reason": f"Upstream failure: {exc.__class__.__name__}",
            },
            headers={"x-aegis-decision": "BLOCK"},
        )
    finally:
        observe_request(
            final_decision, endpoint_group, (time.perf_counter() - _start) * 1000
        )
        await gateway.close()


def is_output_inspectable(path: str) -> bool:
    """Routes whose upstream responses should be inspected/redacted."""
    return any(
        seg in path
        for seg in (
            "/ai/",
            "/chat",
            "/llm/",
            "/api/users",
            "/api/customers",
            "/api/orders",
            "/api/payments",
        )
    )
