# Final Live Security Verification

**Date:** 2026-08-13  
**Host:** Windows 10, Docker Desktop 4.85.0 (Engine 29.6.2)  
**Classification:** **PRODUCTION-ORIENTED PROTOTYPE** (not production-ready)

---

## 1. Environment

| Item | Value |
|------|-------|
| OS | Windows 10.0.26200 |
| Docker Client | 29.6.2 |
| Docker Server | 29.6.2 (desktop-linux) |
| Python | 3.13.3 (backend `.venv`) |
| Node | 20 (frontend build) |
| Gateway | `http://127.0.0.1:8000` (Docker backend) |
| Frontend | `http://127.0.0.1:3000` (nginx profile) |
| Postgres | `127.0.0.1:5433` (compose volume, fresh `docker compose down -v`) |
| Mock upstream | `http://127.0.0.1:8100` |
| LLM provider | **mock** (default) |

---

## 2. Commands executed

```powershell
docker version
docker info
docker compose down -v
docker compose --profile frontend up -d --build

# Health / readiness
Invoke-WebRequest http://127.0.0.1:8000/health
Invoke-WebRequest http://127.0.0.1:8000/ready

# Attack lab (strict)
cd attack_lab\scripts
..\..\backend\.venv\Scripts\python.exe run_all.py

# Bypass suite
cd attack_lab\bypass_tests
..\..\backend\.venv\Scripts\python.exe run_bypass.py

# E2E (local uvicorn + compose Postgres; stops docker backend/mock first)
docker compose stop backend mock-api
backend\.venv\Scripts\python.exe e2e.py
docker compose start backend mock-api

# Rate limit (live Postgres)
cd backend
$env:DATABASE_URL="postgresql+asyncpg://aegis:aegis@127.0.0.1:5433/aegis"
.\.venv\Scripts\python.exe -m pytest tests/unit/test_login_rate_limit.py::test_failed_logins_eventually_return_429_postgres -v

# Live checks (auth, tools, approval, frontend proxy)
backend\.venv\Scripts\python.exe scripts\live_verification_checks.py

# Performance
backend\.venv\Scripts\python.exe scripts\loadtest.py --requests 50 --concurrency 10 --json docs\benchmarks\live_verification_2026-08-13.json

# Regression
pytest tests -q
ruff check app tests
mypy app
cd frontend && npm test -- --run && npm run build
terraform validate && terraform fmt -check -recursive

# Docker Scout
docker scout quickview aegis-backend:latest
docker scout quickview aegis-worker:latest
docker scout quickview aegis-frontend:latest
docker scout quickview aegis-mock-api:latest
```

---

## 3. Docker stack status

**Start:** `docker compose down -v` then `docker compose --profile frontend up -d --build`

| Service | Status | Notes |
|---------|--------|-------|
| postgres | **healthy** | Fresh volume, migrations + seed via backend |
| mock-api | **healthy** | Vulnerable test upstream |
| backend | **healthy** | `/health` 200, `/ready` 200 + `database: ok` |
| frontend | **healthy** | SPA + `/api` proxy |
| worker | **running (unhealthy)** | No HTTP healthcheck defined; process running |

**Readiness distinction verified:**

| Endpoint | Postgres up | Postgres stopped |
|----------|---------------|------------------|
| `GET /health` | 200 | **200** (liveness only) |
| `GET /ready` | 200 | **503** |

---

## 4. Test counts (final regression)

| Suite | Result |
|-------|--------|
| pytest | **225 collected**, **224 passed**, **1 skipped** (live Postgres) |
| Ruff | **PASS** |
| Mypy | **PASS** (96 source files) |
| Frontend Vitest | **7/7 PASS** |
| Frontend build | **PASS** |
| Terraform validate | **PASS** |
| Terraform fmt -check | **PASS** |

---

## 5. Attack lab (strict) — **16/16 PASS**

Evidence: [`attack_lab_results.json`](attack_lab_results.json)

