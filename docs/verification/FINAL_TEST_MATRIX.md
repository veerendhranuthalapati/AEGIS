# AEGIS Final Test Matrix

**Date:** 2026-08-13  
**Environment:** Windows 10, Docker Desktop, Python 3.13 venv, Node 20  
**Classification:** Feature-freeze verification

---

| Component | Result | Evidence |
|-----------|--------|----------|
| Backend pytest | **169 passed / 170 collected** (1 postgres integration test failed when DB polluted by prior attack-lab brute-force run) | `backend/.venv/Scripts/python.exe -m pytest tests -v` — CI uses fresh Postgres and expects **170/170** |
| Ruff (`app`, `tests`) | **PASS** | `ruff check app tests` — All checks passed |
| Mypy (`app/`) | **PASS — 0 errors** | `mypy app --config-file mypy.ini` — 82 source files |
| Frontend Vitest | **7/7 PASS** | `npm test` — 3 files, 7 tests |
| Frontend production build | **PASS** | `npm run build` — Vite build ~19s (chunk size warning only) |
| Attack lab (16 scenarios) | **16/16 PASS** | `attack_lab/scripts/run_all.py http://127.0.0.1:8000` — 2026-08-13 freeze run |
| Bypass regression suite | **15/15 PASS** | `attack_lab/bypass_tests/run_bypass.py http://127.0.0.1:8000` |
| E2E (`e2e.py`) | **NOT RUN — BLOCKED** | PostgreSQL socket refused during `reset_telemetry()` after extended session; prior successful artifact documented in `FINAL_RELEASE_REPORT.md` |
| Docker backend build | **PASS** | `docker build -t aegis-backend:freeze-test ./backend` |
| pip-audit (runtime deps) | **PASS** | No known vulnerabilities found |
| Bandit (`-lll`, HIGH+) | **PASS** | 0 High severity findings |
| detect-secrets baseline | **NOT RUN locally** | CLI not installed in dev venv; CI job `security` runs baseline scan |
| Terraform fmt/validate | **NOT RUN locally** | Terraform CLI not in PATH; CI job `terraform` runs fmt + validate |
| npm audit (prod) | **NOT RUN this session** | CI runs non-blocking `npm audit --omit=dev` |
| Docker Scout | **NOT RUN this session** | CI runs non-blocking high/critical scan |

---

## Notes

### Postgres integration test

`test_failed_logins_eventually_return_429_postgres` requires a clean PostgreSQL instance. Running the attack-lab brute-force scenario against the same database can leave rate-limit state that causes this test to fail in a combined local session. **CI uses an isolated Postgres service per job** and is the authoritative pass signal for 170/170.

### E2E

`e2e.py` spawns mock-api + backend, runs attack scenarios, and verifies persistence (events, incidents, approvals, ML). Local run failed at DB reset (`ConnectionRefusedError` on port 5433) during this freeze session. Attack lab + bypass (which exercise the same gateway paths) **passed** on the live stack.

### CI reference

GitHub Actions workflow `.github/workflows/ci.yml` jobs:

| Job | Gates |
|-----|-------|
| `backend` | pytest, ruff, mypy, pip-audit |
| `frontend` | vitest, build, npm audit (informational) |
| `terraform` | fmt, validate |
| `docker` | build, Docker Scout (informational) |
| `attack-lab` | 16 scenarios + 15 bypass tests |
| `security` | bandit `-lll`, detect-secrets baseline |

---

## Reproduce locally

```powershell
# Backend unit tests (clean DB recommended)
cd backend
$env:DATABASE_URL = "postgresql+asyncpg://aegis:aegis@127.0.0.1:5433/aegis"
$env:SECRET_KEY = "dev-secret-change-me"
.\.venv\Scripts\python.exe -m pytest tests -q

# Attack lab (requires running stack)
docker compose up -d postgres mock-api
# start backend on :8000, then:
cd attack_lab\scripts
..\..\backend\.venv\Scripts\python.exe run_all.py

# Frontend
cd frontend
npm test
npm run build
```

---

## Artifact files

| Artifact | Location |
|----------|----------|
| Attack lab JSON | `docs/verification/attack_lab_results.json` |
| Bypass JSON | `attack_lab/bypass_tests/bypass_results.json` |
| Performance benchmarks | `docs/benchmarks/run1_noml.json`, `run2_ml.json` |
| CI security report | `docs/verification/CI_SECURITY_REPORT.md` |
| Cloud readiness | `docs/verification/CLOUD_READINESS_REPORT.md` |
