"""Policy evaluation engine.

Policies are stored as JSON condition trees and evaluated with a small,
safe, deterministic matcher (no ``eval``, no code execution). Multiple
matching policies combine and the most severe action wins (fail closed).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Policy

logger = structlog.get_logger("aegis.policies")

ACTION_SEVERITY = {"ALLOW": 1, "WARN": 2, "REQUIRE_REVIEW": 3, "BLOCK": 4}


@dataclass
class PolicyResult:
    policy: Policy
    matched: bool
    action: str
    message: str | None = None
    response_actions: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "policy_id": self.policy.id,
            "policy_name": self.policy.name,
            "version": self.policy.version,
            "matched": self.matched,
            "action": self.action,
            "message": self.message,
        }


class PolicyEvaluationError(Exception):
    pass


def resolve_field(context: dict, path: str) -> Any:
    current: Any = context
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _op_matches(field_value: Any, op: str, value: Any) -> bool:
    if op in ("eq", "ne"):
        result = field_value == value
        return result if op == "eq" else not result
    if op in ("gt", "gte", "lt", "lte"):
        try:
            if field_value is None:
                return False
            if op == "gt":
                return field_value > value
            if op == "gte":
                return field_value >= value
            if op == "lt":
                return field_value < value
            return field_value <= value
        except TypeError:
            return False
    if op == "in":
        return field_value in (value or [])
    if op == "nin":
        return field_value not in (value or [])
    if op == "contains":
        return value in (field_value or "")
    if op == "exists":
        return field_value is not None
    if op == "matches":
        try:
            return bool(re.search(value, str(field_value or "")))
        except re.error as exc:
            raise PolicyEvaluationError(f"bad regex: {value}") from exc
    raise PolicyEvaluationError(f"unknown operator: {op}")


def evaluate_condition(node: dict, context: dict) -> bool:
    """Evaluate a single condition node (``field`` + ``op`` + ``value``)."""
    if "field" not in node or "op" not in node:
        raise PolicyEvaluationError(f"invalid condition node: {node}")
    field_value = resolve_field(context, node["field"])
    return _op_matches(field_value, node["op"], node.get("value"))


def evaluate_tree(tree: Any, context: dict) -> bool:
    """Evaluate a condition tree of all/any/not operators."""
    if isinstance(tree, dict):
        if "all" in tree:
            return all(evaluate_tree(child, context) for child in tree["all"])
        if "any" in tree:
            return any(evaluate_tree(child, context) for child in tree["any"])
        if "not" in tree:
            return not evaluate_tree(tree["not"], context)
        if "field" in tree:
            return evaluate_condition(tree, context)
    raise PolicyEvaluationError(f"unsupported policy tree node: {tree}")


def build_context(**kwargs: Any) -> dict:
    """Build an evaluation context with computed convenience fields."""
    context = dict(kwargs)
    now = datetime.now(timezone.utc)
    context["now"] = now.isoformat()
    context["time_of_day"] = now.hour
    context["day_of_week"] = now.weekday()  # 0 = Monday
    return context


class PolicyEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_enabled(self) -> list[Policy]:
        result = await self._session.execute(
            select(Policy)
            .where(Policy.enabled == True)  # noqa: E712
            .order_by(Policy.priority.asc())
        )
        return list(result.scalars().all())

    def evaluate(self, policy: Policy, context: dict) -> bool:
        return evaluate_tree(policy.when, context)

    async def evaluate_all(
        self, context: dict, policies: list[Policy] | None = None
    ) -> tuple[str, list[PolicyResult], int]:
        """Return (final_action, results, effective_severity).

        Policies that cannot be evaluated (malformed conditions) fail CLOSED:
        they are treated as matched with a BLOCK action so a broken security
        policy can never silently disable protection.
        """
        policies = policies if policies is not None else await self.load_enabled()
        results: list[PolicyResult] = []
        final_action = "ALLOW"
        best_severity = ACTION_SEVERITY["ALLOW"]
        for policy in policies:
            try:
                matched = self.evaluate(policy, context)
            except PolicyEvaluationError as exc:
                matched = True
                logger.error(
                    "policy.evaluation_failed_failing_closed",
                    policy=policy.name,
                    version=policy.version,
                    error=str(exc),
                )
                results.append(
                    PolicyResult(
                        policy=policy,
                        matched=True,
                        action="BLOCK",
                        message=f"Policy evaluation failed; failing closed: {exc}",
                    )
                )
                severity = ACTION_SEVERITY["BLOCK"]
                if severity > best_severity:
                    best_severity = severity
                    final_action = "BLOCK"
                continue
            results.append(
                PolicyResult(
                    policy=policy,
                    matched=matched,
                    action=policy.action,
                    message=policy.message,
                    response_actions=policy.response_actions or [],
                )
            )
            if matched:
                severity = ACTION_SEVERITY.get(policy.action, 1)
                if severity > best_severity:
                    best_severity = severity
                    final_action = policy.action
        return final_action, results, best_severity
