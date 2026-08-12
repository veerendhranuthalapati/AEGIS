# AEGIS

**AI-Powered API & LLM Security Gateway**

**Classification:** Production-oriented prototype (not production-ready)

---

## Problem

Modern applications expose REST APIs, LLMs, and AI agents that introduce new attack surfaces: injection, broken object-level authorization (BOLA), SSRF, prompt manipulation, unauthorized tool use, and sensitive data leakage. Traditional WAFs and API gateways often lack LLM-aware inspection, behavioral context, and policy-driven response controls in one place.

## Solution

AEGIS sits in front of upstream APIs and LLM endpoints and provides:

- **API security** — deterministic rules for SQLi, SSRF, path traversal, command injection, BOLA
- **Behavioral detection** — request-rate and enumeration signals
- **ML anomaly detection** — Isolation Forest + Random Forest on behavioral features (**synthetic training data**)
- **LLM security** — prompt injection / jailbreak heuristics; output redaction
- **AI agent / tool authorization** — registry, risk scoring, approval workflows
- **Risk scoring & policy enforcement** — aggregated decisions: ALLOW, WARN, REQUIRE_REVIEW, BLOCK
- **Incident correlation** — async worker groups related security events
- **Response controls** — block, review, redact, rate limit, require approval
- **SOC dashboard** — React UI over the control-plane API

## Architecture

```
                    ┌─────────────────────────────────────────┐
  Clients / Bots    │              AEGIS Gateway               │
  ───────────────►  │  Auth → Rules → Behavior → ML → LLM     │
                    │         ↓ Risk → Policy → Decision       │
                    └───────────┬──────────────┬──────────────┘
                                │              │
                     block/review│              │ allow + forward
                                │              ▼
                                │     ┌─────────────────┐
                                │     │  Mock / Upstream │
                                │     │  API + LLM echo  │
                                │     └─────────────────┘
                                ▼
                    ┌─────────────────────────────────────────┐
                    │ PostgreSQL — telemetry, events,         │
                    │ incidents, policies, approvals, ML meta   │
                    └─────────────────────────────────────────┘
                                ▲
                                │ correlate
                    ┌───────────┴──────────────┐
                    │   Correlation worker      │
                    └──────────────────────────┘

  Operators ──► React SOC UI ──► Control-plane REST API
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for component detail.

## Technology

| Layer | Stack |
|-------|--------|
| Backend | FastAPI, Python 3.13 |
| Database | PostgreSQL |
| ML | scikit-learn — Isolation Forest + Random Forest |
| Frontend | React, TypeScript, Vite, Tailwind |
| Infrastructure | Docker Compose; Terraform/AWS design (**defined, not deployed**) |

## Security demonstration

Examples verified via attack lab and gateway tests (mock upstream only):

| Scenario | Typical decision |
|----------|------------------|
| BOLA (cross-subject) | **BLOCK** |
| SQL injection (incl. encoded variants) | **BLOCK** |
| SSRF | **BLOCK** |
| Prompt injection | **REQUIRE_REVIEW** |
| Unauthorized tool | **BLOCK** |
| High-value payment | **REQUIRE_APPROVAL** |
| Admin approval flow | **EXECUTE** after approve |

Run: `attack_lab/scripts/run_all.py` and `attack_lab/bypass_tests/run_bypass.py`.

## Testing

Verified on 2026-08-13 (post plus-encoded SQLi fix):

| Check | Result |
|-------|--------|
| Backend pytest | **169 passed** (170 with optional Postgres integration test when DB available) |
| Ruff | **PASS** |
| Mypy (`app/`) | **0 errors** |
| Frontend tests | **7/7 PASS** |
| Frontend build | **PASS** |
| Attack lab | **16/16 PASS** |
| Bypass suite | **15/15 PASS** |
| E2E | See [docs/verification/FINAL_RELEASE_REPORT.md](docs/verification/FINAL_RELEASE_REPORT.md) |

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest tests -q
cd ..; backend\.venv\Scripts\python.exe e2e.py
cd attack_lab\scripts; ..\..\backend\.venv\Scripts\python.exe run_all.py
cd frontend; npm test; npm run build
```

## Limitations

- **ML dataset is synthetic** — metrics demonstrate pipeline behavior, not production detection quality
- **LLM upstream is mock/echo** — no live provider integration in default stack
- **AWS is not deployed** — Terraform modules exist for design review only
- **Performance** — measured gateway overhead documented in [docs/PERFORMANCE.md](docs/PERFORMANCE.md)
- **Heuristic detection** — encoding evasions require ongoing normalization; not a substitute for parameterized queries and app-layer controls
- **BOLA coverage** — limited to known ownership semantics on selected routes

This honesty is intentional: AEGIS is a **production-oriented prototype** suitable for portfolio demonstration and further hardening, not a certified production WAF replacement.

## Quick start (Windows)

```powershell
cd aegis
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
$env:DATABASE_URL = "postgresql+asyncpg://aegis:aegis@127.0.0.1:5433/aegis"
$env:SECRET_KEY = "dev-secret-change-me"
$env:UPSTREAM_BASE_URL = "http://127.0.0.1:8100"
.\.venv\Scripts\python.exe -m alembic upgrade head

cd ..
docker compose up -d postgres mock-api
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# separate terminal: .\.venv\Scripts\python.exe -m app.worker.main

cd ..\frontend
npm install
npm run dev
# http://127.0.0.1:5173 — login: admin / Admin@1234
```

Copy [.env.example](.env.example) for local configuration.

## Seed users (development only)

| User | Password | Role |
|------|----------|------|
| admin | Admin@1234 | admin |
| operator | Operator@1234 | operator |
| alice | Alice@1234 | user |
| bob | Bob@1234 | user |

## Documentation

- [SECURITY.md](docs/SECURITY.md) · [THREAT_MODEL.md](docs/THREAT_MODEL.md)
- [ATTACK_LAB.md](docs/ATTACK_LAB.md) · [ML_EVALUATION.md](docs/ML_EVALUATION.md)
- [CLOUD_SECURITY.md](docs/CLOUD_SECURITY.md) · [DEPLOYMENT.md](docs/DEPLOYMENT.md)
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) · [DEVELOPMENT.md](docs/DEVELOPMENT.md)

## License

MIT — see [LICENSE](LICENSE).
