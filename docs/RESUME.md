# AEGIS — Resume Bullets

Use the section that fits your resume format. All metrics are from this repository's measured tests — not production deployment claims.

---

## One-line

Built **AEGIS**, an AI-powered API and LLM security gateway with layered detection (rules, behavioral analytics, ML, policy) and a React SOC dashboard — verified against **16 controlled attack scenarios**, **220 backend tests collected** (at 2026-08-13 audit), and **~215 ms** measured local gateway overhead.

---

## Two-bullet

- Designed and implemented an **AI-powered API/LLM security gateway** in FastAPI combining deterministic injection/BOLA/SSRF detection, behavioral telemetry, Isolation Forest + Random Forest anomaly scoring, LLM prompt heuristics, and policy-driven decisions (ALLOW/BLOCK/REQUIRE_REVIEW/REQUIRE_APPROVAL).
- Verified end-to-end with **220 pytest tests collected** (at 2026-08-13 audit), **16/16 attack-lab scenarios**, **15/15 encoding bypass regressions**, React operator UI, async incident correlation worker, Docker Compose stack, and Terraform AWS architecture (defined, not deployed).

---

## Three-bullet

- Built **AEGIS**, a production-oriented security gateway for REST APIs and LLM/agent endpoints using FastAPI, PostgreSQL, scikit-learn, and React — enforcing synchronous fail-closed decisions before upstream forwarding.
- Implemented multi-layer detection: regex + normalization rules, behavioral rate/enum signals, ML feature pipeline (19 request-time features), LLM injection heuristics, risk aggregation, YAML policy engine, tool authorization with human approval workflow, and MITRE-mapped incident correlation.
- Demonstrated controlled adversarial coverage (**16/16 attack lab**, **15/15 bypass suite**), **219–220 passing backend tests** (at 2026-08-13 audit), frontend build/tests, CI with attack-lab automation, performance profiling (**~215 ms** serial overhead, **~4 req/s** local throughput), and AWS-ready Terraform (ECS/RDS/WAF/IAM).

---

## Detailed project description

**AEGIS — AI-Powered API & LLM Security Gateway**  
*Personal / portfolio project · Python, FastAPI, PostgreSQL, scikit-learn, React, Docker, Terraform*

Modern applications expose REST APIs, LLM chat endpoints, and AI-agent tool calls — attack surfaces that traditional WAFs often treat as opaque HTTP. AEGIS is a security gateway that sits in front of upstream services and applies layered inspection before forwarding traffic.

**Architecture:** Clients hit a FastAPI gateway that runs a synchronous pipeline: JWT authentication → deterministic API rules (SQLi, SSRF, path traversal, command injection, BOLA on known routes) → behavioral statistics from PostgreSQL telemetry → ML inference (Isolation Forest + Random Forest on 19 request-time features) → LLM prompt/output heuristics → risk scoring → policy evaluation → decision. Hard-block rule matches fail closed regardless of async components. A separate correlation worker polls `security_events` with `FOR UPDATE SKIP LOCKED` and groups related activity into incidents for the SOC dashboard.

**Agent security:** Tool registry with deterministic authorization checks, subject scoping, risk thresholds, and admin approval queue for high-value operations (e.g., large payments).

**Verification (at 2026-08-13 audit):** 220 backend tests collected; Ruff + Mypy clean on `app/`; 16-scenario attack lab with strict rule/decision assertions; 15-test encoding bypass regression suite; React frontend with 7 unit tests and production build; Docker non-root images; GitHub Actions CI including attack-lab job.

**Performance (local benchmark, not production capacity):** ~215 ms mean gateway overhead vs ~4 ms bare upstream; ~4 req/s per worker under concurrency — bottleneck traced to sequential DB aggregation queries (~110 ms).

**Cloud (design only):** Terraform modules for VPC, WAF, ALB, ECS Fargate, private RDS, S3, SQS, Secrets Manager, IAM least-privilege roles, CloudWatch alarms. Not deployed; S3/SQS not yet integrated in application code.

**Honest limitations:** ML trained on synthetic data; LLM tier uses mock/echo upstream; heuristic detection with known encoding edge cases; BOLA limited to modeled ownership semantics; not a certified production WAF replacement.

**Classification:** Production-oriented prototype suitable for portfolio demonstration and further hardening.
