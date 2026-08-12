"""Shared test helpers (pure, no database)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.gateway.models import RequestContext


def make_ctx(**overrides) -> RequestContext:
    base: dict = {
        "request_id": "req_test",
        "timestamp": datetime.now(timezone.utc),
        "method": "GET",
        "path": "/api/gateway/search",
        "endpoint": "/search",
        "query_string": None,
        "headers": {},
        "body_text": None,
        "body_json": None,
        "body_bytes": 0,
        "source_ip": "203.0.113.10",
        "user_agent": None,
        "device_id": None,
    }
    base.update(overrides)
    return RequestContext(**base)
