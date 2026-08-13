"""Run the full attack-lab suite against a running AEGIS stack.

Usage:
    python run_all.py [gateway_base]

Each scenario is evaluated against explicit expectations in
``scenario_expectations.py`` (HTTP status, decision, rule IDs / reasons).
"""
from __future__ import annotations

import json
import sys
import traceback

import attacks
from scenario_expectations import (
    SCENARIO_EXPECTATIONS,
    evaluate_brute_force,
    evaluate_http_scenario,
)

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

RESULTS: list[dict] = []


def main() -> None:
    print(f"AEGIS Attack Lab -> gateway {BASE}")
    alice = attacks.login(BASE, "alice", "Alice@1234")
    operator = attacks.login(BASE, "operator", "Operator@1234")

    funcs: list[tuple[str, object, str]] = [
        (
            "brute_force_login",
            lambda: (
                attacks.clear_login_rate_limit_bucket(attacks.BRUTE_FORCE_TEST_IP),
                attacks.brute_force_login(BASE, attempts=20),
            )[1],
            "10+ x 401 then 429 on login (isolated IP)",
        ),
        ("sql_injection", lambda: attacks.sql_injection(BASE, alice), "403 BLOCK API-006"),
        ("path_traversal", lambda: attacks.path_traversal(BASE, alice), "403 BLOCK API-005"),
        ("ssrf_attempt", lambda: attacks.ssrf_attempt(BASE, alice), "403 BLOCK API-008"),
        ("command_injection", lambda: attacks.command_injection(BASE, alice), "403 BLOCK API-007"),
        ("admin_probe", lambda: attacks.admin_probe(BASE, alice), "403 BLOCK API-017"),
        ("bola_attempt", lambda: attacks.bola_attempt(BASE, alice, target=2), "403 BLOCK API-016"),
        (
            "direct_prompt_injection",
            lambda: attacks.direct_prompt_injection(BASE, alice),
            "202 REQUIRE_REVIEW LLM-001",
        ),
        (
            "jailbreak_attempt",
            lambda: attacks.jailbreak_attempt(BASE, alice),
            "202 REQUIRE_REVIEW LLM-003",
        ),
        (
            "system_prompt_extraction",
            lambda: attacks.system_prompt_extraction(BASE, alice),
            "202 REQUIRE_REVIEW LLM-002",
        ),
        (
            "sensitive_extraction_llm",
            lambda: attacks.sensitive_extraction_llm(BASE, alice),
            "202 REQUIRE_REVIEW LLM-005",
        ),
        (
            "tool_manipulation_prompt",
            lambda: attacks.tool_manipulation_prompt(BASE, alice),
            "202 REQUIRE_REVIEW LLM-006",
        ),
        (
            "malicious_tool_call",
            lambda: attacks.malicious_tool_call(BASE, alice),
            "403 BLOCK tool denied",
        ),
        (
            "cross_subject_tool_call",
            lambda: attacks.cross_subject_tool_call(BASE, alice),
            "403 BLOCK cross-subject",
        ),
        (
            "large_payment_approval",
            lambda: attacks.large_payment_approval(BASE, operator),
            "200 REQUIRE_APPROVAL",
        ),
        (
            "data_exfiltration",
            lambda: attacks.data_exfiltration(BASE, alice),
            "202 REQUIRE_REVIEW LLM-005",
        ),
    ]

    failures = 0
    for name, fn, expected_desc in funcs:
        spec = SCENARIO_EXPECTATIONS[name]
        try:
            result = fn()
            if name == "brute_force_login":
                if not isinstance(result, list):
                    status, summary = "FAIL", "brute_force_login must return status list"
                else:
                    status, summary = evaluate_brute_force(result)
            else:
                status, summary = evaluate_http_scenario(name, result, spec)

            RESULTS.append(
                {
                    "name": name,
                    "attack_type": spec.attack_type,
                    "expected": expected_desc,
                    "actual": summary,
                    "status": status,
                }
            )
            if status == "FAIL":
                failures += 1
            print(f"[{status}] {name:28s} -> {summary[:70]:70s} expected: {expected_desc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            RESULTS.append(
                {
                    "name": name,
                    "expected": expected_desc,
                    "actual": str(exc),
                    "status": "FAIL",
                }
            )
            print(f"[FAIL ] {name:28s} -> {exc.__class__.__name__}: {exc}")
            traceback.print_exc()

    print("\nResults summary:")
    for row in RESULTS:
        print(f"  {row['status']:7s} {row['name']:28s} actual={row['actual']}")

    out_path = "attack_lab_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, indent=1)

    if failures:
        print(f"\n{failures} scenario(s) FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
