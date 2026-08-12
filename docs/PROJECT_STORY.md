# AEGIS Project Story

How this project evolved from problem statement to feature freeze — with real engineering problems, not a generated-and-abandoned codebase.

---

## 1. Problem

APIs and LLM endpoints expose injection, authorization, and abuse surfaces that WAFs treat as opaque HTTP. The goal: build a **demonstrable** security gateway that combines deterministic detection, behavioral context, ML scoring, LLM heuristics, agent tool controls, and operator visibility — in one repo you can run, test, and explain in an interview.

---

## 2. Architecture

Chose a **monolithic FastAPI gateway** with internal modules rather than microservices — faster iteration for a portfolio project. PostgreSQL holds telemetry, events, incidents, policies, and approvals. A separate worker process correlates events asynchronously so enforcement never depends on it.

Key design rule early: **synchronous fail-closed enforcement**, async everything else.

---

## 3. Implementation

Built in layers:

1. JWT auth + gateway proxy to mock upstream  
2. Deterministic API rules (SQLi, SSRF, traversal, cmd)  
3. Behavioral stats from SQL aggregates  
4. Risk + YAML policy engine  
5. ML pipeline (Isolation Forest + Random Forest on 19 features)  
6. LLM prompt scanner + output redaction  
7. Tool registry + approval workflow  
8. React SOC dashboard on real control-plane APIs  

Each layer has unit tests; the gateway orchestrates them in `gateway/service.py`.

---

## 4. Attack testing

Created `attack_lab/` with 16 scripted scenarios and strict pass criteria (`run_all.py` — not "200 OK means pass"). Added `bypass_tests/` for encoding regressions. CI gained a dedicated **attack-lab job** so security demos aren't manual-only.

**Verified:** 16/16 attack lab, 15/15 bypass (2026-08-13 freeze run).

---

## 5. Bugs discovered

### Plus-encoded SQLi bypass

**Symptom:** Payload `q=1+%OR+%1%3D1` returned ALLOW.  
**Cause:** Malformed `%` tokens hid `OR 1=1` from regex when only raw/standard-decoded strings were scanned.  
**Fix:** Inspection-only decoder (`decode_for_inspection`, bounded 2 rounds) — upstream bytes unchanged.  
**Evidence:** Unit tests + live 403 + bypass suite PASS.

### Bypass suite BOLA semantics

**Symptom:** Own-resource BOLA cases marked FAIL when ALLOW was correct.  
**Fix:** `run_bypass.py` distinguishes EXPECTED ALLOW vs BLOCK.

### Rate-limit test pollution

**Symptom:** Postgres integration test fails after brute-force attack lab on same DB.  
**Lesson:** CI uses fresh Postgres per job; local runs need clean DB or ordering discipline.

### E2E / Docker on Windows

**Symptom:** Intermittent `ConnectionRefusedError` on port 5433 during `e2e.py`.  
**Mitigation:** `ensure_postgres()` bootstrap; document CI as authoritative for full E2E.

---

## 6. Security fixes

Beyond SQLi: JWT authorization tests, auth lockout, login rate limit, tool cross-subject blocking, correlation integrity tests, LLM cost budget tests, response redaction coverage. Bandit `-lll` clean; pip-audit clean on runtime deps.

Encoding matrix documented in [FINAL_RELEASE_REPORT.md](verification/FINAL_RELEASE_REPORT.md).

---

## 7. Performance measurement

Profiled gateway phases — discovered **~110 ms** in `collect_request_stats` (9+ sequential SQL queries). Documented honest numbers in [PERFORMANCE.md](PERFORMANCE.md):

- ~215 ms serial overhead vs upstream  
- ~4 req/s local throughput  
- Did **not** claim production capacity  

---

## 8. Frontend

React dashboard consumes real APIs — not mock charts. Pages: dashboard, events, incidents, policies, approvals, ML, audit. Vitest tests for auth guard and API client. Production build verified.

---

## 9. Cloud architecture

Terraform modules for VPC, WAF, ALB, ECS (backend + worker tasks), private RDS, S3, SQS, IAM, CloudWatch. Hardened in cloud-readiness phase: non-root ECS user, DLQ, S3 versioning, scoped IAM.

**Honest gap:** Application does not use boto3 S3/SQS yet; worker polls PostgreSQL. Terraform is **design**, not deployment.

---

## 10. Final security posture

| Area | State |
|------|-------|
| Controlled attack scenarios | 16/16 PASS |
| Encoding bypass regressions | 15/15 PASS |
| Backend tests | 170 collected |
| Mypy / Ruff | Clean |
| AWS deployed | No |
| ML | Synthetic — pipeline real |
| Classification | **Production-oriented prototype** |

---

## Feature freeze (2026-08-13)

No new features unless security/correctness/reproducibility issues. Portfolio docs added: resume bullets, interview guide, demo script, limitations, future work.

This project was **built, broken, tested, fixed, measured, and documented** — not abandoned after code generation.
