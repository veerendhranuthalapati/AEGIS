# AEGIS Interview Guide

Prepared answers for architecture, security, ML, LLM, agent, cloud, and DevSecOps questions. Claims match this repository — not production deployment fiction.

---

## ARCHITECTURE

### 1. Why build AEGIS?

Modern apps expose REST APIs, LLM chat endpoints, and AI-agent tool calls. Traditional WAFs inspect HTTP superficially and rarely understand prompt injection, tool authorization, or behavioral context in one pipeline. AEGIS demonstrates a **unified gateway** that applies deterministic rules, behavioral telemetry, ML scoring, LLM heuristics, and policy — with a SOC UI for incidents and approvals.

### 2. Why FastAPI?

Async I/O fits gateway forwarding and concurrent DB queries. Pydantic gives strict request/response validation. OpenAPI supports the React dashboard and testing. Python ecosystem includes scikit-learn for the ML tier without a separate service.

### 3. Why PostgreSQL?

Security telemetry (events, rate limits, incidents, policies, approvals, ML metadata) is relational and query-heavy. `FOR UPDATE SKIP LOCKED` gives a simple, reliable worker queue without adding Redis/SQS in the local stack. RDS PostgreSQL maps cleanly to the Terraform design.

### 4. Why a gateway?

Centralizing inspection ensures **every** request passes the same pipeline before upstream exposure. Upstream apps (especially mock/vulnerable targets in the lab) stay unchanged. Policies, audit, and decisions live in one trust boundary.

### 5. Why not microservices?

AEGIS is a portfolio prototype proving an inspection pipeline end-to-end. Splitting rules/ML/LLM into separate services would add network latency, deployment complexity, and failure modes without improving the demonstration. The gateway already modularizes internally (`gateway/`, `ml/`, `security/`).

### 6. Why asynchronous incident correlation?

Correlation requires batching events, similarity scoring, and incident DB writes — work that must **not** block HTTP responses. Enforcement (BLOCK/ALLOW) is synchronous; grouping events into incidents is eventually consistent. If the worker is down, requests are still inspected; incidents may lag.

### 7. What is the trust boundary?

**Untrusted:** Internet clients, frontend browser, upstream response bodies (until redacted).  
**Semi-trusted:** JWT claims (verified server-side).  
**Trusted:** Gateway decision engine, PostgreSQL after gateway write, operator actions on control-plane API.

The worker and UI never override a synchronous BLOCK.

---

## SECURITY

### 8. How does BOLA detection work?

Route-aware checks in `gateway/service.py` compare the authenticated actor's `subject_id` to resource IDs in paths like `/api/users/{id}` and `/api/orders/{id}`. Cross-subject access produces finding `BOLA_ATTEMPT` (rule API-016) → hard BLOCK. Own-resource access is allowed. Coverage is **limited to modeled routes** — not universal object authorization.

### 9. How does authorization work?

JWT access tokens (HS256) carry `sub`, role, permissions. Gateway and control-plane routes use dependency injection to require roles/permissions. Tool calls add a **deterministic** registry check: tool name, actor subject scope, risk tier, and approval state — no LLM decides authorization.

### 10. How does rate limiting work?

Sliding-window counters persisted in PostgreSQL — login endpoint (401 attempts → 429), gateway per-actor limits, LLM call budget. Attack lab verifies brute force: 10×401 then 429 on an isolated test IP bucket.

### 11. How does SSRF detection work?

Rules scan URL-like input for private/link-local IP patterns, metadata IP `169.254.169.254`, dangerous schemes (`file:`, `gopher:`), and suspicious hostnames. Variants run through `inspection_variants()` after bounded decoding.

### 12. How does SQLi detection work?

Regex patterns match `UNION SELECT`, `OR 1=1`, `pg_sleep`, etc. on query/body text. **Inspection-only decoding** (`decode_for_inspection`) normalizes plus-encoding and malformed `%` tokens without changing forwarded bytes. Hard-block rule API-006 triggers BLOCK.

### 13. What are the limitations of regex detection?

No regex catches all SQLi/SSRF/cmd variants. Encoding chains beyond two rounds, novel grammar, and context-free matches cause false negatives. False positives hit legitimate search strings. **Defense in depth:** parameterized queries and app-layer auth remain essential.

### 14. How do you prevent secret leakage?

Secrets via environment / Secrets Manager only; production refuses default `SECRET_KEY`. `detect-secrets` baseline in CI. Logs use structlog without raw JWT/body dumps by convention. Response redaction masks common sensitive patterns. Terraform references secret ARNs, not values.

### 15. How does response redaction work?

After upstream response, `security/redact.py` scans body for patterns (API keys, emails, credit cards, etc.) and replaces with placeholders before returning to client. Unit tests in `test_redact.py`.

---

## ML

### 16. Why Isolation Forest?

Unsupervised anomaly detection fits scarce real attack labels. It scores "normal" behavioral feature vectors; high anomaly contributes to risk. Runs fast (~15 ms locally) on 19 numeric features.

### 17. Why Random Forest?

Supervised head on synthetic labeled data produces `threat_probability` for policy/risk blending. Handles mixed feature scales and nonlinear interactions better than a single linear model.

### 18. What features are used?

19 request-time features in `REQUEST_FEATURES`: time-of-day, path depth, request rate, auth failures, body entropy, prompt length, tool call count, endpoint rarity, etc. Response status/size used **offline only** to avoid leakage.

### 19. Why synthetic data?

No public labeled API attack dataset was integrated in project scope. Synthetic generation proves the **training → registry → inference → API** path with reproducible metrics.

