"""Consistent client IP extraction for rate limiting and audit.

When ``trust_forwarded_headers`` is enabled (development default), the first
hop in ``X-Forwarded-For`` is used so attack-lab scenarios can isolate rate-
limit buckets without relying on global mutable state. In production this must
only be enabled behind a trusted reverse proxy that strips spoofed headers.
"""
from __future__ import annotations

from fastapi import Request

from app.config import Settings, get_settings


def resolve_client_ip(request: Request, settings: Settings | None = None) -> str:
    """Return a stable rate-limit / audit key for the connecting client."""
    cfg = settings or get_settings()
    if cfg.trust_forwarded_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            candidate = forwarded.split(",")[0].strip()
            if candidate:
                return candidate
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
