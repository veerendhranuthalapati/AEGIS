"""Policy evaluation engine tests (pure, no database)."""
import pytest

from app.models import Policy
from app.policies.engine import (
    PolicyEngine,
    PolicyEvaluationError,
    build_context,
    evaluate_condition,
    evaluate_tree,
    resolve_field,
)


def _policy(when: dict, action: str = "BLOCK") -> Policy:
    return Policy(
        name="test",
        description="",
        priority=1,
        enabled=True,
        when=when,
        action=action,
        version=1,
    )


def test_resolve_field_nested():
    ctx = {"actor": {"role": "user"}, "risk_score": 42}
    assert resolve_field(ctx, "actor.role") == "user"
    assert resolve_field(ctx, "risk_score") == 42
    assert resolve_field(ctx, "missing.key") is None


def test_evaluate_condition_operators():
    assert evaluate_condition({"field": "risk_score", "op": "gte", "value": 80}, {"risk_score": 90})
    assert not evaluate_condition({"field": "risk_score", "op": "gte", "value": 80}, {"risk_score": 50})
    assert evaluate_condition({"field": "actor.role", "op": "nin", "value": ["admin"]}, {"actor": {"role": "user"}})
    assert evaluate_condition({"field": "endpoint", "op": "matches", "value": "^/admin"}, {"endpoint": "/admin/users"})
    assert evaluate_condition({"field": "endpoint", "op": "contains", "value": "chat"}, {"endpoint": "/ai/chat"})
    assert evaluate_condition({"field": "jti", "op": "exists"}, {"jti": "abc"})


def test_unknown_operator_raises():
    with pytest.raises(PolicyEvaluationError):
        evaluate_condition({"field": "x", "op": "frobnicate", "value": 1}, {"x": 1})


def test_evaluate_tree_all_any_not():
    tree = {
        "all": [
            {"field": "risk_level", "op": "in", "value": ["HIGH", "CRITICAL"]},
            {
                "any": [
                    {"field": "endpoint", "op": "contains", "value": "chat"},
                    {"field": "endpoint", "op": "contains", "value": "ai"},
                ]
            },
        ]
    }
    ctx = {"risk_level": "HIGH", "endpoint": "/ai/chat"}
    assert evaluate_tree(tree, ctx) is True


def test_evaluate_tree_not():
    tree = {"not": {"field": "actor.role", "op": "eq", "value": "admin"}}
    assert evaluate_tree(tree, {"actor": {"role": "user"}}) is True
    assert evaluate_tree(tree, {"actor": {"role": "admin"}}) is False


def test_engine_evaluate_matches():
    policy = _policy({"all": [{"field": "risk_score", "op": "gte", "value": 80}]})
    engine = PolicyEngine(session=None)  # type: ignore[arg-type]
    assert engine.evaluate(policy, build_context(risk_score=90)) is True
    assert engine.evaluate(policy, build_context(risk_score=10)) is False


def test_engine_broken_policy_raises():
    policy = _policy({"bogus": True})
    engine = PolicyEngine(session=None)  # type: ignore[arg-type]
    with pytest.raises(PolicyEvaluationError):
        engine.evaluate(policy, build_context())


async def test_engine_broken_policy_fails_closed():
    policy = _policy({"bogus": True}, action="BLOCK")
    engine = PolicyEngine(session=None)  # type: ignore[arg-type]
    final_action, results, severity = await engine.evaluate_all(
        build_context(), policies=[policy]
    )
    assert final_action == "BLOCK"
    assert results[0].matched is True
    assert results[0].action == "BLOCK"
