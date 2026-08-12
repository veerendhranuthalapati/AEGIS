"""AI agent / tool-call security engine.

Every tool invocation passes through AEGIS. The engine combines identity,
permissions, tool category, target resource, operation type and risk before
allowing execution. The LLM is never a trusted authorization mechanism.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tool

_DESTRUCTIVE_CATEGORIES = {"destructive", "payment"}


@dataclass
class ToolDecision:
    decision: str  # ALLOW | WARN | REQUIRE_APPROVAL | BLOCK
    risk_score: float
    reasons: list[str] = field(default_factory=list)
    requires_approval: bool = False
    operation: str | None = None
    mitre: list[str] = field(default_factory=list)
    tool_id: str | None = None
    tool_name: str | None = None


class ToolSecurityEngine:
    """Evaluates a single tool invocation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_tool(self, name: str) -> Tool | None:
        result = await self._session.execute(
            select(Tool).where(Tool.name == name)
        )
        return result.scalar_one_or_none()

    def _score_arguments(self, arguments: dict | None) -> float:
        args = arguments or {}
        score = 0.0
        if args.get("amount"):
            try:
                amount = float(args["amount"])
                if amount >= 1_000_000:
                    score += 0.6
                elif amount >= 100_000:
                    score += 0.35
                elif amount >= 10_000:
                    score += 0.15
            except (TypeError, ValueError):
                pass
        if args.get("count"):
            try:
                count = float(args["count"])
                if count >= 10_000:
                    score += 0.4
                elif count >= 1_000:
                    score += 0.2
            except (TypeError, ValueError):
                pass
        if args.get("delete_all") is True or args.get("all") is True:
            score += 0.5
        if args.get("permanent") is True:
            score += 0.3
        return min(1.0, score)

    async def evaluate(
        self,
        *,
        actor_id: str | None,
        actor_role: str | None,
        actor_permissions: list[str],
        tool_name: str,
        arguments: dict | None,
        resource_owner_id: str | None = None,
        base_risk: float = 0.0,
    ) -> ToolDecision:
        if not actor_id:
            return ToolDecision(
                decision="BLOCK",
                risk_score=1.0,
                reasons=["Authentication required to invoke tools"],
                mitre=["T1078"],
            )

        if "agents:invoke" not in (actor_permissions or []):
            return ToolDecision(
                decision="BLOCK",
                risk_score=1.0,
                reasons=["Actor lacks agents:invoke permission"],
                mitre=["T1078"],
            )

        tool = await self.get_tool(tool_name)
        if tool is None:
            return ToolDecision(
                decision="BLOCK",
                risk_score=1.0,
                reasons=[f"Unknown tool: {tool_name}"],
                mitre=["T1213"],
                tool_name=tool_name,
            )
        if not tool.enabled:
            return ToolDecision(
                decision="BLOCK",
                risk_score=1.0,
                reasons=[f"Tool disabled: {tool_name}"],
                mitre=["T1213"],
                tool_id=tool.id,
                tool_name=tool.name,
            )

        allowed_roles = tool.default_allowed_roles or ["admin", "operator"]
        if actor_role not in allowed_roles:
            return ToolDecision(
                decision="BLOCK",
                risk_score=0.9,
                reasons=[
                    f"Role '{actor_role}' is not allowed to invoke '{tool_name}'"
                ],
                mitre=["T1078"],
                tool_id=tool.id,
                tool_name=tool.name,
            )

        reasons: list[str] = []
        risk = base_risk
        arg_score = self._score_arguments(arguments)
        risk = max(risk, arg_score * 0.8)
        operation = tool.category

        if tool.sensitive and actor_role not in ("admin", "operator"):
            risk = max(risk, 0.6)
            reasons.append(f"Tool '{tool_name}' exposes sensitive data")

        if tool.category in _DESTRUCTIVE_CATEGORIES and actor_role != "admin":
            risk = max(risk, 0.75)
            reasons.append(f"Destructive operation requires elevated role ({tool.category})")

        if resource_owner_id and resource_owner_id != actor_id and actor_role != "admin":
            risk = max(risk, 0.95)
            reasons.append("Target resource is owned by another subject (BOLA check)")
            return ToolDecision(
                decision="BLOCK",
                risk_score=min(1.0, risk),
                reasons=reasons + ["Cross-subject resource access denied"],
                mitre=["T1078"],
                operation=operation,
                tool_id=tool.id,
                tool_name=tool.name,
            )

        requires_approval = False
        if tool.requires_approval:
            requires_approval = True
            reasons.append(f"Tool '{tool_name}' requires human approval by policy")
        if tool.approval_threshold_risk is not None and risk >= tool.approval_threshold_risk:
            requires_approval = True
            reasons.append(f"Risk {risk:.0f} exceeds approval threshold")
        if tool.category == "payment" and (arguments or {}).get("amount"):
            try:
                if float((arguments or {})["amount"]) >= 100_000:
                    requires_approval = True
                    reasons.append("Large payment requires human approval")
            except (TypeError, ValueError):
                pass

        if requires_approval:
            return ToolDecision(
                decision="REQUIRE_APPROVAL",
                risk_score=min(1.0, risk),
                reasons=reasons,
                requires_approval=True,
                operation=operation,
                mitre=["T1213"],
                tool_id=tool.id,
                tool_name=tool.name,
            )

        if risk >= 0.9:
            return ToolDecision(
                decision="BLOCK",
                risk_score=min(1.0, risk),
                reasons=reasons + ["Aggregate risk too high for tool call"],
                mitre=["T1213"],
                operation=operation,
                tool_id=tool.id,
                tool_name=tool.name,
            )

        if risk >= 0.6:
            decision = "WARN"
            reasons.append("Tool call carries elevated risk")
        else:
            decision = "ALLOW"
        return ToolDecision(
            decision=decision,
            risk_score=min(1.0, risk),
            reasons=reasons or ["No policy violation detected"],
            operation=operation,
            tool_id=tool.id,
            tool_name=tool.name,
        )
