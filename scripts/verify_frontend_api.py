"""Release gate: verify frontend API endpoints against live backend."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent / "docs" / "verification" / "frontend_api_check.json"


def main() -> int:
    results: dict = {"pages": {}, "errors": {}}
    with httpx.Client(base_url=BASE, timeout=15.0) as c:
        r = c.post("/api/auth/login", json={"username": "admin", "password": "Admin@1234"})
        if r.status_code != 200:
            print(f"LOGIN FAIL {r.status_code}")
            return 1
        token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        endpoints = {
            "dashboard_overview": ("GET", "/api/analytics/overview", None),
            "dashboard_requests": ("GET", "/api/analytics/requests", None),
            "threats": ("GET", "/api/threats/live", None),
            "incidents": ("GET", "/api/incidents", None),
            "events": ("GET", "/api/events", {"params": {"limit": 10}}),
            "policies": ("GET", "/api/policies", None),
            "users": ("GET", "/api/users", None),
            "ml_models": ("GET", "/api/ml/models", None),
            "audit": ("GET", "/api/audit", None),
            "tools": ("GET", "/api/tools", None),
            "approvals": ("GET", "/api/tools/approvals", None),
            "auth_me": ("GET", "/api/auth/me", None),
        }
        for name, (method, path, extra) in endpoints.items():
            kwargs = extra or {}
            resp = c.request(method, path, headers=h, **kwargs)
            results["pages"][name] = {"status": resp.status_code, "ok": resp.status_code == 200}
            if resp.status_code != 200:
                results["errors"][name] = resp.text[:200]

        # Error handling checks (401 logout path)
        r401 = c.get("/api/incidents")
        results["errors"]["no_auth"] = {"status": r401.status_code, "ok": r401.status_code == 401}

        # alice cannot list users (403 expected)
        r_alice = c.post("/api/auth/login", json={"username": "alice", "password": "Alice@1234"})
        ah = {"Authorization": f"Bearer {r_alice.json()['access_token']}"}
        r403 = c.get("/api/users", headers=ah)
        results["errors"]["alice_users"] = {"status": r403.status_code, "ok": r403.status_code == 403}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    failed = [k for k, v in results["pages"].items() if not v["ok"]]
    print(json.dumps(results, indent=2))
    print(f"FAILED_PAGES={failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
