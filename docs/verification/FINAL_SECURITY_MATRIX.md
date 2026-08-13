# AEGIS Final Security Matrix

**Date:** 2026-08-13  
**Environment:** Local gateway + PostgreSQL + mock upstream (prior verified run); unit/adversarial tests on validation host  
**Classification:** Controlled scenario verification — **not** proof against all attacks

Legend: **REAL** = implemented code · **MOCK** = test upstream/LLM · **SYNTHETIC** = ML training data

---

## API & auth

| Attack / control | Expected behavior | Actual (evidence) | Status |
|------------------|-------------------|-------------------|--------|
| SQL injection | BLOCK 403 + SQLI rule | HTTP 403 `decision=BLOCK` | **PASS** — attack lab |
| Path traversal | BLOCK 403 | HTTP 403 `decision=BLOCK` | **PASS** — attack lab |
| SSRF indicators | BLOCK 403 | HTTP 403 `decision=BLOCK` | **PASS** — attack lab |
| Command injection | BLOCK 403 | HTTP 403 `decision=BLOCK` | **PASS** — attack lab |
| Admin probe | BLOCK 403 | HTTP 403 `decision=BLOCK` | **PASS** — attack lab |
| BOLA (modeled routes) | BLOCK 403 post-forward | HTTP 403 `decision=BLOCK` | **PASS** — attack lab + `test_bola_enforcement` |
| Brute-force login | 401 then 429 | 429 at attempt 11 | **PASS** — attack lab |
| Missing auth | 401 upstream/gateway | 401 on protected routes | **PASS** — attack lab |
| JWT wrong algorithm | Reject token | `test_wrong_algorithm_rejected` | **PASS** — unit |
| Account lockout | Lock after N failures | `test_auth_lockout` | **PASS** — unit |
| Rate limit (gateway) | BLOCK/REVIEW on abuse | Behavioral rules API-013/015 | **PASS** — unit + performance notes |
| Encoding bypass (15 cases) | Detect or BLOCK | 15/15 bypass suite (prior run) | **PASS** — bypass regression |

---

## LLM security (MOCK provider default)

| Attack / control | Expected behavior | Actual (evidence) | Status |
|------------------|-------------------|-------------------|--------|
| Direct prompt injection | REQUIRE_REVIEW or BLOCK | HTTP 202 `REQUIRE_REVIEW` | **PASS** — attack lab |
| Jailbreak | REQUIRE_REVIEW or BLOCK | HTTP 202 `REQUIRE_REVIEW` | **PASS** — attack lab |
| System prompt extraction | REQUIRE_REVIEW or BLOCK | HTTP 202 `REQUIRE_REVIEW` | **PASS** — attack lab |
| Sensitive extraction (LLM) | REQUIRE_REVIEW or BLOCK | HTTP 202 `REQUIRE_REVIEW` | **PASS** — attack lab |
| Tool manipulation (prompt) | REQUIRE_REVIEW or BLOCK | HTTP 202 `REQUIRE_REVIEW` | **PASS** — attack lab |
| Data exfiltration patterns | REQUIRE_REVIEW or BLOCK | HTTP 202 `REQUIRE_REVIEW` | **PASS** — attack lab |
| Adversarial prompt suite | Rule IDs match expected sets | `tests/adversarial/test_llm_prompt_adversarial` | **PASS** — unit |
| Output secret redaction | Redact + flag | `test_llm_output_security`, adversarial output | **PASS** — unit |
| LLM provider failure | Controlled error; security continues | 502/503 JSON; deterministic scan still ran | **PASS** — `test_llm_failure_modes` + gateway code |
| Real provider (opt-in) | Same pipeline | `LLM_REAL_TESTS=1` integration test | **DESIGNED** — opt-in only |

---

## Agent / tool security

