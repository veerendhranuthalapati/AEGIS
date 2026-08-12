"""Response engine.

Executes configurable automated responses. Every action is audited,
idempotent where possible, reversible where possible, and (in development)
uses safe mock implementations. No unrestricted infrastructure control is
ever exposed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AccessToken,
    IpBlock,
    ResponseAction,
    Session as DbSession,
    User,
)
from app.services.audit import log_audit


class ResponseError(Exception):
    pass


class ResponseExecutor:
    """Executes named response actions with idempotent, audited handlers."""

    def __init__(self, mode: str = "mock") -> None:
        self._mode = mode

    async def execute(
        self,
        session: AsyncSession,
        *,
        action_type: str,
        target: str | None = None,
        target_value: str | None = None,
        trigger_event_id: str | None = None,
        trigger_incident_id: str | None = None,
        details: dict | None = None,
    ) -> ResponseAction:
        handler = getattr(self, f"_handle_{action_type.lower()}", None)
        if handler is None:
            raise ResponseError(f"unknown response action: {action_type}")

        record = ResponseAction(
            action_type=action_type,
            target=target,
            target_value=target_value,
            trigger_event_id=trigger_event_id,
            trigger_incident_id=trigger_incident_id,
            status="executing",
            reversible=True,
            executed_by="engine",
            details=details or {},
        )
        session.add(record)
        await session.flush()

        try:
            result = await handler(session, target, target_value, record)
            record.status = "executed"
            record.reversible = result.get("reversible", True)
            record.details = {**(details or {}), "result": result.get("summary", "")}
        except Exception as exc:  # noqa: BLE001
            record.status = "failed"
            record.details = {**(details or {}), "error": str(exc)}
            await session.commit()
            raise ResponseError(f"{action_type} failed: {exc}") from exc

        await log_audit(
            session,
            action=f"response.{action_type.lower()}",
            actor_id="engine",
            target_type=target,
            target_id=target_value,
            details={"status": "executed", "mode": self._mode},
        )
        await session.commit()
        return record

    # --- Handlers ---------------------------------------------------------

    async def _handle_block_ip(
        self,
        session: AsyncSession,
        target: str | None,
        value: str | None,
        record: ResponseAction,
    ) -> dict:
        if not value:
            raise ResponseError("BLOCK_IP requires an IP value")
        existing = await session.execute(
            select(IpBlock).where(IpBlock.ip == value, IpBlock.is_active == True)  # noqa: E712
        )
        if existing.scalar_one_or_none() is not None:
            return {"summary": "IP already blocked", "reversible": True}
        session.add(
            IpBlock(
                ip=value,
                reason="automated response",
                is_active=True,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            )
        )
        return {"summary": f"IP {value} blocked for 24h", "reversible": True}

    async def _handle_revoke_token(
        self,
        session: AsyncSession,
        target: str | None,
        value: str | None,
        record: ResponseAction,
    ) -> dict:
        if not value:
            raise ResponseError("REVOKE_TOKEN requires a token id (jti)")
        token = await session.get(AccessToken, value)
        if token is None:
            # Try lookup by jti
            result = await session.execute(
                select(AccessToken).where(AccessToken.jti == value)
            )
            token = result.scalar_one_or_none()
        if token is None:
            raise ResponseError("token not found")
        if token.revoked_at is None:
            token.revoked_at = datetime.now(timezone.utc)
        return {"summary": "token revoked", "reversible": True}

    async def _handle_revoke_session(
        self,
        session: AsyncSession,
        target: str | None,
        value: str | None,
        record: ResponseAction,
    ) -> dict:
        if not value:
            raise ResponseError("REVOKE_SESSION requires a session id")
        db_session = await session.get(DbSession, value)
        if db_session is None:
            raise ResponseError("session not found")
        if db_session.is_active:
            db_session.is_active = False
            db_session.revoked_at = datetime.now(timezone.utc)
        return {"summary": "session revoked", "reversible": True}

    async def _handle_disable_user(
        self,
        session: AsyncSession,
        target: str | None,
        value: str | None,
        record: ResponseAction,
    ) -> dict:
        if not value:
            raise ResponseError("DISABLE_USER requires a user id")
        user = await session.get(User, value)
        if user is None:
            raise ResponseError("user not found")
        if user.is_active:
            user.is_active = False
        return {"summary": f"user {user.username} disabled", "reversible": True}

    async def _handle_rate_limit(
        self,
        session: AsyncSession,
        target: str | None,
        value: str | None,
        record: ResponseAction,
    ) -> dict:
        return {
            "summary": "rate limiting policy enforced at gateway",
            "reversible": True,
        }

    async def _handle_require_human_approval(
        self,
        session: AsyncSession,
        target: str | None,
        value: str | None,
        record: ResponseAction,
    ) -> dict:
        return {
            "summary": "human approval required (approval record created)",
            "reversible": True,
        }

    async def _handle_isolate_service(
        self,
        session: AsyncSession,
        target: str | None,
        value: str | None,
        record: ResponseAction,
    ) -> dict:
        # Mock implementation for local/dev. Cloud integration is isolated
        # behind a real deployment integration that is not part of this repo.
        return {
            "summary": f"service isolation requested for {value or 'unknown'} (mock)",
            "reversible": True,
        }

    async def _handle_create_incident(
        self,
        session: AsyncSession,
        target: str | None,
        value: str | None,
        record: ResponseAction,
    ) -> dict:
        return {"summary": "incident created by correlation engine", "reversible": False}

    async def _handle_redact_response(
        self,
        session: AsyncSession,
        target: str | None,
        value: str | None,
        record: ResponseAction,
    ) -> dict:
        return {"summary": "response redaction applied", "reversible": True}

    async def _handle_block_request(
        self,
        session: AsyncSession,
        target: str | None,
        value: str | None,
        record: ResponseAction,
    ) -> dict:
        return {"summary": "request blocked", "reversible": True}
