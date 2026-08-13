"""AI agent / tool invocation and approval endpoints."""
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    ApprovalDecision,
    ApprovalOut,
    ToolCreate,
    ToolInvokeRequest,
    ToolInvokeResponse,
    ToolOut,
)
from app.auth.dependencies import (
    CurrentUser,
    require_permission,
    resolve_user_permissions,
)
from app.auth.permissions import APPROVALS_DECIDE, TOOLS_READ, TOOLS_WRITE
from app.database import get_session
from app.metrics import observe_approval, observe_tool
from app.models import Approval, Tool, ToolInvocation
from app.security.agents.engine import ToolSecurityEngine
from app.services.audit import log_audit
from app.services.events import create_security_event
from app.services.tool_executor import ToolExecutor

router = APIRouter(prefix="/tools", tags=["agents"])
logger = structlog.get_logger("aegis.agents")


async def _emit_tool_event(
    session: AsyncSession,
    *,
    event_type: str,
    severity: str,
    actor_id: str | None,
    source_ip: str | None,
    tool: str,
    decision: str,
    risk_score: float,
    reasons: list[str],
    mitre: list[str] | None = None,
) -> None:
    await create_security_event(
        session,
        event_type=event_type,
        severity=severity,
        actor_id=actor_id,
        source_ip=source_ip,
        endpoint="/api/agents/tools/invoke",
        method="POST",
        risk_score=risk_score,
        decision=decision,
        reasons=reasons,
        details={"tool": tool},
        detection_source="agents",
        correlation_key=actor_id or source_ip,
        mitre_techniques=mitre,
    )


@router.get("", response_model=list[ToolOut])
async def list_tools(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(TOOLS_READ))],
):
    result = await session.execute(select(Tool).order_by(Tool.name))
    return list(result.scalars().all())


@router.post("", response_model=ToolOut)
async def create_tool(
    body: ToolCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require_permission(TOOLS_WRITE))],
):
    existing = await session.execute(select(Tool).where(Tool.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Tool already exists")
    tool = Tool(
        name=body.name,
        description=body.description,
        parameters_schema=body.parameters_schema,
        category=body.category,
        default_allowed_roles=body.default_allowed_roles,
        sensitive=body.sensitive,
        requires_approval=body.requires_approval,
        approval_threshold_risk=body.approval_threshold_risk,
    )
    session.add(tool)
    await log_audit(
        session,
        action="tools.create",
        actor_id=user.id,
        target_type="tool",
        target_id=body.name,
    )
    await session.commit()
    return tool


@router.post("/invoke", response_model=ToolInvokeResponse)
async def invoke_tool(
    request: Request,
    body: ToolInvokeRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: CurrentUser,
):
    permissions = await resolve_user_permissions(session, user)
    source_ip = request.client.host if request.client else None

    engine = ToolSecurityEngine(session)
    decision = await engine.evaluate(
        actor_id=user.id,
        actor_role=user.role.name if user.role else "user",
        actor_permissions=permissions,
        tool_name=body.tool,
        arguments=body.arguments,
        resource_owner_id=body.resource_owner_id,
        base_risk=0.0,
    )

    invocation = ToolInvocation(
        actor_id=user.id,
        session_id=getattr(request.state, "token_payload", {}).get("sid"),
        tool_id=decision.tool_id,
        tool_name=body.tool,
        arguments=body.arguments,
        resource_id=body.resource_owner_id,
        operation=decision.operation,
        decision=decision.decision,
        risk_score=decision.risk_score,
        reasons=decision.reasons,
        approval_status="not_required",
    )
    session.add(invocation)
    await session.flush()

    if decision.decision == "BLOCK":
        invocation.approval_status = "denied"
        observe_tool("BLOCK")
        await _emit_tool_event(
            session,
            event_type="TOOL_BLOCKED",
            severity="HIGH",
            actor_id=user.id,
            source_ip=source_ip,
            tool=body.tool,
            decision="BLOCK",
            risk_score=decision.risk_score,
            reasons=decision.reasons,
            mitre=decision.mitre,
        )
        await log_audit(
            session,
            action="tools.blocked",
            actor_id=user.id,
            target_type="tool",
            target_id=body.tool,
            details={"reasons": decision.reasons, "risk": decision.risk_score},
            status="denied",
        )
        await session.commit()
        return JSONResponse(
            status_code=403,
            content=ToolInvokeResponse(
                decision="BLOCK",
                risk_score=decision.risk_score,
                reasons=decision.reasons,
                requires_approval=False,
            ).model_dump(),
        )

    if decision.decision == "REQUIRE_APPROVAL":
        invocation.approval_status = "pending"
        observe_tool("REQUIRE_APPROVAL")
        observe_approval("pending")
        approval = Approval(
            invocation_id=invocation.id,
            actor_id=user.id,
            tool_name=body.tool,
            arguments=body.arguments,
            risk_score=decision.risk_score,
            reasons=decision.reasons,
            status="pending",
        )
        session.add(approval)
        await _emit_tool_event(
            session,
            event_type="TOOL_APPROVAL_REQUIRED",
            severity="MEDIUM",
            actor_id=user.id,
            source_ip=source_ip,
            tool=body.tool,
            decision="REQUIRE_APPROVAL",
            risk_score=decision.risk_score,
            reasons=decision.reasons,
            mitre=decision.mitre,
        )
        await session.commit()
        return ToolInvokeResponse(
            decision="REQUIRE_APPROVAL",
            risk_score=decision.risk_score,
            reasons=decision.reasons,
            requires_approval=True,
            approval_id=approval.id,
        )

    # ALLOW or WARN → execute
    observe_tool(decision.decision)
    executor = ToolExecutor()
    try:
        outcome = await executor.execute(body.tool, body.arguments)
    finally:
        await executor.close()

    await _emit_tool_event(
        session,
        event_type="TOOL_INVOKED",
        severity="LOW" if decision.decision == "ALLOW" else "MEDIUM",
        actor_id=user.id,
        source_ip=source_ip,
        tool=body.tool,
        decision=decision.decision,
        risk_score=decision.risk_score,
        reasons=decision.reasons,
    )
    await session.commit()
    return ToolInvokeResponse(
        decision=decision.decision,
        risk_score=decision.risk_score,
        reasons=decision.reasons,
        result=outcome,
        requires_approval=False,
    )


@router.get("/approvals", response_model=list[ApprovalOut])
async def list_approvals(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(APPROVALS_DECIDE))],
):
    result = await session.execute(
        select(Approval).order_by(Approval.created_at.asc())
    )
    return list(result.scalars().all())


