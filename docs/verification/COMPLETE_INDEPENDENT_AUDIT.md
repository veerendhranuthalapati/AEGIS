# AEGIS — Complete Independent Forensic Audit

**Auditor:** Independent agent (does not trust prior reports)  
**Date:** 2026-08-13  
**Git HEAD:** `0bb2659` (master) — **large uncommitted working tree**  
**Audit method:** Inspect → reproduce (where possible) → compare claims vs evidence

---

## 1. Executive summary

AEGIS is a **real, runnable FastAPI security gateway** with a React SOC UI, PostgreSQL persistence, deterministic API/LLM heuristics, synthetic ML, mock LLM default, optional real LLM code (uncommitted), async incident correlation, and Terraform **design** (not deployed).

**What is genuinely strong:** Synchronous gateway pipeline is implemented and unit-tested; JWT auth with DB-backed revocation; tool authorization with approval workflow and duplicate-decide protection (409); risk engine excludes ML weight when unavailable; 220 backend tests exist; attack-lab harness exists.

**What prior reports overstate or cannot verify here:**
- **Feature freeze** is declared on a **dirty worktree** (~40+ modified/untracked files including LLM, ML V2, verification docs) — not a clean release artifact.
- **16/16 attack lab** — **NOT REPRODUCED** this audit (Docker daemon unavailable); stored JSON artifact from prior run; **pass criteria are permissive** (see §25).
- **220/220 tests** — **219 pass** locally without PostgreSQL; 1 integration test requires live DB.
- **Terraform validate** — **FAILED** until unused `vpc_id` variable removed from RDS module (**fixed** this audit, low-risk).
- **Production-ready / AWS deployed** — **FALSE**; correctly disclaimed in README.

**Final classification:** **PRODUCTION-ORIENTED PROTOTYPE** (see §36)

---

## 2. Repository inventory (Phase 0)

| Area | Path | Status |
|------|------|--------|
| Backend | `backend/app/` | **REAL** — FastAPI ~96 Python modules |
| Frontend | `frontend/src/` | **REAL** — React 18 + Vite + TypeScript |
| Attack lab | `attack_lab/` | **REAL** — 16 scenarios + bypass suite |
| Tests | `backend/tests/` | **REAL** — 220 collected |
| Docker | `docker-compose.yml`, Dockerfiles | **CONFIGURED** — build **NOT VERIFIED** (daemon down) |
| Terraform | `terraform/modules/*`, `environments/dev/` | **CONFIGURED** — validate **VERIFIED** after fix |
| CI | `.github/workflows/ci.yml` | **REAL** |
| ML artifacts | `models/`, `*.joblib` | **GITIGNORED** — not tracked |
| Docs | `docs/`, `docs/verification/` | Extensive; some stale counts (170 vs 220 tests) |

### Technology stack (from `requirements.txt`, `package.json`)

| Component | Version / choice |
|-----------|------------------|
| Python | 3.13 (CI + venv) |
| FastAPI | 0.140.13 |
| Starlette | 1.6.0 |
| PostgreSQL | 16 (Docker/CI) |
| asyncpg + SQLAlchemy 2.0 | async ORM |
| scikit-learn | 1.6.1 (ML) |
| PyJWT + bcrypt | Auth |
| httpx | Upstream + LLM client |
| React | 18.3.1 |
| Vitest | 2.1.8 |
| XGBoost | **NOT IMPLEMENTED** |
| boto3 / SQS / S3 app code | **NOT IMPLEMENTED** |

---

## 3. Git / release integrity (Phase 1)

### Committed (HEAD `0bb2659`)

3 commits total. Last commit: `chore: finalize AEGIS portfolio release`.

### Uncommitted (audit snapshot)

**Modified:** README, docker-compose, gateway, ML inference, risk engine, docs, etc.  
**Untracked:** Entire `backend/app/llm/`, ML V2 modules, adversarial tests, verification reports (`AEGIS_FINAL_PROJECT_REPORT.md`, this file), `ML_V2_EVALUATION.md`, `REAL_LLM_INTEGRATION.md`.

