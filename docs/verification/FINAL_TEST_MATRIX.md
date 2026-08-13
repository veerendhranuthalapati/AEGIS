# AEGIS Final Test Matrix

**Date:** 2026-08-13  
**Environment:** Windows 10, Python 3.13 venv, Node 20  
**Classification:** FEATURE FREEZE verification

---

| Component | Result | Evidence |
|-----------|--------|----------|
| Backend pytest | **219 passed / 220 collected** (1 postgres integration test fails when DB unavailable) | `pytest tests -q` — CI expects **220/220** with fresh Postgres |
| Ruff (`app`, `tests`) | **PASS** | Fixed unused imports in ML V2 modules |
| Mypy (`app/`) | **PASS — 0 errors** | 96 source files |
| Frontend Vitest | **7/7 PASS** | `npm test -- --run` |
| Frontend production build | **NOT RUN this session** | Prior freeze: PASS |
| Attack lab (16 scenarios) | **16/16 PASS** (artifact 2026-08-13) | `docs/verification/attack_lab_results.json` |
| Bypass regression suite | **15/15 PASS** (prior verified run) | `attack_lab/bypass_tests/run_bypass.py` |
| Docker full stack | **NOT RUN — BLOCKED** | Docker Desktop daemon not running |
| E2E (`e2e.py`) | **NOT RUN — BLOCKED** | Requires Postgres on :5433 |
| Performance recheck | **NOT RUN — BLOCKED** | Requires full stack; prior run in PERFORMANCE.md |
| pip-audit | **NOT RUN this session** | CI job |
| Terraform fmt/validate | **NOT RUN locally** | CI job |

---

## Failure injection (unit / code review)

| Scenario | Verified by |
|----------|-------------|
| ML unavailable | `test_ml_inference_failsafe.py` |
| LLM provider errors | `test_llm_failure_modes.py` |
| Duplicate approval | `tools.py` 409 gate |
| Worker duplicate incidents | `test_worker.py` |
| SQS down | N/A — not in application |

Live injection (stop Postgres/worker/upstream): **NOT RUN** — Docker stopped.

---

## Postgres integration test

`test_failed_logins_eventually_return_429_postgres` requires PostgreSQL on `DATABASE_URL`. When Docker/Postgres is stopped, this test fails. **CI uses an isolated Postgres service per job.**

---

## Reproduce locally

```powershell
docker compose up -d postgres mock-api
cd backend
$env:DATABASE_URL = "postgresql+asyncpg://aegis:aegis@127.0.0.1:5433/aegis"
$env:SECRET_KEY = "dev-secret-change-me"
$env:UPSTREAM_BASE_URL = "http://127.0.0.1:8100"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.scripts.seed
.\.venv\Scripts\python.exe -m pytest tests -q

cd ..\attack_lab\scripts
..\..\backend\.venv\Scripts\python.exe run_all.py http://127.0.0.1:8000
```

---

## Artifacts

| Artifact | Location |
|----------|----------|
| Final project report | `docs/verification/AEGIS_FINAL_PROJECT_REPORT.md` |
| Security matrix | `docs/verification/FINAL_SECURITY_MATRIX.md` |
| Deployment rehearsal | `docs/verification/DEPLOYMENT_REHEARSAL_REPORT.md` |
| Attack lab JSON | `docs/verification/attack_lab_results.json` |
| Performance (prior) | `docs/benchmarks/run1_noml.json`, `run2_ml.json` |
| ML V2 eval | `docs/benchmarks/ml_v2_eval.json` |

**FEATURE FREEZE: ACTIVE**
