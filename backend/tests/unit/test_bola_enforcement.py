"""Tests for gateway BOLA ownership enforcement (F2 fix).

Covers the privileged-only collection restriction in ``_route_checks`` and
the post-forward ``ownership_violation`` check for owner-keyed resource paths.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.gateway.models import RequestContext, UpstreamResponse
from app.gateway.service import GatewayService


async def _make_service():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin():
        pass
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as ses:
        yield GatewayService(ses)
    await engine.dispose()


def _ctx(**overrides) -> RequestContext:
    base = dict(
        request_id="req-test",
        timestamp=datetime.now(timezone.utc),
        method="GET",
        path="/api/orders/102",
        endpoint="/api/orders/{id}",
        query_string=None,
        headers={},
        body_text=None,
        body_json=None,
        body_bytes=0,
        source_ip="127.0.0.1",
        user_agent=None,
        device_id=None,
        actor_id="user-1",
        actor_username="alice",
        actor_role="user",
        actor_subject_id=1,
    )
    base.update(overrides)
    return RequestContext(**base)


def _upstream(payload: dict | list) -> UpstreamResponse:
    body = json.dumps(payload)
    return UpstreamResponse(
        status_code=200,
        body_text=body,
        body_json=payload,
        headers={"content-type": "application/json"},
        bytes_size=len(body.encode()),
        latency_ms=1.0,
    )


async def test_route_checks_blocks_non_privileged_collections():
    async for svc in _make_service():
        for path in ("/api/customers", "/api/payments", "/api/payments/summary"):
            findings = svc._route_checks(_ctx(path=path, endpoint=path))
            assert any(f.rule_id == "API-016" for f in findings), path


async def test_route_checks_allows_privileged_collections():
    async for svc in _make_service():
        for role in ("admin", "operator"):
            findings = svc._route_checks(_ctx(path="/api/customers", actor_role=role))
            assert findings == [], role


async def test_ownership_violation_detects_cross_subject_order():
    async for svc in _make_service():
        finding = svc.ownership_violation(
            _ctx(path="/api/orders/102"), _upstream({"id": 102, "user_id": 2})
        )
        assert finding is not None
        assert finding.rule_id == "API-016"
        assert "owned by another subject" in finding.reasons[0]


async def test_ownership_violation_allows_own_order():
    async for svc in _make_service():
        finding = svc.ownership_violation(
            _ctx(path="/api/orders/101"), _upstream({"id": 101, "user_id": 1})
        )
        assert finding is None


async def test_ownership_violation_skips_privileged_actors():
    async for svc in _make_service():
        finding = svc.ownership_violation(
            _ctx(path="/api/orders/102", actor_role="admin"),
            _upstream({"id": 102, "user_id": 2}),
        )
        assert finding is None


async def test_ownership_violation_ignores_list_responses():
    async for svc in _make_service():
        finding = svc.ownership_violation(
            _ctx(path="/api/orders/102"),
            _upstream([{"id": 102, "user_id": 2}]),
        )
        assert finding is None


async def test_orders_query_user_id_bola():
    async for svc in _make_service():
        findings = svc._route_checks(
            _ctx(
                path="/api/orders",
                endpoint="/api/orders",
                query_string="user_id=2",
                actor_subject_id=1,
            )
        )
        assert any(f.rule_id == "API-016" for f in findings)


async def test_orders_query_own_user_id_allowed():
    async for svc in _make_service():
        findings = svc._route_checks(
            _ctx(
                path="/api/orders",
                endpoint="/api/orders",
                query_string="user_id=1",
                actor_subject_id=1,
            )
        )
        assert findings == []


async def test_users_own_resource_allowed():
    async for svc in _make_service():
        findings = svc._route_checks(
            _ctx(path="/api/users/1", endpoint="/api/users/:id", actor_subject_id=1)
        )
        assert findings == []


async def test_users_other_resource_blocked():
    async for svc in _make_service():
        findings = svc._route_checks(
            _ctx(path="/api/users/2", endpoint="/api/users/:id", actor_subject_id=1)
        )
        assert any(f.rule_id == "API-016" for f in findings)