**Impact:** Claims about LLM provider abstraction and ML V2 are **not in the last git commit**. Feature freeze is **process-level only**, not a tagged release.

### `.gitignore` assessment

Correctly ignores: `.env`, `.venv`, `node_modules`, `*.joblib`, `.pytest_cache`, terraform state, local DB files.

### Secrets search

| Finding | Location | Type |
|---------|----------|------|
| AWS example key pattern | `test_redact.py` | Test fixture only |
| Test PEM snippet | `test_redact.py` | Test fixture only |
| Demo passwords in docs/seed | `Admin@1234`, etc. | **Dev-only** — documented |
| `CI_SECRET_KEY` | `.github/workflows/ci.yml` | Ephemeral CI label |

**No production secrets found in tracked source.**

---

## 4. Claims vs reality matrix (Phase 2)

| Claim | Evidence | Status |
|-------|----------|--------|
| 220 backend tests | `220 tests collected`; 219 pass without Postgres | **PARTIALLY VERIFIED** |
| 16/16 attack lab | JSON artifact 2026-08-13; **not re-run** this audit | **UNVERIFIED** (live) / **PARTIALLY VERIFIED** (artifact) |
| 15/15 bypass | Not executed this audit | **UNVERIFIED** |
| LLM security implemented | `security/llm/scanner.py`, gateway integration | **VERIFIED** (heuristic) |
| Real LLM provider | `app/llm/real.py` (uncommitted); default `mock` | **IMPLEMENTED, NOT VERIFIED** live |
| ML trained | V1 API `POST /api/ml/train` on **synthetic** data | **SYNTHETIC** |
| ML V2 evaluation | `evaluate_ml_v2.py` reproduced F1 ~0.66 | **SYNTHETIC / VERIFIED** (offline) |
| Incident correlation | Worker + tests | **VERIFIED** (unit) |
| Terraform valid | Failed → fixed `vpc_id`; `terraform validate` **Success** | **VERIFIED** (post-fix) |
| AWS deployed | No apply; docs say not deployed | **NOT IMPLEMENTED** |
| Feature freeze | Dirty worktree with major new code | **PARTIALLY FALSE** as release state |
| Production-oriented prototype | README + architecture | **VERIFIED** (label) |
| Production-ready | Explicitly denied in README | **FALSE** (correctly) |
| Distributed rate limiting | PostgreSQL fixed-window only | **NOT IMPLEMENTED** |
| SQS in app | Worker polls PostgreSQL | **NOT IMPLEMENTED** |
| Automated infra response | `ResponseExecutor(mode="mock")` | **MOCK** |

---

## 5. Architecture (Phase 3)

**Execution path (verified in code):**

`gateway.py` → `GatewayService.process()` → auth context → rules → behavior stats → ML → LLM scan → risk → policy → decision → forward/redact → persist events.

**Async path:** `SecurityEvent` → worker (`FOR UPDATE SKIP LOCKED`) → correlation → incidents.

**Trust boundaries:** Client, prompts, HTTP params, LLM output, tool args = **UNTRUSTED**. Policy/tool registry/approved ops = **TRUSTED AFTER VALIDATION**.

**Modularity:** Real separation of rules, risk, policy, agents — not merely cosmetic. **Caveat:** ~15 sequential DB round-trips per gateway request (performance bottleneck, documented).

**Dead/unused:** RDS module had unused `vpc_id` variable (removed in audit fix).

---

## 6. Authentication (Phase 4)

| Control | Implementation | Tested |
|---------|----------------|--------|
| Password hashing | bcrypt | **VERIFIED** — unit tests |
| JWT HS256 | `auth/jwt.py`, issuer enforced | **VERIFIED** |
| Algorithm enforcement | `algorithms=[settings.jwt_algorithm]` only | **VERIFIED** — wrong alg rejected |
| Token DB revocation | `ensure_token_valid` | **VERIFIED** |
| Account lockout | After N failures | **VERIFIED** |
| Login rate limit | PostgreSQL bucket `login:{ip}` | **VERIFIED** (SQLite + service tests); Postgres integration **FAILED** (no DB) |

