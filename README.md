# AEGIS

**AI-Powered API & LLM Security Gateway**

**Classification:** Production-oriented prototype — **not production-ready**, **not AWS-deployed**  
**FEATURE FREEZE:** ACTIVE (2026-08-13)

---

## What

AEGIS is a security gateway that sits in front of upstream APIs and LLM endpoints. It inspects every request through layered detection and returns ALLOW, WARN, REQUIRE_REVIEW, BLOCK, or REQUIRE_APPROVAL before traffic reaches your application.

## Why

Modern applications expose REST APIs, LLM chat endpoints, and AI-agent tool calls — attack surfaces that traditional WAFs rarely inspect with full context. AEGIS demonstrates unified API security, LLM prompt controls, behavioral analytics, ML scoring, policy enforcement, and SOC visibility in one system.

## Why is it different?

One gateway covers **REST APIs, LLM prompts, and agent tool calls** with shared risk/policy, human approval for high-impact actions, and SOC visibility — not a separate WAF + ad-hoc LLM filter.

## How did you test it?

220 backend tests, 7 frontend tests, **16/16 attack lab** (strict), **15/15 bypass regressions**, adversarial LLM suites, Docker/CI gates, and controlled ML V2 **offline** evaluation — all documented with explicit **MOCK/SYNTHETIC/NOT DEPLOYED** labels.

**Live verification (2026-08-13):** **225 collected**, **224 passed**, **1 skipped** with live PostgreSQL — see [FINAL_LIVE_SECURITY_VERIFICATION.md](docs/verification/FINAL_LIVE_SECURITY_VERIFICATION.md).

## How

Layered, synchronous inspection pipeline:

```
Rules → Behavioral detection → ML → LLM security → Risk → Policy → Decision → Upstream
```

Async path (does not gate enforcement): security events → correlation worker → incidents → dashboard.

| Layer | Implementation |
|-------|----------------|
| Rules | SQLi, SSRF, path traversal, cmd injection, BOLA (modeled routes) |
| Behavioral | Rate, enumeration, auth-failure signals from PostgreSQL |
| ML | Isolation Forest + Random Forest (**synthetic training data**; V2 eval: [ML_V2_EVALUATION.md](docs/ML_V2_EVALUATION.md)) |
| LLM | Prompt injection heuristics; output redaction |
| Policy | YAML policy engine + risk aggregation |
| Agent | Tool registry, subject scope, approval workflow |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for diagrams (LOCAL vs CLOUD-DESIGNED).

## Demo

| Asset | Count / status |
|-------|----------------|
| Attack scenarios | **16/16 PASS** ([attack lab](docs/ATTACK_LAB.md)) |
| Encoding bypass tests | **15/15 PASS** |
| Backend tests | **225 collected**, **224 pass** + 1 skipped (live DB, 2026-08-13) |
| Frontend tests | **7/7 PASS** |
| SOC UI | Dashboard, incidents, approvals, ML, audit |
| Approval workflow | REQUIRE_APPROVAL → admin approve → execute |
| Incident correlation | Worker + MITRE-tagged incidents |

5-minute walkthrough: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)

## Limitations (not hidden)

| Area | Reality |
|------|---------|
| ML | **Synthetic dataset** — metrics show pipeline behavior, not real-world accuracy |
| LLM | **Mock provider VERIFIED** — real provider **IMPLEMENTED, NOT LIVE VERIFIED**; see [REAL_LLM_INTEGRATION.md](docs/REAL_LLM_INTEGRATION.md) |
| Cloud | **Terraform defined — AWS not deployed** |
| Detection | **Heuristic** — regex + normalization; encoding evasion is an ongoing concern |
| Performance | Live Docker benchmark: ~26 ms p50 serial overhead (50 req); prior ~215 ms (100 req dev) — **not production capacity** |
| Scope | Demonstrated against **16 controlled scenarios**, not all attacks |

Full honesty: [docs/LIMITATIONS.md](docs/LIMITATIONS.md)

---

## Architecture (summary)

```
Client → [WAF/ALB — cloud designed] → AEGIS Gateway → Upstream (mock in dev)
              ↓
         PostgreSQL ← Worker → Incidents → React SOC UI
```

## Quick start (Windows)

```powershell
cd aegis
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
$env:DATABASE_URL = "postgresql+asyncpg://aegis:aegis@127.0.0.1:5433/aegis"
$env:SECRET_KEY = "dev-secret-change-me"
$env:UPSTREAM_BASE_URL = "http://127.0.0.1:8100"
cd ..
docker compose up -d postgres mock-api
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.scripts.seed

# Terminal 1 — backend (in-process worker enabled by default)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — frontend
cd ..\frontend
npm install
npm run dev
# http://127.0.0.1:5173 — admin / Admin@1234

# Attack lab (requires backend + postgres + mock-api running)
cd ..\attack_lab\scripts
..\..\backend\.venv\Scripts\python.exe run_all.py http://127.0.0.1:8000
```

Copy [.env.example](.env.example) for configuration reference. Full setup: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Testing (2026-08-13 — v1.0.0-rc1)

| Check | Result |
|-------|--------|
| pytest | **224 pass**, **1 skipped**, **225 collected** (live Postgres) |
| Ruff / Mypy | PASS |
| Attack lab (strict) | **16/16** |
| Bypass suite | **15/15** |
| E2E | **PASS** |
| Frontend | **7/7** + build PASS |
| Docker build | **4/4 images** |
| Terraform validate/fmt | PASS |

Details: [FINAL_LIVE_SECURITY_VERIFICATION.md](docs/verification/FINAL_LIVE_SECURITY_VERIFICATION.md) · [RELEASE_NOTES.md](docs/verification/RELEASE_NOTES.md)

## Portfolio & interview

| Doc | Purpose |
|-----|---------|
| [RESUME.md](docs/RESUME.md) | Resume bullets |
| [INTERVIEW_GUIDE.md](docs/INTERVIEW_GUIDE.md) | 44 prepared Q&A |
| [DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) | Live demo steps |
| [PROJECT_STORY.md](docs/PROJECT_STORY.md) | Engineering narrative |
| [PROJECT_COMPLETION_REPORT.md](docs/verification/PROJECT_COMPLETION_REPORT.md) | Prior status |
| [AEGIS_FINAL_PROJECT_REPORT.md](docs/verification/AEGIS_FINAL_PROJECT_REPORT.md) | Final validation + freeze |

## Documentation

- [SECURITY.md](docs/SECURITY.md) · [THREAT_MODEL.md](docs/THREAT_MODEL.md)
- [ATTACK_LAB.md](docs/ATTACK_LAB.md) · [ML_EVALUATION.md](docs/ML_EVALUATION.md) · [ML_V2_EVALUATION.md](docs/ML_V2_EVALUATION.md)
- [PERFORMANCE.md](docs/PERFORMANCE.md) · [AWS_DEPLOYMENT.md](docs/AWS_DEPLOYMENT.md)
- [REAL_LLM_INTEGRATION.md](docs/REAL_LLM_INTEGRATION.md)
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) · [DEVELOPMENT.md](docs/DEVELOPMENT.md)

## License

MIT — see [LICENSE](LICENSE).
