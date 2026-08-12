# AEGIS Backend Security Hardening Report

Date: 2026-08-12  
Classification: **Production-oriented prototype** (backend)

---

## Baseline (verified before hardening)

| Area | Status |
|------|--------|
| Unit tests | 108 passing |
| E2E integration | Passing (legitimate + API + LLM + approvals) |
| Attack lab | 16/16 reported (brute-force validation was too permissive) |
| Ruff | Clean |
| mypy | 2 errors in correlation engine (plus pre-existing issues elsewhere) |
| BOLA | `/api/users` path-only + post-forward orders |
| Login rate limit | Worked in TestClient; attack lab masked failures |
| Frontend / Terraform / CI | Not implemented |

---

## Vulnerabilities Found

### 1. Attack-lab brute-force false PASS (Medium)

**Reproduction:** `run_all.py` accepted HTTP `401` as PASS for brute-force.  
**Root cause:** Two compounding issues:
1. Pass criteria treated `401` as success (`401` in allowed prefix list).
2. Brute-force targeted the seed `admin` account, which **locks after 5 failures** (`auth_lockout_max_failed=5`), returning `401` indefinitely and never reaching the rate-limit threshold (10/min).

**Fix:** Strict validation requiring `429` after a series of `401`s; use non-existent username `bruteforce_lab_target`; isolated bucket via `X-Forwarded-For: 198.18.0.99`; clear bucket before scenario.

**Verified:** E2E attack lab now reports `429 at attempt 11`.

### 2. Inconsistent client IP for rate limiting (Medium)

**Issue:** Login rate-limit keys used `request.client.host` only; attack-lab bucket collided with prior E2E logins on `127.0.0.1`.

**Fix:** Added `app/core/client_ip.py` with `resolve_client_ip()` honoring `X-Forwarded-For` when `trust_forwarded_headers=true` (dev default). Used in auth and gateway.

### 3. Rate-limit timezone bug on SQLite (Low)

**Issue:** `check_rate_limit` subtracted naive/aware datetimes on SQLite test paths.

**Fix:** `_as_utc()` normalization in `app/services/ratelimit.py`.

### 4. Incomplete BOLA coverage (Medium)

**Issue:** Query-parameter BOLA only on `/api/users`; orders relied solely on post-forward check.

**Fix:** Extended `_BOLA_QUERY_RESOURCE_PATHS` to include `/api/orders` for `user_id` query params. Post-forward ownership for `/api/orders/{id}` unchanged (correct design).

### 5. Correlation duplicate event inflation (Low)

**Issue:** Duplicate `event_id` values could inflate incident evidence lists.

**Fix:** Deduplicate matched events and `related_event_ids` in correlation engine.

### 6. Stale dev server processes (Operational)

**Issue:** Stale uvicorn on port 8000 served outdated code during manual HTTP tests.

**Fix:** `e2e.py` now kills listeners on ports 8000/8100 before starting stack.

---

## Fixes Applied

| Component | Change |
|-----------|--------|
| `.gitignore` | Root gitignore for secrets, DB, venv, ML artifacts |
| `app/core/client_ip.py` | Consistent IP extraction |
| `app/api/v1/auth.py` | Uses `resolve_client_ip` for login rate limits |
| `app/api/v1/gateway.py` | Uses `resolve_client_ip` for telemetry |
| `app/services/ratelimit.py` | UTC-safe datetime handling |
| `app/gateway/service.py` | Orders query-param BOLA |
| `app/security/correlation/engine.py` | Dedup + mypy fix |
| `attack_lab/scripts/run_all.py` | Strict PASS/FAIL; exit 1 on failures |
| `attack_lab/scripts/attacks.py` | Isolated brute-force IP/user; bucket reset helper |
| `e2e.py` | Port cleanup before stack start |

---

## Regression Tests Added (160 total)

| File | Coverage |
|------|----------|
| `test_login_rate_limit.py` | Service, TestClient (SQLite + PostgreSQL), X-Forwarded-For isolation |
| `test_api_bypass.py` | SQLi, traversal, SSRF, cmd injection encoding variants |
| `test_llm_bypass.py` | Prompt injection, jailbreak, benign prompts |
| `test_jwt_authorization.py` | Tampered/expired tokens, gateway auth rejection |
| `test_tool_security.py` | Permissions, cross-subject, unknown tools |
| `test_correlation_security.py` | Dedup, timeline ordering, empty input |
| `test_bola_enforcement.py` | Orders query BOLA, users own/other resource |

Live bypass suite: `attack_lab/bypass_tests/run_bypass.py`

---

## Attack Coverage Tested

- **API:** SQLi, path traversal, SSRF, cmd injection (encoded variants), admin probe, BOLA
- **LLM:** Prompt injection, jailbreak, extraction → `REQUIRE_REVIEW` (policy-intentional)
- **Tools:** Role blocks, cross-subject, approval queue
- **Auth:** JWT tampering, missing auth, login rate limit 401→429
- **Redaction:** Existing 11 tests (SSN, email, API keys, PEM, etc.)

---

## Performance (unchanged — documented only)

Serial gateway overhead ~215 ms per `docs/PERFORMANCE.md`. Primary bottleneck: behavioral stats SQL (~110 ms). No optimization applied (per instructions).

---

## Remaining Gaps

1. **Heuristic detection** — Regex LLM/API rules are bypassable with novel encodings (e.g. invalid `%OR` sequences).
2. **ML metrics** — Synthetic data with trivial class separation; not production-grade.
3. **Tool scenarios during long E2E** — 3 attack-lab tool cases returned HTTP 500 at end of full E2E (likely backend exhaustion/state); need isolated reproduction.
4. **mypy** — Correlation engine fixed; ~31 pre-existing errors remain in other modules.
5. **Multi-worker rate limits** — DB-backed (correct), but `trust_forwarded_headers` must be disabled in production without trusted proxy.
6. **Frontend, CI, Terraform** — Out of scope for this phase.

---

## Security Limitations (honest assessment)

AEGIS backend is a **production-oriented prototype**, not production-ready:

- Deterministic rules + optional ML on synthetic data
- LLM threats default to `REQUIRE_REVIEW`, not `BLOCK` (configurable via policy)
- BOLA enforced where ownership semantics are known; not a full authz engine
- Rate limiting is per-IP bucket; distributed attacks need edge/WAF controls
- No WAF, no mTLS, no HSM key storage in this codebase

**Do not claim complete security.** Continue red-team iteration before any production deployment.

---

## Verification Commands

```powershell
# Unit tests (from backend/)
.venv\Scripts\python.exe -m pytest tests -q

# E2E (from repo root)
backend\.venv\Scripts\python.exe e2e.py

# Attack lab (backend + mock-api must be running)
cd attack_lab\scripts
..\..\backend\.venv\Scripts\python.exe run_all.py

# Bypass suite
cd attack_lab\bypass_tests
..\..\backend\.venv\Scripts\python.exe run_bypass.py
```

---

## E2E / Attack Lab Results (2026-08-12 post-hardening)

- **Unit tests:** 160 passed
- **Brute force:** PASS — `429 at attempt 11` after ten `401`s
- **API/LLM scenarios:** PASS
- **Tool scenarios (end of long E2E):** 3× HTTP 500 — investigate separately