**Gap:** JWT role/permissions in token payload; server reloads role from DB on API routes — good. Gateway `_resolve_actor` loads role — good.

**Frontend:** Tokens in **localStorage** via Zustand persist (`aegis-auth`) — **MEDIUM** XSS exposure.

---

## 7. Authorization (Phase 5)

Admin API routes use `require_permission()` — **verified** on users, policies, incidents, ML train, approvals, audit.

**Gateway:** Requires bearer except `_OPEN_PATHS` (`/public`, `/auth/`, etc.).

**Tool invoke** (`POST /api/tools/invoke`): Uses `CurrentUser` only; **`agents:invoke` checked inside `ToolSecurityEngine`** → returns `decision=BLOCK` in body (HTTP 200), not HTTP 403. Functionally protected but **easy to misread in API audits**.

**BOLA:** Post-forward ownership check on **modeled routes only** (`gateway/service.py`) — not universal IDOR protection.

---

## 8. Input normalization (Phase 6)

Decode pipeline in `security/api/decode.py` — unit tests for encoding layers (`test_decode_inspection`, `test_api_bypass`). **VERIFIED** at unit level; bypass suite **NOT RE-RUN** live.

---

## 9. API security (Phase 7)

Rules engine: SQLi, SSRF, traversal, cmd injection — **REAL**, heavily unit-tested (`test_rules.py` ~30 tests).

Attack lab scenarios use real payloads in `attacks.py` — design is sound; **evaluator weakness** (§25).

---

## 10. Rate limiting (Phase 8)

| Property | Value |
|----------|-------|
| Storage | PostgreSQL `RateLimitState` |
| Algorithm | Fixed window, atomic UPDATE |
| Login key | `login:{ip}` |
| Gateway key | Per auth/anon limits |
| Distributed | **NO** — single DB, process-local semantics |
| Forwarded IP | `resolve_client_ip` + dev trust headers |

**401 ≠ 429:** Brute-force test expects 401s then 429 — **verified** in attack-lab evaluator logic.

---

## 11. LLM security (Phase 9)

**What it is:** Deterministic regex/heuristic scanner (`security/llm/scanner.py`) + optional external analyzer (`LLM_ANALYZER_ENABLED=false` default) + output redaction.

**NOT:** A neural classifier or production LLM safety product.

**Decisions:** HIGH findings → typically REQUIRE_REVIEW (202); not always BLOCK.

**Mock provider default:** Echoes deterministic responses; tool calls simulated in `llm/mock.py`.

---

## 12. Real LLM provider (Phase 10)

| Item | Status |
|------|--------|
| Interface | `LLMProvider` in `llm/base.py` |
| Mock | **REAL**, default |
| Real (OpenAI-compatible) | **IMPLEMENTED** in `llm/real.py` (uncommitted) |
| Live test | `test_llm_real_provider.py` marked `real_llm` — **NOT RUN** (no API key) |
| Failure modes | **VERIFIED** — unit tests for 429, malformed JSON |

Label: **REAL PROVIDER: IMPLEMENTED BUT NOT VERIFIED** (live)

---

## 13. LLM output security (Phase 11)

`scan_output`, `redact_text` — **VERIFIED** unit + adversarial tests. Secrets sanitized in logging (`test_llm_secret_handling`).

---

## 14. Agent / tool security (Phase 12)

| Control | Status |
|---------|--------|
| Registry in DB | **REAL** |
| Role + `agents:invoke` | **REAL** (engine) |
| Cross-subject block | **REAL** |
| REQUIRE_APPROVAL | **REAL** |
| Duplicate approval | HTTP **409** if `status != pending` — **VERIFIED** (code) |
| LLM cannot self-approve | Human `decide_approval` + no self-approval | **REAL** |

**Gap:** No automated test for duplicate approval HTTP 409 (code inspection only).

---

## 15. Risk engine (Phase 13)

Weights sum with ML zeroed when `ml_available=False` — **VERIFIED** (`test_ml_inference_failsafe`, `engine.py`).

Malformed inputs clamped via `min(1.0, max(0.0, ...))` on scores — no NaN propagation observed.

---

## 16. Policy engine (Phase 14)

