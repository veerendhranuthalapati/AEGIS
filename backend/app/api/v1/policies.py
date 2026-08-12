"""Policy management endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import PolicyCreate, PolicyOut, PolicyUpdate
from app.auth.dependencies import CurrentUser, require_permission
from app.auth.permissions import POLICIES_READ, POLICIES_WRITE
from app.database import get_session
from app.models import Policy, PolicyVersion
from app.policies.engine import PolicyEvaluationError, evaluate_tree
from app.services.audit import log_audit

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("", response_model=list[PolicyOut])
async def list_policies(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[CurrentUser, Depends(require_permission(POLICIES_READ))],
):
    result = await session.execute(select(Policy).order_by(Policy.priority.asc()))
    return list(result.scalars().all())


@router.post("", response_model=PolicyOut)
async def create_policy(
    body: PolicyCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require_permission(POLICIES_WRITE))],
):
    try:
        evaluate_tree(body.when, {})
    except PolicyEvaluationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid policy: {exc}") from exc

    existing = await session.execute(
        select(Policy).where(Policy.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Policy name exists")

    policy = Policy(
        name=body.name,
        description=body.description,
        enabled=body.enabled,
        priority=body.priority,
        when=body.when,
        action=body.action,
        response_actions=body.response_actions,
        message=body.message,
        version=1,
    )
    session.add(policy)
    await session.flush()
    session.add(
        PolicyVersion(
            policy_id=policy.id,
            version=1,
            definition=body.when,
            changed_by=user.id,
        )
    )
    await log_audit(
        session,
        action="policies.create",
        actor_id=user.id,
        target_type="policy",
        target_id=policy.name,
    )
    await session.commit()
    return policy


@router.patch("/{policy_id}", response_model=PolicyOut)
async def update_policy(
    policy_id: str,
    body: PolicyUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require_permission(POLICIES_WRITE))],
):
    policy = await session.get(Policy, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")

    if body.when is not None:
        try:
            evaluate_tree(body.when, {})
        except PolicyEvaluationError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid policy: {exc}") from exc
        policy.when = body.when

    if body.name is not None:
        policy.name = body.name
    if body.description is not None:
        policy.description = body.description
    if body.enabled is not None:
        policy.enabled = body.enabled
    if body.priority is not None:
        policy.priority = body.priority
    if body.action is not None:
        policy.action = body.action
    if body.response_actions is not None:
        policy.response_actions = body.response_actions
    if body.message is not None:
        policy.message = body.message

    policy.version += 1
    session.add(
        PolicyVersion(
            policy_id=policy.id,
            version=policy.version,
            definition=policy.when,
            changed_by=user.id,
        )
    )
    await log_audit(
        session,
        action="policies.update",
        actor_id=user.id,
        target_type="policy",
        target_id=policy.name,
        details={"version": policy.version},
    )
    await session.commit()
    return policy


@router.delete("/{policy_id}")
async def delete_policy(
    policy_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(require_permission(POLICIES_WRITE))],
):
    policy = await session.get(Policy, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    await log_audit(
        session,
        action="policies.delete",
        actor_id=user.id,
        target_type="policy",
        target_id=policy.name,
    )
    await session.delete(policy)
    await session.commit()
    return {"detail": "deleted"}