| Scenario | Expected | Actual | Status |
|----------|----------|--------|--------|
| brute_force_login | 10+×401 then 429 | 10×401 then 429 | PASS |
| sql_injection | 403 BLOCK API-006 | 403 BLOCK rules API-006 (+API-013) | PASS |
| path_traversal | 403 BLOCK API-005 | 403 BLOCK rules API-005 (+API-013) | PASS |
| ssrf_attempt | 403 BLOCK API-008 | 403 BLOCK rules API-008 (+API-013) | PASS |
| command_injection | 403 BLOCK API-007 | 403 BLOCK rules API-007 (+API-013) | PASS |
| admin_probe | 403 BLOCK API-017 | 403 BLOCK rules API-017 (+API-013) | PASS |
| bola_attempt | 403 BLOCK API-016 | 403 BLOCK rules API-016 (+API-013) | PASS |
| direct_prompt_injection | 202 REQUIRE_REVIEW LLM-001 | 202 REQUIRE_REVIEW LLM-001 (+API-013) | PASS |
| jailbreak_attempt | 202 REQUIRE_REVIEW LLM-003 | 202 REQUIRE_REVIEW LLM-003 (+API-013) | PASS |
| system_prompt_extraction | 202 REQUIRE_REVIEW LLM-002 | 202 REQUIRE_REVIEW LLM-002 (+API-013) | PASS |
| sensitive_extraction_llm | 202 REQUIRE_REVIEW LLM-005 | 202 REQUIRE_REVIEW LLM-005 (+API-013) | PASS |
| tool_manipulation_prompt | 202 REQUIRE_REVIEW LLM-006 | 202 REQUIRE_REVIEW LLM-006 (+API-013) | PASS |
| malicious_tool_call | 403 BLOCK | 403 BLOCK | PASS |
| cross_subject_tool_call | 403 BLOCK | 403 BLOCK | PASS |
| large_payment_approval | 200 REQUIRE_APPROVAL | 200 REQUIRE_APPROVAL | PASS |
| data_exfiltration | 202 REQUIRE_REVIEW LLM-005 | 202 REQUIRE_REVIEW LLM-005 (+API-013) | PASS |

**Note:** API-013 (rate/abuse) co-triggers after sustained attack traffic — primary rule IDs still match expectations.

---

## 6. Bypass suite — **15/15 PASS**

Evidence: [`bypass_results.json`](bypass_results.json)

All encoding variants (URL, double, plus, mixed case), SSRF decimal IP, cmd injection, BOLA cross-subject BLOCK + own-resource ALLOW verified.

---

## 7. E2E — **PASS** (local stack + compose Postgres)

Evidence: [`e2e_live_results.json`](e2e_live_results.json)

| Category | Result |
|----------|--------|
| Legitimate API/LLM/health | 200 |
| BOLA, SQLi, SSRF, traversal, cmd inj, admin | 403 BLOCK |
| Prompt injection, jailbreak, extraction | 202 REQUIRE_REVIEW |
| Unauthorized tools | 403 BLOCK |
| Events + incidents persisted | Yes (MITRE tags present) |
| ML train | 200 (`train_split_only` metadata) |
| Payment approval flow | REQUIRE_APPROVAL → approve → success |
| Embedded attack lab | exit_code **0**, 16/16 PASS |

**E2E mode:** Spawns local uvicorn (in-process worker) against compose Postgres; not the Docker backend container.

---

## 8. Rate limiting — **PASS**

| Method | Result |
|--------|--------|
| pytest `test_failed_logins_eventually_return_429_postgres` | **PASS** (live Postgres) |
| Attack lab `brute_force_login` | 10×401 then 429 |
| Direct HTTP | Confirmed via attack lab isolated IP |

---

## 9. Authorization (live) — **PASS**

Evidence: [`live_verification_checks.json`](live_verification_checks.json)

| Check | Result |
|-------|--------|
| Alice → own user resource | 200 ALLOW |
| Alice → Bob user resource | 403 BLOCK |
| Admin → admin endpoint | 200 |
| Operator payment | REQUIRE_APPROVAL |

---

## 10. Tool security + approval (live) — **PASS**