YAML policies evaluated in `policies/engine.py` — unit tests present. Fail-closed on hard BLOCK policies — **VERIFIED** in gateway integration.

---

## 17. ML audit (Phase 15)

| Aspect | V1 (online) | V2 (eval only) |
|--------|-------------|----------------|
| Data | `dataset.py` synthetic | `traffic_generator.py` controlled local |
| Labels | Direct row generation | Scenario-based |
| Split | Random 70/30 index | Temporal 60/20/20 + actor holdout |
| IF training | **Full dataset incl. test** | Train split only |
| Leakage features | Excluded online; in dataframe offline | Explicitly excluded |
| Online integration | **V1 only** via `/api/ml/train` | **NOT wired** to inference |
| Metrics | API after train | Reproduced: RF F1 ~0.66, FPR ~0.17% on synthetic test |

**ML credibility:** Pipeline is **real**; detection quality claims are **SYNTHETIC ONLY**.

---

## 18. Incident correlation (Phase 17)

Worker claims events with `SKIP LOCKED`; duplicate incident suppression tested — **VERIFIED** (unit).

---

## 19. Response engine (Phase 18)

`ResponseExecutor(mode="mock")` — actions persist DB records; **no real infra control**. Documented honestly in module docstring.

---

## 20. Database (Phase 19)

Alembic migrations present. Fresh setup requires `alembic upgrade head` + **`app.scripts.seed`** (documented after prior rehearsal fixes).

**Race protection:** Rate limit uses atomic SQL; approval status gate prevents double execute.

---

## 21. Frontend (Phase 20)

Pages call real APIs via `frontend/src/api/endpoints.ts` — **no fake incident data** found in source (grep for mock/fake/hardcoded stats: clean except UI placeholders).

Auth: localStorage tokens — see §6.

Tests: **7/7 PASS** — **VERIFIED** this audit.

---

## 22. Docker (Phase 22–23)

Compose defines postgres, mock-api, backend, worker, frontend (profile). Backend runs migrate + seed + uvicorn; `AEGIS_IN_PROCESS_WORKER=false` when worker container present.

**Build/run:** **NOT VERIFIED — DOCKER UNAVAILABLE** (daemon stopped during audit).

---

## 23. Terraform (Phase 24)

| Check | Result |
|-------|--------|
| RDS private | `publicly_accessible = false` — **VERIFIED** in module |
| IAM scoped | Named SQS/S3/secrets ARNs — **VERIFIED** |
| Wildcard admin | Not found in modules reviewed |
| `terraform validate` | **VERIFIED** after removing unused `vpc_id` |
| `terraform apply` | **NOT RUN** (by design) |

---

## 24. CI/CD (Phase 25)

| Job | Blocking? |
|-----|-----------|
| backend (pytest, ruff, mypy, pip-audit) | **YES** |
| frontend (test, build) | **YES** |
| terraform | **YES** |
| attack-lab | **YES** (needs backend job) |
| docker build | **YES** |
| docker scout | **NO** (`continue-on-error`) |
| npm audit | **NO** (`continue-on-error`) |
| security (bandit, detect-secrets) | **YES** |

**Note:** Backend CI job does **not** run `seed` — tests use migrations only; attack-lab job seeds separately.

---

## 25. Attack lab forensic audit (Phase 29)

### Pass criteria (`run_all.py::_evaluate`)

Passes if response text starts with `429`, `403`, `202` **OR** contains `BLOCK` **OR** `REQUIRE`.

**Does NOT verify:**
- Specific rule IDs (`SQLI_INDICATOR`, etc.) despite expected strings mentioning them
- Whether block was for the **intended** reason vs incidental policy
- Upstream errors vs security decisions

### Scenario assessment

| Scenario | Payload real? | Pass strictness | Audit verdict |
|----------|---------------|-----------------|---------------|
| brute_force_login | Yes | Checks 401 then 429 | **GENUINE PASS** criteria |
| sql_injection … cmd_injection | Yes | Any 403/BLOCK | **PERMISSIVE PASS** |
| LLM scenarios | Yes | 202 REQUIRE_REVIEW OK | **GENUINE PASS** if review triggered |
| tool scenarios | Yes | BLOCK/REQUIRE in JSON | **GENUINE PASS** |
| large_payment_approval | Yes | REQUIRE_APPROVAL | **GENUINE PASS** |

