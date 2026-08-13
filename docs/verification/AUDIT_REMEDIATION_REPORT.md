# Audit Remediation Report

**Date:** 2026-08-13  
**Scope:** Correctness, security quality, test quality, release integrity — **no new features**  
**Classification unchanged:** **PRODUCTION-ORIENTED PROTOTYPE**

---

## 1. Findings addressed

| ID | Finding | Action |
|----|---------|--------|
| CR-1 | Attack-lab permissive PASS | Strict scenario expectations in `scenario_expectations.py` + rewritten `run_all.py` |
| CR-2 | Release not reproducible | `RELEASE_CONTENTS.md` — HEAD vs uncommitted split |
| M-3 | JWT in localStorage | `JWT_STORAGE_MIGRATION.md` — deferred with bounded plan |
| M-4 | BOLA partial coverage | `AUTHORIZATION_MATRIX.md` |
| M-5 | Rate limit not distributed | `RATE_LIMITING.md` |
| M-6 | ML V1 IF test leakage | `iforest.fit(X_train)` + `ML_V1_LEAKAGE_FIX.md` |
| M-7 | `/health` no DB check | Added `GET /ready` + tests; `/health` remains liveness-only |
| M-8 | Tool BLOCK returned HTTP 200 | Tool BLOCK → **HTTP 403** + integration test |
| M-9 | Stale doc test counts | RESUME, PROJECT_STORY, INTERVIEW_GUIDE updated |
| L-10 | No duplicate approval HTTP test | `test_approval_idempotency.py` (409 + single execute) |
| — | Terraform validate failure | Removed unused RDS `vpc_id` variable; fmt applied |
| — | SQLite token expiry compare | Timezone-aware compare in `ensure_token_valid` |

---

## 2. Findings intentionally deferred

| Finding | Reason |
|---------|--------|
| JWT → httpOnly cookies | Requires full auth architecture migration |
| Redis rate limiting | Infrastructure scope; documented only |
| ML V2 online integration | Evaluation-only by design this phase |
| Real LLM live verification | No API key; code exists uncommitted |
| BOLA on all upstream routes | Requires upstream owner metadata |
| Attack lab live re-run | **NOT VERIFIED** — Docker/Postgres unavailable on host |
| AWS deploy / SQS app code | Out of scope |

---

## 3. Test results (2026-08-13 remediation run)

| Suite | Result |
|-------|--------|
| New: health/ready | **2/2 PASS** |
| New: approval idempotency | **2/2 PASS** |
| New: tool HTTP 403 | **1/1 PASS** |
| Full pytest | **225 collected** — 224 pass without Postgres; 1 postgres integration test fails when DB down |
| Ruff | **PASS** |
| Mypy | **PASS** |
| Frontend vitest | **7/7 PASS** |
| terraform validate | **PASS** |
| terraform fmt -check | **PASS** |
| Attack lab live | **NOT VERIFIED** (Docker daemon down; stack not running) |
| Bypass suite live | **NOT VERIFIED** (requires gateway on :8000) |
| Docker build | **NOT VERIFIED** |

---

## 4. Attack-lab assertion quality

Each scenario now requires:

- Exact HTTP status set
- Exact `decision` value
- `rule_id` intersection for gateway attacks (e.g. API-006 for SQLi, LLM-001 for prompt injection)
- Reason substring checks for tool endpoints
- Auth-failure blocks **fail** wrong-reason scenarios
- Brute force: ≥10×401 then 429

See `attack_lab/scripts/scenario_expectations.py`.

---

## 5. Authorization coverage

Documented in [AUTHORIZATION_MATRIX.md](AUTHORIZATION_MATRIX.md).

---

## 6. ML leakage correction

Isolation Forest now trains on train split only. See [ML_V1_LEAKAGE_FIX.md](ML_V1_LEAKAGE_FIX.md). ML V2 remains **offline-only**.

---

## 7. Auth storage status

**Deferred.** Plan in [JWT_STORAGE_MIGRATION.md](JWT_STORAGE_MIGRATION.md).

---

## 8. Rate-limit status

Documented PostgreSQL semantics in [RATE_LIMITING.md](RATE_LIMITING.md). Not distributed-safe across regions.

---

## 9. Health / readiness

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness — always 200 if process up |
| `GET /ready` | Readiness — 503 if DB unreachable |

---

## 10. Tool HTTP semantics

| Decision | HTTP |
|----------|------|
| BLOCK | **403** + JSON body |
| REQUIRE_APPROVAL | 200 |
| ALLOW | 200 |

---

## 11. Documentation cleanup

Updated test counts with audit date context. Added verification docs listed in §1.

---

## 12. Git / release state

- **HEAD:** `0bb2659` — does not include remediation or LLM/ML V2 modules
- **Working tree:** contains remediation + experimental modules
- See [RELEASE_CONTENTS.md](RELEASE_CONTENTS.md)

**Recommendation:** Single commit tagging remediation before claiming freeze on a SHA.

---

## 13. Remaining risks

- Attack lab not re-run against live stack after assertion tightening
- JWT in localStorage (XSS)
- Partial BOLA scope
- Synthetic ML
- Mock LLM default
- Uncommitted release state

---

**PRODUCTION-ORIENTED PROTOTYPE** — not production-ready.