| Check | Result |
|-------|--------|
| Unauthorized delete_user | 403 BLOCK |
| Cross-subject read_user_profile | 403 BLOCK |
| execute_payment (operator) | 200 REQUIRE_APPROVAL |
| First approve | 200, execution success |
| Second approve | **409** |

---

## 11. LLM (live, mock provider)

| Test | Result |
|------|--------|
| Prompt injection | 202 REQUIRE_REVIEW |
| Legitimate prompt | 200 (mock echo) |
| **Real LLM provider live test** | **NOT VERIFIED** (no credentials configured) |

---

## 12. Frontend (live HTTP)

All routes return 200 via nginx (`/`, `/dashboard`, `/threats`, `/incidents`, `/api-security`, `/llm-security`, `/agents`, `/policies`, `/users`, `/ml`, `/audit`).

`/api/analytics/overview` proxied successfully with admin token — **not mock statistics** (live backend data).

**Browser visual QA:** **NOT VERIFIED** (HTTP-only; no Playwright/Cypress run).

---

## 13. Docker build — **PASS**

Images built during `docker compose up --build`:

- `aegis-backend:latest`
- `aegis-worker:latest`
- `aegis-mock-api:latest`
- `aegis-frontend:latest`

Stack restarted and re-verified after E2E port conflict.

---

## 14. Docker security scan (Docker Scout, 2026-08-13)

| Image | CVE summary | Policy |
|-------|-------------|--------|
| aegis-backend | 2C 5H 6M 29L | **4/7** (fixable 3H, copyleft, no attestations) |
| aegis-worker | 2C 5H 6M 29L | **4/7** |
| aegis-frontend | 6C 27H 47M 16L | **4/7** (fixable 4C 23H) |
| aegis-mock-api | 2C 2H 9M 30L | **4/7** (runs as root in image) |

Non-root runtime enforced for backend/worker/frontend via Dockerfile USER; mock-api image runs as root.

---

## 15. Performance (live Docker stack, 50 requests)

Evidence: [`../benchmarks/live_verification_2026-08-13.json`](../benchmarks/live_verification_2026-08-13.json)

| Tier | p50 (ms) | p95 (ms) | p99 (ms) | req/s |
|------|----------|----------|----------|-------|
| upstream | 4.25 | 5.35 | 6.74 | 64.15 |
| aegis | 29.94 | 35.41 | 42.49 | 21.36 |
| aegis_ml | 31.39 | 37.55 | 38.74 | 21.55 |
| aegis_llm | 28.84 | 31.47 | 32.10 | 21.68 |
| aegis_concurrent (10 workers) | 185.61 | 513.66 | 525.05 | 41.20 |

**Gateway overhead (serial aegis vs upstream):** ~26 ms p50 on this run (lower than prior ~215 ms benchmark due to warm DB + fewer requests). Prior benchmarks remain in `docs/benchmarks/run1_noml.json`.

---

## 16. Remaining limitations

| Item | Status |
|------|--------|
| Real LLM live verification | NOT VERIFIED |
| Browser E2E (visual) | NOT VERIFIED |
| AWS / Terraform apply | NOT DEPLOYED |
| JWT in localStorage | Deferred (documented) |
| Distributed rate limiting | PostgreSQL-only |
| Worker container healthcheck | Missing |
| Git release tag | Uncommitted working tree |
| ML V2 online | Offline evaluation only |

---

## 17. Summary

**Live verification PASSED** for all runnable checks on 2026-08-13:

- Docker stack (postgres, mock-api, backend, worker, frontend)
- Strict attack lab **16/16**
- Bypass suite **15/15**
- E2E script with persistence + embedded attack lab
- PostgreSQL rate-limit integration test
- Authorization, tool 403, approval 409
- Mock LLM security paths
- Frontend HTTP routes + API proxy
- Docker builds + Scout scans
- Full static regression (pytest, ruff, mypy, frontend, terraform)

**NOT VERIFIED:** real LLM provider, browser visual E2E, AWS deployment.

**Classification unchanged:** **PRODUCTION-ORIENTED PROTOTYPE**