**Live execution this audit:** **NOT VERIFIED — ENVIRONMENT BLOCKED**

---

## 26. Security scanners (Phase 30)

| Tool | Result | Verified |
|------|--------|----------|
| Ruff | All checks passed | **YES** |
| Mypy | 0 errors, 96 files | **YES** |
| Bandit `-lll` | 0 High severity | **YES** |
| pip-audit | Not run this audit | **NOT VERIFIED** |
| detect-secrets | Not run locally | **NOT VERIFIED** |
| Docker scan | Not run | **NOT VERIFIED** |

---

## 27. Test quality (Phase 31)

**Valid:** Rules, decode, BOLA, JWT, tool security, LLM scanner adversarial suites, ML failsafe, correlation dedup.

**Weak / gaps:**
- Attack lab accepts broad HTTP outcomes
- Some adversarial tests use flexible rule-set matching (`any rule in set`)
- Postgres login rate test fails when DB absent (environment coupling)
- No integration test for duplicate approval 409
- Frontend tests cover layout/auth store only — not SOC pages against API

---

## 28. Complete security matrix (Phase 32)

| Domain | Attack/Check | Implemented | Tested | Result | Severity if fail |
|--------|--------------|-------------|--------|--------|------------------|
| API | SQLi | Yes | Unit + lab* | Pass* | — |
| API | SSRF | Yes | Unit + lab* | Pass* | — |
| API | Traversal | Yes | Unit + lab* | Pass* | — |
| API | Cmd injection | Yes | Unit + lab* | Pass* | — |
| API | BOLA | Partial routes | Unit + lab* | Pass* | MEDIUM (scope) |
| API | Rate limit | Yes | Unit + lab* | Pass* | — |
| Auth | JWT tampering | Yes | Unit | Pass | — |
| Auth | Token in localStorage | N/A | — | Risk | MEDIUM |
| LLM | Prompt injection | Heuristic | Unit + lab* | Pass* | — |
| LLM | Output leakage | Redaction | Unit | Pass | — |
| Agent | Unauthorized tool | Yes | Unit + lab* | Pass* | — |
| Agent | Cross-user tool | Yes | Unit + lab* | Pass* | — |
| Agent | Approval replay | 409 gate | Code only | Pass | LOW (test gap) |
| ML | Failure open | No | Unit | Pass | — |
| ML | Real-world accuracy | No | N/A | N/A | INFO |
| Cloud | IAM | Terraform | Validate | Pass | — |
| Cloud | RDS public | No | Static | Pass | — |
| Cloud | Deployed | No | N/A | N/A | — |
| DevOps | CI blocking | Yes | Inspect | Pass | — |

*Lab = **NOT RE-RUN** this audit; unit tests **VERIFIED**.

---

## 29. Scorecard (Phase 33)

| Area | Score | Rationale |
|------|-------|-----------|
| Architecture | 7/10 | Clear sync/async split; DB-heavy hot path |
| Backend correctness | 7/10 | Broad tests; some integration gaps |
| Authentication | 7/10 | Solid JWT; localStorage tokens |
| Authorization | 6/10 | BOLA partial; tool invoke returns 200 on block |
| API security | 7/10 | Good rules; heuristic limits |
| LLM security | 6/10 | Deterministic only; mock default |
| Agent security | 7/10 | Real approval flow; limited concurrency tests |
| ML quality | 4/10 | Honest synthetic; V1 train leakage |
| Incident response | 7/10 | Real worker; mock response actions |
| Frontend | 6/10 | Real APIs; minimal test depth |
| Testing | 7/10 | 220 tests; permissive attack lab |
| Test quality | 6/10 | Strong unit; weak live integration |
| Docker | 5/10 | Hardened compose; not built this audit |
| Terraform | 6/10 | Valid modules; not applied; pre-provisioned SQS perms |
| CI/CD | 7/10 | Solid gates; some scans non-blocking |
| Observability | 6/10 | Prometheus metrics present |
| Documentation | 6/10 | Honest README; stale counts in older docs |
| Reproducibility | 5/10 | Dirty tree; Docker/Postgres required |

