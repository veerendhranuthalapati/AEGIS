"""Structured logging with built-in secret redaction.

Passwords, API keys, tokens and PII must never reach logs. This logger
applies a redaction processor to every emitted record before it is written.
"""
from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.core.redact import RedactLabel, redact_text

_RESERVED_KEYS = {
    "password",
    "password_hash",
    "secret",
    "token",
    "refresh_token",
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "set-cookie",
    "private_key",
    "secret_key",
    "client_secret",
    "x-api-key",
}


def _scrub_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if lowered in _RESERVED_KEYS:
        return RedactLabel.SECRET.value if value is not None else value
    if isinstance(value, str) and len(value) > 0:
        scrubbed, _ = redact_text(value)
        return scrubbed
    return value


def _scrub_dict(event_dict: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in event_dict.items():
        if isinstance(value, dict):
            out[key] = _scrub_dict(value)
        elif isinstance(value, list):
            out[key] = [
                _scrub_dict(v) if isinstance(v, dict) else _scrub_value(key, v)
                for v in value
            ]
        else:
            out[key] = _scrub_value(key, value)
    return out


def _redact_processor(
    _: object, __: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    return _scrub_dict(event_dict)


def setup_logging(level: str = "INFO") -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(stream=sys.stdout, level=level.upper())
    # Stdlib loggers that emit full request URLs (including query strings)
    # at INFO are not covered by structlog redaction and can leak sensitive
    # query parameters. Request telemetry is already persisted by the app,
    # so these access logs are suppressed below WARNING.
    for _noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
