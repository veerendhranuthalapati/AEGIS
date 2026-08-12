"""Run the full attack-lab suite against a running AEGIS stack.

Usage:
    python run_all.py [gateway_base]

The script prints, for every attack: purpose, expected detection and the
actual HTTP status observed. Everything stays in the local environment.
"""
from __future__ import annotations

import json
import sys
import traceback

import attacks

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

RESULTS: list[dict] = []


def _evaluate(name: str, expected: str, actual, result) -> tuple[str, str]:
    """Return (status, summary_text) for a scenario."""
    if name == "brute_force_login":
        if not isinstance(result, list) or not result:
            return "FAIL", "no login statuses recorded"
        if 429 not in result:
            return "FAIL", f"no 429 in {result}"
        idx = result.index(429)
        pre = result[:idx]
        if pre and any(code != 401 for code in pre):
            return "FAIL", f"expected 401 before 429, got {result}"
        return "PASS", f"429 at attempt {idx + 1} (statuses={result})"

    text = str(actual)
    if (
        text.startswith(("429", "403", "202"))
        or "BLOCK" in text
        or "REQUIRE" in text
    ):
        return "PASS", text
    if name == "missing_auth" and text.startswith("401"):
        return "PASS", text
    return "FAIL", text


def record(name: str, expected: str, actual, result) -> None:
    status, summary = _evaluate(name, expected, actual, result)
    RESULTS.append(
        {
            "name": name,
            "expected": expected,
            "actual": summary,
            "status": status,
        }
    )


def response_summary(resp) -> str:
    """Gateway and tool endpoints report decisions in a JSON body."""
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        data = None
    if isinstance(data, dict) and data.get("decision"):
        return f"HTTP {resp.status_code} decision={data['decision']}"
    return f"HTTP {resp.status_code}"


def main() -> None:
    print(f"AEGIS Attack Lab -> gateway {BASE}")
    alice = attacks.login(BASE, "alice", "Alice@1234")
    operator = attacks.login(BASE, "operator", "Operator@1234")

    funcs = [
        (
            "brute_force_login",
            lambda: (
                attacks.clear_login_rate_limit_bucket(attacks.BRUTE_FORCE_TEST_IP),
                attacks.brute_force_login(BASE, attempts=20),
            )[1],
            "401 then 429 Too Many Requests (isolated test IP bucket)",
        ),
        ("sql_injection", lambda: attacks.sql_injection(BASE, alice), "403 BLOCK + SQLI_INDICATOR"),
        ("path_traversal", lambda: attacks.path_traversal(BASE, alice), "403 BLOCK + PATH_TRAVERSAL"),
        ("ssrf_attempt", lambda: attacks.ssrf_attempt(BASE, alice), "403 BLOCK + SSRF_INDICATOR"),
        ("command_injection", lambda: attacks.command_injection(BASE, alice), "403 BLOCK + CMD_INJ_INDICATOR"),
        ("admin_probe", lambda: attacks.admin_probe(BASE, alice), "403 BLOCK + ADMIN_PROBE"),
        ("bola_attempt", lambda: attacks.bola_attempt(BASE, alice, target=2), "403 BLOCK + BOLA_ATTEMPT"),
        ("direct_prompt_injection", lambda: attacks.direct_prompt_injection(BASE, alice), "PROMPT_INJECTION + BLOCK/REQUIRE_REVIEW"),
        ("jailbreak_attempt", lambda: attacks.jailbreak_attempt(BASE, alice), "JAILBREAK_ATTEMPT + BLOCK/REQUIRE_REVIEW"),
        ("system_prompt_extraction", lambda: attacks.system_prompt_extraction(BASE, alice), "SYSTEM_PROMPT_EXTRACTION + BLOCK/REQUIRE_REVIEW"),
        ("sensitive_extraction_llm", lambda: attacks.sensitive_extraction_llm(BASE, alice), "SENSITIVE_EXTRACTION + BLOCK/REQUIRE_REVIEW"),
        ("tool_manipulation_prompt", lambda: attacks.tool_manipulation_prompt(BASE, alice), "TOOL_MANIPULATION + BLOCK/REQUIRE_REVIEW"),
        ("malicious_tool_call", lambda: attacks.malicious_tool_call(BASE, alice), "TOOL_BLOCKED / REQUIRE_APPROVAL"),
        ("cross_subject_tool_call", lambda: attacks.cross_subject_tool_call(BASE, alice), "TOOL_BLOCKED (BOLA)"),
        ("large_payment_approval", lambda: attacks.large_payment_approval(BASE, operator), "202/200 REQUIRE_APPROVAL (approval queue)"),
        ("data_exfiltration", lambda: attacks.data_exfiltration(BASE, alice), "SENSITIVE_EXTRACTION + BLOCK/REQUIRE_REVIEW"),
    ]

    failures = 0
    for name, fn, expected in funcs:
        try:
            result = fn()
            if isinstance(result, list):
                actual = result[-1] if result else "no statuses"
                summary = f"last={actual} (seen={sorted(set(result))})"
            else:
                actual = response_summary(result)
                summary = actual
            record(name, expected, actual, result)
            row = RESULTS[-1]
            if row["status"] == "FAIL":
                failures += 1
            print(f"[{row['status']}] {name:28s} -> {row['actual'][:60]:60s} expected: {expected}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            RESULTS.append({"name": name, "expected": expected, "actual": str(exc), "status": "FAIL"})
            print(f"[FAIL ] {name:28s} -> {exc.__class__.__name__}: {exc}")
            traceback.print_exc()

    print("\nResults summary:")
    for row in RESULTS:
        print(f"  {row['status']:7s} {row['name']:28s} actual={row['actual']}")

    with open("attack_lab_results.json", "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, indent=1)

    if failures:
        print(f"\n{failures} scenario(s) FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