**Overall engineering score:** **6.5/10**  
**Overall security score:** **6.5/10**  
**Overall portfolio score:** **7.5/10** (strong demo narrative, honest limitations)

---

## 30. Critical / high findings (Phase 34)

### HIGH-1: Feature freeze vs dirty worktree

**Location:** Git state  
**Impact:** Release claims do not match committable artifact; LLM/ML V2 unauditable from HEAD alone  
**Remediation:** Single commit or tag; CI on that SHA  

### HIGH-2: Attack lab pass criteria permissive

**Location:** `attack_lab/scripts/run_all.py::_evaluate`  
**Impact:** False PASS if any block/review unrelated to attack  
**Remediation:** Assert `decision`, `findings` rule IDs, or event types  

### MEDIUM-1: JWT in localStorage

**Location:** `frontend/src/stores/authStore.ts`  
**Impact:** XSS → token theft  
**Remediation:** httpOnly cookies or BFF pattern  

### MEDIUM-2: BOLA coverage partial

**Location:** `gateway/service.py` modeled routes  
**Impact:** IDOR on unmodeled resources may reach upstream  
**Remediation:** Document scope; extend ownership map  

### MEDIUM-3: ML V1 Isolation Forest trains on test data

**Location:** `ml/pipeline.py` line 82 `iforest.fit(X)`  
**Impact:** Inflated offline anomaly metrics  
**Remediation:** Train on train split only (V2 already does)  

### MEDIUM-4: Rate limiting not distributed

**Location:** `services/ratelimit.py`  
**Impact:** Multi-instance bypass under load  
**Remediation:** Redis or centralized store (documented limitation)  

### LOW-1: `/health` liveness only

**Location:** `main.py`  
**Impact:** Orchestrator may route to DB-degraded instance  
**Remediation:** Optional readiness probe  

### FIXED this audit (LOW)

**Terraform RDS `vpc_id`:** Required but unused variable broke `terraform validate` — **removed**, validate **passes**.

---

## 31. Recommended remediation order

1. Commit or tag current worktree; align docs to one SHA  
2. Tighten attack-lab assertions (rule IDs + decisions)  
3. Add duplicate-approval integration test  
4. Fix ML V1 IF train/test leakage (or document V1 deprecated)  
5. httpOnly session storage for frontend  
6. Expand BOLA route coverage or document explicit scope  
7. Re-run Docker + attack lab + bypass when daemon available  

---

## 32. Test results reproduced (this audit)

| Suite | Result |
|-------|--------|
| pytest | **219 passed, 1 failed** / 220 collected (`test_failed_logins_eventually_return_429_postgres` — no Postgres) |
| ruff | **PASS** |
| mypy | **PASS** (96 files) |
| bandit -lll | **0 High** |
| frontend vitest | **7/7 PASS** |
| ML V2 eval script | **PASS** — RF F1 ~0.661, ROC-AUC ~0.770 (synthetic) |
| terraform validate | **PASS** (after fix) |
| attack lab live | **NOT VERIFIED** |
| docker build | **NOT VERIFIED** |
| performance benchmark | **NOT VERIFIED** |

---

## 33. Final classification (Phase 36)

**PRODUCTION-ORIENTED PROTOTYPE**

Not production-ready: synthetic ML, mock LLM default, no AWS deployment, ~4 req/s local throughput, partial BOLA, permissive attack-lab gates, uncommitted release state.

Not merely "PROTOTYPE" — the gateway enforcement path is substantial, tested, and architecturally coherent.

---

## 34. Unresolved at audit close

- Live attack lab / bypass / Docker stack  
- pip-audit / detect-secrets local run  
- Real LLM provider with API key  
- Performance benchmark re-run  
- Full authorization matrix live probing  
- Whether CI terraform job passed **before** vpc_id fix on remote  

---

*This audit does not trust prior agent reports. Evidence is limited to files inspected and commands executed on 2026-08-13.*
