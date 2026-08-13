"""Explicit pass criteria for each attack-lab scenario.

Each scenario must match HTTP status, security decision, and detection signals.
A block for the *wrong* reason (e.g. auth failure on a SQLi payload) is a FAIL.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScenarioExpectation:
    attack_type: str
    expected_http_status: set[int]
    expected_decision: str | set[str]
    rule_ids_any: frozenset[str] = frozenset()
    reason_substrings_any: frozenset[str] = frozenset()
    forbidden_decisions: frozenset[str] = frozenset(("ALLOW",))
    requires_approval: bool | None = None
    notes: str = ""


# Gateway scenarios include findings with rule_id. Tool scenarios use reasons.
SCENARIO_EXPECTATIONS: dict[str, ScenarioExpectation] = {
    "brute_force_login": ScenarioExpectation(
        attack_type="T1110 brute force (login rate limit)",
        expected_http_status=set(),  # evaluated from status list
        expected_decision="RATE_LIMIT",
        notes="401s then 429 on /api/auth/login — not gateway decision JSON",
    ),
    "sql_injection": ScenarioExpectation(
        attack_type="SQL injection",
        expected_http_status={403},
        expected_decision="BLOCK",
        rule_ids_any=frozenset({"API-006"}),
    ),
    "path_traversal": ScenarioExpectation(
        attack_type="Path traversal",
        expected_http_status={403},
        expected_decision="BLOCK",
        rule_ids_any=frozenset({"API-005"}),
    ),
    "ssrf_attempt": ScenarioExpectation(
        attack_type="SSRF",
        expected_http_status={403},
        expected_decision="BLOCK",
        rule_ids_any=frozenset({"API-008"}),
    ),
    "command_injection": ScenarioExpectation(
        attack_type="Command injection",
        expected_http_status={403},
        expected_decision="BLOCK",
        rule_ids_any=frozenset({"API-007"}),
    ),
    "admin_probe": ScenarioExpectation(
        attack_type="Admin endpoint probing",
        expected_http_status={403},
        expected_decision="BLOCK",
        rule_ids_any=frozenset({"API-017"}),
    ),
    "bola_attempt": ScenarioExpectation(
        attack_type="BOLA/IDOR (cross-subject user resource)",
        expected_http_status={403},
        expected_decision="BLOCK",
        rule_ids_any=frozenset({"API-016"}),
    ),
    "direct_prompt_injection": ScenarioExpectation(
        attack_type="Prompt injection",
        expected_http_status={202},
        expected_decision="REQUIRE_REVIEW",
        rule_ids_any=frozenset({"LLM-001"}),
    ),
    "jailbreak_attempt": ScenarioExpectation(
        attack_type="Jailbreak",
        expected_http_status={202},
        expected_decision="REQUIRE_REVIEW",
        rule_ids_any=frozenset({"LLM-003"}),
    ),
    "system_prompt_extraction": ScenarioExpectation(
        attack_type="System prompt extraction",
        expected_http_status={202},
        expected_decision="REQUIRE_REVIEW",
        rule_ids_any=frozenset({"LLM-002"}),
    ),
    "sensitive_extraction_llm": ScenarioExpectation(
        attack_type="Sensitive data extraction via LLM",
        expected_http_status={202},
        expected_decision="REQUIRE_REVIEW",
        rule_ids_any=frozenset({"LLM-005"}),
    ),
    "tool_manipulation_prompt": ScenarioExpectation(
        attack_type="Tool manipulation via prompt",
        expected_http_status={202},
        expected_decision="REQUIRE_REVIEW",
        rule_ids_any=frozenset({"LLM-006"}),
    ),
    "data_exfiltration": ScenarioExpectation(
        attack_type="Data exfiltration via LLM",
        expected_http_status={202},
        expected_decision="REQUIRE_REVIEW",
        rule_ids_any=frozenset({"LLM-005"}),
    ),
    "malicious_tool_call": ScenarioExpectation(
        attack_type="Unauthorized destructive tool",
        expected_http_status={403},
        expected_decision="BLOCK",
        reason_substrings_any=frozenset(
            {"not allowed", "Role", "agents:invoke", "delete_user", "disabled"}
        ),
    ),
    "cross_subject_tool_call": ScenarioExpectation(
        attack_type="Cross-subject tool access (BOLA)",
        expected_http_status={403},
        expected_decision="BLOCK",
        reason_substrings_any=frozenset({"Cross-subject", "owned", "BOLA", "denied"}),
    ),
    "large_payment_approval": ScenarioExpectation(
        attack_type="High-value payment requiring approval",
        expected_http_status={200},
        expected_decision="REQUIRE_APPROVAL",
        requires_approval=True,
        reason_substrings_any=frozenset({"approval", "payment", "Large"}),
    ),
}


def parse_gateway_body(data: dict[str, Any] | None) -> tuple[str | None, set[str], list[str]]:
    if not isinstance(data, dict):
        return None, set(), []
    decision = data.get("decision")
    findings = data.get("findings") or []
    rule_ids = {str(f.get("rule_id")) for f in findings if isinstance(f, dict) and f.get("rule_id")}
    reasons = [str(r) for r in (data.get("reasons") or [])]
    if data.get("reason"):
        reasons.append(str(data["reason"]))
    return decision, rule_ids, reasons


def evaluate_brute_force(statuses: list[int], limit: int = 10) -> tuple[str, str]:
    if not statuses:
        return "FAIL", "no login statuses recorded"
    if 429 not in statuses:
        return "FAIL", f"expected 429 rate limit, got {statuses}"
    idx = statuses.index(429)
    pre = statuses[:idx]
    if not pre:
        return "FAIL", f"429 on first attempt — expected {limit} failed logins first"
    if any(code != 401 for code in pre):
        return "FAIL", f"expected only 401 before 429, got {statuses}"
    if len(pre) < limit:
        return "FAIL", f"expected at least {limit} x 401 before 429, got {len(pre)}"
    return "PASS", f"{len(pre)} x 401 then 429 (statuses={statuses})"


def evaluate_http_scenario(
    name: str,
    resp,
    spec: ScenarioExpectation,
) -> tuple[str, str]:
    if resp is None:
        return "FAIL", "no HTTP response (connection/infrastructure failure)"

    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        data = None

    status = resp.status_code
    decision, rule_ids, reasons = parse_gateway_body(data)
    reasons_blob = " ".join(reasons).lower()

    if status not in spec.expected_http_status:
        return (
            "FAIL",
            f"HTTP {status} not in {sorted(spec.expected_http_status)}; "
            f"decision={decision} rule_ids={sorted(rule_ids)}",
        )

    expected_decisions = (
        {spec.expected_decision}
        if isinstance(spec.expected_decision, str)
        else set(spec.expected_decision)
    )
    if decision not in expected_decisions:
        return (
            "FAIL",
            f"decision={decision!r} expected one of {sorted(expected_decisions)}; "
            f"HTTP {status} rule_ids={sorted(rule_ids)} reasons={reasons[:3]}",
        )

    if decision in spec.forbidden_decisions:
        return "FAIL", f"forbidden decision {decision}"

    # Wrong-reason guard: auth-only block on attack scenarios
    if status == 401 or (decision == "BLOCK" and "unauthenticated" in reasons_blob):
        return "FAIL", "blocked due to authentication failure, not attack detection"

    if spec.rule_ids_any and not (rule_ids & set(spec.rule_ids_any)):
        return (
            "FAIL",
            f"missing expected rule_id(s) {sorted(spec.rule_ids_any)}; "
            f"got {sorted(rule_ids)} decision={decision} HTTP {status}",
        )

    if spec.reason_substrings_any:
        if not any(sub.lower() in reasons_blob for sub in spec.reason_substrings_any):
            return (
                "FAIL",
                f"reasons missing any of {sorted(spec.reason_substrings_any)}; "
                f"got {reasons}",
            )

    if spec.requires_approval is not None and isinstance(data, dict):
        ra = data.get("requires_approval")
        if bool(ra) != spec.requires_approval:
            return "FAIL", f"requires_approval={ra!r} expected {spec.requires_approval}"

    summary = f"HTTP {status} decision={decision}"
    if rule_ids:
        summary += f" rules={sorted(rule_ids)}"
    return "PASS", summary
