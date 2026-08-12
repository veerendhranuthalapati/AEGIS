"""Security event creation and persistence.

Events are the atomic unit of the detection pipeline. Sensitive payload
values are redacted before they are stored. The worker (see
``app.worker.main``) picks up unprocessed events for correlation, incident
creation and automated responses.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.ids import new_event_id
from app.core.redact import redact_text
from app.metrics import observe_security_event
from app.models import SecurityEvent

settings = get_settings()


class SensitiveValueError(ValueError):
    """Raised when a caller tries to store an unredacted sensitive value."""


def _redact_details(details: dict | None) -> dict | None:
    """Recursively redact strings in a details dict."""
    if not details:
        return details
    out: dict = {}
    for key, value in details.items():
        if isinstance(value, str):
            out[key], _ = redact_text(value)
        elif isinstance(value, dict):
            out[key] = _redact_details(value)
        elif isinstance(value, list):
            out[key] = [
                _redact_details(v) if isinstance(v, dict)
                else (redact_text(v)[0] if isinstance(v, str) else v)
                for v in value
            ]
        else:
            out[key] = value
    return out


async def create_security_event(
    session: AsyncSession,
    *,
    event_type: str,
    severity: str = "LOW",
    actor_id: str | None = None,
    source_ip: str | None = None,
    endpoint: str | None = None,
    method: str | None = None,
    risk_score: float | None = None,
    decision: str | None = None,
    reasons: list[str] | None = None,
    details: dict | None = None,
    detection_source: str | None = None,
    model_version: str | None = None,
    policy_version: str | None = None,
    correlation_key: str | None = None,
    mitre_techniques: list[str] | None = None,
) -> SecurityEvent:
    event = SecurityEvent(
        event_id=new_event_id(),
        timestamp=datetime.now(timezone.utc),
        event_type=event_type,
        severity=severity,
        actor_id=actor_id,
        source_ip=source_ip,
        endpoint=endpoint,
        method=method,
        risk_score=risk_score,
        decision=decision,
        reasons=list(reasons) if reasons else None,
        details=_redact_details(details),
        detection_source=detection_source,
        model_version=model_version,
        policy_version=policy_version,
        correlation_key=correlation_key,
        mitre_techniques=list(mitre_techniques) if mitre_techniques else None,
        processed=False,
    )
    session.add(event)
    await session.flush()
    observe_security_event(event_type, severity)
    return event