### 20. Why are 1.0 metrics not automatically impressive?

Perfect accuracy on separable synthetic data is expected — it validates plumbing, not generalization. Claiming "production ML" from such metrics would be misleading.

### 21. How would you evaluate against real traffic?

Collect anonymized gateway logs → label incidents from SOC feedback → time-based train/test split → report precision/recall at operational thresholds → shadow mode before enforcement.

### 22. What are false positives?

Normal traffic with high rate, rare endpoints, or unusual entropy flagged as anomalous → elevated risk → WARN/REQUIRE_REVIEW without a true attack.

### 23. What are false negatives?

Attacks mimicking normal feature vectors, slow/low-volume probes, or novel payloads missed by rules and ML → ALLOW until rules catch them.

### 24. How would you prevent model drift?

Monitor feature distributions and prediction rates; periodic retrain on fresh labeled data; version models in registry; rollback via `ModelVersion` metadata; alert when anomaly rate spikes.

---

## LLM SECURITY

### 25. What is prompt injection?

User content that attempts to override system instructions, exfiltrate secrets, or manipulate tool calls — e.g., "ignore previous instructions."

### 26. How does AEGIS detect it?

`security/llm/scanner.py` applies heuristic patterns (injection phrases, jailbreak templates, extraction attempts) on prompt routes. Findings feed risk/policy; high-severity LLM findings can yield REQUIRE_REVIEW.

### 27. Why not let an LLM make security decisions?

Non-deterministic, prompt-injectable, high latency, cost, and audit difficulty. AEGIS uses LLM **analysis** optionally; **decisions** come from deterministic rules + policy with fail-closed hard blocks.

### 28. How do you detect output leakage?

Scanner/redaction patterns on upstream LLM responses — system prompt fragments, credential-like strings, PII formats — before returning to client.

### 29. How do you prevent LLM cost abuse?

`llm_max_calls_per_minute`, daily/actor USD budgets in settings, tracking in DB — tests in `test_llm_analyzer_cost.py`. Blocks or throttles when budget exceeded.

### 30. How do you secure AI-agent tools?

Tool registry defines allowed tools, subject scope, risk level. `tool_executor` only runs after gateway authorization. Cross-subject tool args → BLOCK. High-risk tools → REQUIRE_APPROVAL queue.

---

## AGENT SECURITY

### 31. How does tool authorization work?

Deterministic check: registered tool name, actor permissions, subject_id match on arguments, risk score vs threshold, pending approval status. Implemented in gateway tool route — not ML/LLM.

### 32. How does approval work?

`REQUIRE_APPROVAL` decisions create approval records. Admin/operator approves via control-plane API; only then does execution proceed. Demo: `large_payment_approval` attack scenario.

### 33. How do you prevent confused-deputy attacks?

Tool calls bind to authenticated actor's `subject_id`; arguments referencing another subject are rejected (cross-subject tool scenario). Service accounts would need explicit scoped credentials — out of demo scope.

### 34. Why must authorization remain deterministic?

Auditors and incident response need reproducible "why blocked" answers. Probabilistic LLM judgments cannot be sole authorization gate.

---

## CLOUD

### 35. Why ECS/Fargate?

Containerized FastAPI + worker maps 1:1 to Docker Compose. No cluster management; private subnets; IAM task roles for S3/SQS/secrets. Fits stateless gateway scaling.

### 36. Why SQS?

Designed for decoupling event publish from correlation under load. **App does not use SQS yet** — worker polls PostgreSQL. Terraform pre-provisions queue for future integration.

### 37. Why RDS?

Same PostgreSQL semantics as local dev; managed backups, encryption, private subnet placement.

### 38. How is IAM secured?

Separate execution vs task vs worker roles; `secretsmanager:GetSecretValue` scoped to specific ARNs; S3/SQS permissions on named resources; no wildcard admin policies in modules.

### 39. How are secrets handled?

ECS injects `DATABASE_URL` and `SECRET_KEY` from Secrets Manager at task start. JWT secret shell created by Terraform — value set manually. RDS master password RDS-managed.

### 40. Why should RDS be private?

Database contains credentials hashes, security events, incidents — never expose PostgreSQL to internet. Only ECS SG allowed on 5432.

---

## DEVSECOPS

### 41. What happens in CI?

GitHub Actions: backend pytest/ruff/mypy/pip-audit; frontend test/build; terraform fmt/validate; docker build; attack-lab (16 scenarios + bypass); bandit; detect-secrets baseline. Attack-lab job is blocking.

### 42. How do you test attacks automatically?

`attack_lab/scripts/run_all.py` — 16 HTTP scenarios against running gateway; strict PASS/FAIL on status and decision. `bypass_tests/run_bypass.py` — 15 encoding/regression cases.

### 43. How do you scan Docker?

`docker build` in CI; Docker Scout for high/critical CVEs (non-blocking). Backend Dockerfile: non-root user, slim base, health check.

### 44. How do you validate Terraform?

`terraform fmt -check -recursive` and `terraform validate` with `init -backend=false` in CI. No apply in pipeline. Static review for public resources, IAM wildcards, open SGs.

---

## Quick reference metrics

| Metric | Value |
|--------|-------|
| Backend tests | 170 collected |
| Attack lab | 16/16 |
| Bypass suite | 15/15 |
| Gateway overhead | ~215 ms local serial |
| Throughput | ~4 req/s local |
| AWS deployed | No |

See [LIMITATIONS.md](LIMITATIONS.md) before overstating capabilities.
