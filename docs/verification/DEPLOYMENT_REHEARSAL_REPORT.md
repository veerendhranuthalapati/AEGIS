# Clean-Room Deployment Rehearsal

**Date:** 2026-08-13  
**Method:** Follow only `README.md`, `docs/DEVELOPMENT.md`, `docs/DEPLOYMENT.md` as a new developer would.

---

## Steps attempted

| Step | Document | Result |
|------|----------|--------|
| Clone / open repo | — | OK |
| Create venv + pip install | README | OK |
| Set env vars | README | OK (DATABASE_URL, SECRET_KEY, UPSTREAM_BASE_URL) |
| Start Postgres + mock-api | README | **BLOCKED** — Docker Desktop daemon not running on validation host |
| Alembic migrate | README | Documented |
| **Seed demo data** | **Missing in original README** | **FIXED** — added `python -m app.scripts.seed` |
| Start backend | README | Documented |
| Start frontend | README | Documented |
| Login admin | README | Requires seed |
| Attack lab | README | **Missing in original README** — **FIXED** — added attack lab step |
| Full Docker stack | DEPLOYMENT.md | **BLOCKED** — Docker unavailable |
| Docker seed on startup | DEPLOYMENT.md | **Missing** — **FIXED** in `docker-compose.yml` |

---

## Gaps found and fixed

| Gap | Fix |
|-----|-----|
| README omitted `app.scripts.seed` after migrate | Added to README + DEVELOPMENT.md |
| README started Docker after alembic (wrong order) | Reordered: Docker first, then migrate + seed |
| README did not mention attack lab | Added attack lab command |
| DEPLOYMENT.md did not mention seed in compose | Documented; compose command now runs seed |
| DEVELOPMENT.md had no first-time setup block | Added full bootstrap section |
| Docker backend + worker both ran in-process worker | Backend compose sets `AEGIS_IN_PROCESS_WORKER=false` |
| `/health` does not check Postgres | Documented in DEPLOYMENT.md (not a bug — liveness only) |

---

## Remaining notes (not bugs)

| Item | Note |
|------|------|
| Worker for local venv dev | Optional separate process; backend defaults to in-process worker |
| `LOGIN_RATE_LIMIT_PER_MIN` | Load tests need `500`; documented in PERFORMANCE.md |
| Frontend Docker port | `:3000` maps to nginx `:8080` (profile `frontend`) |
| `.env.example` | Reference only; README uses inline `$env:` for Windows |

---

## Reproduce when Docker is available

```powershell
$env:AEGIS_SECRET_KEY = "rehearsal-secret"
$env:AEGIS_POSTGRES_PASSWORD = "rehearsal-pg"
docker compose --profile frontend up -d --build
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:3000/
cd attack_lab\scripts
..\..\backend\.venv\Scripts\python.exe run_all.py http://127.0.0.1:8000
```

**Status:** Documentation corrected; live Docker rehearsal **BLOCKED** on validation host (Docker daemon stopped). CI and prior freeze run (2026-08-13) remain authoritative for stack verification.