| Attack / control | Expected behavior | Actual (evidence) | Status |
|------------------|-------------------|-------------------|--------|
| Malicious tool call | BLOCK | HTTP 200 `decision=BLOCK` | **PASS** — attack lab |
| Cross-subject tool (BOLA) | BLOCK | HTTP 200 `decision=BLOCK` | **PASS** — attack lab |
| Large payment | REQUIRE_APPROVAL | HTTP 200 `REQUIRE_APPROVAL` | **PASS** — attack lab |
| Unprivileged tool invoke | BLOCK | `test_tool_security` | **PASS** — unit |
| Unknown tool | BLOCK | `test_unknown_tool_blocked` | **PASS** — unit |
| Duplicate approval decide | Second call 409, no double execute | HTTP 409 `Approval already decided` (`tools.py`) | **PASS** — code + idempotent gate |
| Self-approval | 403 | HTTP 403 | **PASS** — code |

---

## ML & policy

| Control | Expected behavior | Actual (evidence) | Status |
|---------|-------------------|-------------------|--------|
| ML inference error | `ml_available=false`; rules continue | `test_ml_inference_failsafe` | **PASS** — unit |
| ML disabled | Weight excluded; not treated as low risk | Risk engine `ml_weight=0` | **PASS** — unit |
| Policy BLOCK | Fail-closed hard block | Policy engine tests | **PASS** — unit |
| Synthetic ML metrics | Not cited as production accuracy | ML_V2_EVALUATION.md | **DOCUMENTED** |

---

## Redaction & audit

| Control | Expected behavior | Evidence | Status |
|---------|-------------------|----------|--------|
| Response secret redaction | Redact known patterns | `test_redact`, output security tests | **PASS** |
| Audit log on approval | `approvals.decide` logged | `tools.decide_approval` | **REAL** |
| Secret sanitization in logs | No raw API keys | `test_llm_secret_handling` | **PASS** |

---

## Failure injection (documented behavior)

| Failure | Expected | Actual behavior | Live tested |
|---------|----------|-----------------|-------------|
| PostgreSQL down | Auth/telemetry fail; no silent allow | DB errors → 5xx on affected routes; `/health` still 200 | **NOT LIVE** — Docker/Postgres stopped |
| Worker down | Gateway enforcement continues | Sync path independent; incidents may lag | **NOT LIVE** |
| LLM provider error | Deterministic protections continue | 502/503 controlled JSON from gateway | **UNIT** — provider mocks |
| ML unavailable | Policy/rules continue | `available=False`; ML weight 0 | **UNIT** |
| Upstream down | Controlled gateway error | httpx error → gateway error response | **NOT LIVE** |
| SQS unavailable | No impact today | **Not in app** — worker polls PostgreSQL | **N/A** — designed only |

**Security invariant:** Request-time BLOCK/REQUIRE_* decisions are resolved in `gateway/service.py` synchronously. Worker, SQS, and correlation failures do not fail open.

---

## Replay / concurrency

| Scenario | Expected | Evidence | Status |
|----------|----------|----------|--------|
| Duplicate security events | No double-count in correlation | `test_duplicate_event_ids_not_double_counted` | **PASS** |
| Duplicate incidents | Suppress within window | `test_recent_incident_suppresses_duplicate` | **PASS** |
| Duplicate approval | 409 on second decide | `Approval.status != pending` check | **PASS** — code |
| Concurrent LLM requests | Semaphore limit | `test_concurrent_semaphore` | **PASS** — unit |
| Replayed JWT | Expiry + signature validation | JWT unit tests | **PASS** |

---

## Explicit non-claims

AEGIS does **not** claim:

- Secure against all attacks or prompt injection
- Zero false positives/negatives in production
- Real-world ML accuracy (training is **SYNTHETIC**)
- Production-ready deployment (**NOT DEPLOYED** to AWS)

---

## Artifacts

| Artifact | Location |
|----------|----------|
| Attack lab (16 scenarios) | `docs/verification/attack_lab_results.json` |
| Bypass suite (15) | Run `attack_lab/bypass_tests/run_bypass.py` |
| Backend tests | 220 collected — `backend/tests/` |
| Adversarial LLM | `backend/tests/adversarial/` |

**Overall:** All **controlled** scenarios pass. Scope is **demonstration + regression**, not certification.
