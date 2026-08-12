"""Audit logging service.

Every security-relevant action performed through the control plane is
recorded here. Sensitive values are redacted before persisting.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redact import redact_text
from app.models import AuditLog


def _safe_details(details: dict | None) -> dict | None:
    if not details:
        return details
    scrubbed: dict = {}
    for key, value in details.items():
        if isinstance(value, str):
            scrubbed[key], _ = redact_text(value)
        elif isinstance(value, dict):
            scrubbed[key] = _safe_details(value)
        elif isinstance(value, list):
            scrubbed[key] = [
                _safe_details(v) if isinstance(v, dict)
                else (redact_text(v)[0] if isinstance(v, str) else v)
                for v in value
            ]
        else:
            scrubbed[key] = value
    return scrubbed


async def log_audit(
    session: AsyncSession,
    *,
    action: str,
    actor_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    details: dict | None = None,
    status: str = "success",
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details=_safe_details(details),
        status=status,
    )
    session.add(entry)
    await session.flush()
    return entry