@router.post("/approvals/{approval_id}/decide")
async def decide_approval(
    approval_id: str,
    body: ApprovalDecision,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require_permission(APPROVALS_DECIDE))],
):
    approval = await session.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail="Approval already decided")
    if approval.actor_id == user.id:
        raise HTTPException(
            status_code=403, detail="You cannot approve your own request"
        )

    invocation = await session.get(ToolInvocation, approval.invocation_id)
    approval.status = "approved" if body.approve else "denied"
    approval.decided_by = user.id
    from datetime import datetime, timezone

    approval.decided_at = datetime.now(timezone.utc)

    result = None
    if body.approve and invocation is not None:
        invocation.approval_status = "approved"
        invocation.decision = "ALLOW"
        observe_tool("ALLOW")
        observe_approval("approved")
        executor = ToolExecutor()
        try:
            result = await executor.execute(invocation.tool_name, invocation.arguments or {})
        finally:
            await executor.close()
    elif invocation is not None:
        invocation.approval_status = "denied"
        invocation.decision = "BLOCK"
        observe_approval("denied")

    await _emit_tool_event(
        session,
        event_type="TOOL_INVOKED" if body.approve else "TOOL_BLOCKED",
        severity="MEDIUM" if not body.approve else "LOW",
        actor_id=approval.actor_id,
        source_ip=request.client.host if request.client else None,
        tool=approval.tool_name,
        decision="ALLOW" if body.approve else "BLOCK",
        risk_score=approval.risk_score or 0.0,
        reasons=["Human approval granted"] if body.approve else ["Human approval denied"],
    )
    await log_audit(
        session,
        action="approvals.decide",
        actor_id=user.id,
        target_type="approval",
        target_id=approval_id,
        details={"approve": body.approve, "tool": approval.tool_name},
    )
    await session.commit()
    return {
        "approval_id": approval_id,
        "status": approval.status,
        "result": result,
    }
