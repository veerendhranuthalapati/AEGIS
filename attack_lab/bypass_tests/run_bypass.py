"""Structured API bypass suite against a live AEGIS stack.

Usage:
    python run_bypass.py [base_url]

Requires mock-api (:8100) and backend (:8000) running.
"""
from __future__ import annotations

import json
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
GW = f"{BASE}/api/gateway"

RESULTS: list[dict] = []

# Expected outcome categories for pass/fail evaluation.
_OUTCOME_BLOCK = frozenset({"BLOCK", "REQUIRE_REVIEW", "REDACT", "RATE_LIMIT"})
_OUTCOME_ALLOW = frozenset({"ALLOW", "NONE", None})


def login(username: str, password: str) -> str:
    r = httpx.post(f"{BASE}/api/auth/login", json={"username": username, "password": password}, timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]


def gw_get(token: str, path: str) -> httpx.Response:
    return httpx.get(f"{GW}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=15)


def _decision(resp: httpx.Response) -> str | None:
    try:
        return resp.json().get("decision")
    except Exception:  # noqa: BLE001
        return None


def _evaluate(expected: str, resp: httpx.Response) -> bool:
    decision = _decision(resp)
    code = resp.status_code
    if expected == "BLOCK":
        return code in (403, 429, 202) or decision in ("BLOCK", "REQUIRE_REVIEW")
    if expected == "REQUIRE_REVIEW":
        return code in (202, 403) or decision == "REQUIRE_REVIEW"
    if expected == "RATE_LIMIT":
        return code == 429
    if expected == "ALLOW":
        return code == 200 and decision not in ("BLOCK", "REQUIRE_REVIEW")
    return False


def record(category: str, name: str, expected: str, resp: httpx.Response) -> None:
    decision = _decision(resp)
    passed = _evaluate(expected, resp)
    RESULTS.append(
        {
            "category": category,
            "name": name,
            "expected": expected,
            "status_code": resp.status_code,
            "decision": decision,
            "status": "PASS" if passed else "FAIL",
        }
    )
    print(f"[{RESULTS[-1]['status']}] {category}/{name}: HTTP {resp.status_code} decision={decision} (expected {expected})")


def main() -> None:
    alice = login("alice", "Alice@1234")
    bob = login("bob", "Bob@1234")

    sqli_cases = [
        ("url_encoded", "/search?q=%27%20OR%201%3D1%20--"),
        ("double_encoded", "/search?q=%2527%20OR%201%3D1%20--"),
        ("plus_encoded", "/search?q=1+%OR+%1%3D1"),
        ("mixed_case", "/search?q=' Or 1=1 --"),
    ]
    for name, path in sqli_cases:
        record("sqli", name, "BLOCK", gw_get(alice, path))

    trav_cases = [
        ("encoded", "/search?q=..%2F..%2Fetc%2Fpasswd"),
        ("double_encoded", "/search?q=..%252F..%252Fetc%252Fpasswd"),
    ]
    for name, path in trav_cases:
        record("path_traversal", name, "BLOCK", gw_get(alice, path))

    ssrf_cases = [
        ("metadata_ip", "/search?url=http%3A%2F%2F169.254.169.254%2Flatest%2Fmeta-data%2F"),
        ("decimal_ip", "/search?url=http%3A%2F%2F2130706433%2F"),
    ]
    for name, path in ssrf_cases:
        record("ssrf", name, "BLOCK", gw_get(alice, path))

    cmd_cases = [
        ("semicolon", "/search?q=%3B%20id%3B%20whoami"),
        ("pipe", "/search?q=%7C%20id"),
    ]
    for name, path in cmd_cases:
        record("cmd_injection", name, "BLOCK", gw_get(alice, path))

    # BOLA
    record("bola", "users_cross_subject", "BLOCK", gw_get(alice, "/api/users/2"))
    record("bola", "users_own", "ALLOW", gw_get(bob, "/api/users/2"))
    record("bola", "orders_cross_subject", "BLOCK", gw_get(alice, "/api/orders/102"))
    record("bola", "orders_own", "ALLOW", gw_get(bob, "/api/orders/102"))

    # Legitimate
    legit = gw_get(bob, "/api/public/products")
    RESULTS.append(
        {
            "category": "legitimate",
            "name": "public_products",
            "expected": "ALLOW",
            "status_code": legit.status_code,
            "decision": legit.headers.get("x-aegis-decision"),
            "status": "PASS" if _evaluate("ALLOW", legit) else "FAIL",
        }
    )

    failures = sum(1 for r in RESULTS if r["status"] == "FAIL")
    out = {"results": RESULTS, "failures": failures}
    with open("bypass_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"\nBypass suite complete: {len(RESULTS) - failures}/{len(RESULTS)} passed")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
