# CI & Security Pipeline Report

**Date:** 2026-08-13  
**Repository:** AEGIS  
**Workflow:** `.github/workflows/ci.yml`

---

## CI architecture

```
push / pull_request
        │
        ├── backend ──────── Ruff, mypy, alembic, pytest, pip-audit
        ├── frontend ─────── npm test, build, npm audit (prod, informational)
        ├── terraform ──── fmt, validate (no AWS, no apply)
        ├── docker ─────── image build, Docker Scout (informational)
        ├── attack-lab ─── needs backend; postgres + mock-api + seed + run_all + bypass
        └── security ───── Bandit (HIGH+), detect-secrets baseline
```

**Permissions:** `contents: read` at workflow level (least privilege).  
**Secrets:** CI uses ephemeral env vars (`CI_SECRET_KEY`, `CI_DATABASE_URL`) — not GitHub Secrets, not logged intentionally. No credentials in Docker build args.

**Third-party actions:** pinned to major versions (`@v4`, `@v5`, `@v3`).

---

## Blocking vs non-blocking checks

| Job / step | Blocks merge? | Notes |
|------------|---------------|-------|
| Ruff | **Yes** | `backend` job |
| Mypy | **Yes** | `app/` only |
| Pytest | **Yes** | Includes Postgres integration when service available |
| pip-audit | **Yes** | Runtime `requirements.txt` only |
| Frontend test + build | **Yes** | |
| npm audit (prod) | No | `continue-on-error`; dev toolchain may report moderate issues |
| Terraform fmt/validate | **Yes** | Static only; not deployed |
| Docker build | **Yes** | |
| Docker Scout | No | High/critical report; does not fail CI |
| Attack lab (16 scenarios) | **Yes** | Fails on any scenario FAIL |
| Bypass suite (15 cases) | **Yes** | Part of attack-lab job |
| Bandit `-lll` | **Yes** | HIGH severity and above in `app/` |
| detect-secrets baseline | **Yes** | Fails on new secrets vs baseline |

---

## Attack lab in CI

1. PostgreSQL 16 service container (GitHub Actions)
2. `alembic upgrade head` + `python -m app.scripts.seed` (demo users/policies)
3. Mock upstream on `:8100`, AEGIS gateway on `:8000`
4. `AEGIS_IN_PROCESS_WORKER=true` (correlation worker in-process)
5. `attack_lab/scripts/run_all.py` — **exit code must be 0**
6. `attack_lab/bypass_tests/run_bypass.py` — encoding/BOLA regression

No AWS, no external LLM, no production infrastructure.

See [ATTACK_LAB.md](../ATTACK_LAB.md).

---

## Security scanner behavior

### Bandit

- Scope: `backend/app`
- Threshold: `-lll` (HIGH and above)
- LOW findings in prior local runs are expected and acceptable at lower threshold

### detect-secrets

- Baseline: `.secrets.baseline` at repo root
- Excludes: `node_modules`, `.venv`, lockfiles, `dist/`
- CI fails if new secrets appear relative to baseline

### pip-audit

- Scope: `backend/requirements.txt` (runtime)
- Dev-only tools audited separately via `requirements-dev.txt` locally

### Docker Scout

- Runs after image build
- Informational in CI (`continue-on-error: true`)
- Local post-upgrade scan (2026-08-13): see Docker results below

---

## Local verification (this session)

| Check | Result |
|-------|--------|
| Phase 0: initial commit | **Missing** — repo had zero commits; addressed in this phase |
| SQLi unit tests | **PASS** (decode, rules, api_bypass) |
| Backend pytest | **PASS** (169 tests, excluding optional postgres-only when DB down) |
| Ruff | **PASS** |
| Mypy `app/` | **0 errors** |
| Bandit `-lll` | **PASS** (no HIGH in app/) |
| pip-audit runtime | **PASS** (after dependency upgrades) |
| Frontend test/build | **PASS** (7/7) |
| npm audit (all) | 7 issues — mostly **dev** (vitest/esbuild); prod `npm audit --omit=dev` used in CI |
| Docker build | **PASS** |
| Docker Scout | See below |
| E2E (`e2e.py`) | **NOT RUN** — requires stable local Docker Postgres port forwarding |
| Attack lab (local) | **NOT RUN** — same Docker instability this session; CI job is authoritative |

---

## Docker Scout results

### Before (prior gate, python:3.13-slim, older requirements)

| Severity | Count |
|----------|------:|
| Critical | 0 |
| High | 9 |
| Medium | 16 |
| Low | 35 |

### After (2026-08-13, upgraded Python deps in image, `aegis-backend:scan`)

Scout overview for rebuilt image (full scan):

| Severity | Count |
|----------|------:|
| Critical | 2 |
| High | 5 |
| Medium | 6 |
| Low | 29 |
| Unspecified | 5 |
| **Total** | **47** |

**Notable HIGH/CRITICAL packages (Debian base, not Python runtime):**

| Package | CVE examples | Runtime required? | Mitigation |
|---------|--------------|-------------------|------------|
| `perl` (Debian trixie) | CVE-2026-13221, CVE-2026-12087, CVE-2026-48959 | **No** — not invoked by AEGIS | Base image transitive; no fix version published yet |
| Python stack | Reduced via `fastapi`, `starlette`, `PyJWT`, `orjson`, `python-multipart` upgrades | **Yes** | Upgraded in `requirements.txt` |

**Cannot safely claim zero container vulnerabilities** — Debian base packages may retain unfixed CVEs without a fixed upstream image.

---

## Dependency upgrades (runtime)

| Package | Before | After | Reason |
|---------|--------|-------|--------|
| fastapi | 0.115.6 | 0.140.13 | Pull secure Starlette |
| starlette | 0.41.3 | 1.6.0 | PYSEC Starlette advisories |
| PyJWT | 2.10.1 | 2.13.0 | PYSEC JWT advisories |
| python-multipart | 0.0.20 | 0.0.32 | PYSEC multipart advisories |
| orjson | 3.10.14 | 3.11.9 | PYSEC orjson advisory |

---

## Known limitations

- **npm dev toolchain:** vitest/vite/esbuild moderate advisories affect dev server only; production bundle build passes
- **Debian base CVEs:** require upstream `python:3.13-slim` refresh when available
- **E2E locally on Windows:** sensitive to Docker Desktop port forwarding; use CI or Linux host
- **detect-secrets baseline:** large; regenerate when adding intentional test fixtures
- **AWS / Terraform:** defined, not deployed; CI validates syntax only

---

## GitHub repository settings (manual, post-push)

Enable in repository settings (not configurable from files alone):

- Dependabot alerts (`.github/dependabot.yml` present)
- Secret scanning + push protection
- Code scanning (optional)

---

## Final classification

**PRODUCTION-ORIENTED PROTOTYPE** — CI enforces tests, types, attack scenarios, and runtime dependency audit; container and dev-toolchain findings remain documented honestly.
