"""Tool-call security for LLM model output — model never executes tools directly."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.models import RequestContext
from app.llm.base import ToolCall
from app.security.agents.engine import ToolSecurityEngine


@dataclass
class ToolCallInspection:
    tool_name: str
    decision: str
    risk_score: float
    reasons: list[str]
    blocked: bool


async def inspect_llm_tool_calls(
    session: AsyncSession,
    ctx: RequestContext,
    tool_calls: list[ToolCall],
    *,
    max_depth: int,
) -> list[ToolCallInspection]:
    """Evaluate each model-emitted tool call through deterministic authorization."""
    if len(tool_calls) > max_depth:
        return [
            ToolCallInspection(
                tool_name="*",
                decision="BLOCK",
                risk_score=90.0,
                reasons=[f"Tool call depth {len(tool_calls)} exceeds limit {max_depth}"],
                blocked=True,
            )
        ]

    engine = ToolSecurityEngine(session)
    results: list[ToolCallInspection] = []
    for call in tool_calls:
        if not call.name:
            results.append(
                ToolCallInspection(
                    tool_name="",
                    decision="BLOCK",
                    risk_score=80.0,
                    reasons=["Empty tool name from model output"],
                    blocked=True,
                )
            )
            continue
        owner = None
        uid = call.arguments.get("user_id") or call.arguments.get("resource_id")
        if uid is not None:
            try:
                owner = str(int(uid))
            except (TypeError, ValueError):
                owner = str(uid)
        decision = await engine.evaluate(
            actor_id=ctx.actor_id,
            actor_role=ctx.actor_role,
            actor_permissions=ctx.actor_permissions or [],
            tool_name=call.name,
            arguments=call.arguments,
            resource_owner_id=owner,
        )
        blocked = decision.decision in ("BLOCK", "REQUIRE_APPROVAL")
        results.append(
            ToolCallInspection(
                tool_name=call.name,
                decision=decision.decision,
                risk_score=decision.risk_score,
                reasons=decision.reasons,
                blocked=blocked,
            )
        )
    return results
