# AEGIS Limitations

This document states what AEGIS **does not** claim. Read this before demos, interviews, or deployment discussions.

---

## ML

| Limitation | Detail |
|------------|--------|
| **Synthetic dataset** | Training data is generated in `backend/app/ml/training.py` — classes are artificially separable |
| **No production traffic** | Models have not been trained or evaluated on real enterprise API logs |
| **Metrics ≠ real-world accuracy** | High accuracy/F1 on synthetic holdout demonstrates pipeline wiring, not detection quality in production |
| **No adversarial ML testing** | Evasion against the feature vector is not systematically evaluated |
| **Local model storage** | Artifacts live on disk / Docker volume — no managed ML platform |
| **Negligible latency impact locally** | ~15 ms ML phase when model active — does not prove scale under adversarial load |

---

## LLM security

| Limitation | Detail |
|------------|--------|
| **Mock/echo upstream** | Default stack uses `mock-api` echo — no live OpenAI/Anthropic/etc. integration |
| **Heuristic scanner** | Prompt injection detection uses pattern/heuristic rules, not a separate LLM judge |
| **No semantic understanding** | Novel jailbreak phrasing outside patterns may evade detection |
| **Output redaction is pattern-based** | Cannot guarantee all sensitive formats are caught |
| **LLM analyzer disabled by default** | `llm_analyzer_enabled=false` unless API key configured |

---

## Detection (API / behavioral)

| Limitation | Detail |
|------------|--------|
| **Regex + normalization** | SQLi/SSRF/cmd detection is heuristic — not a substitute for parameterized queries, SSRF allowlists, or shell hardening |
| **Bounded decoding** | Inspection uses up to two decode rounds — deeper encoding chains may evade |
| **BOLA scope** | Ownership checks apply to known route semantics — not universal object-level authorization |
| **Rate limits** | Per-actor sliding windows in PostgreSQL — not distributed across gateway replicas |
| **Admin path probing** | Prefix-based — may miss non-standard admin routes |

---

## Cloud

| Limitation | Detail |
|------------|--------|
| **Terraform-defined, not deployed** | No live AWS resources created by this project |
| **S3 / SQS not in app** | Terraform provisions buckets/queues; backend has no boto3 integration yet |
| **Worker uses PostgreSQL poll** | Not SQS — cloud diagram shows target design |
| **Placeholder ECR/ACM** | Must be replaced before any apply |
| **No remote Terraform state** | Local state only in skeleton |
| **Single-region, no DR drill** | RPO/RTO not measured |

---

## Performance

| Limitation | Detail |
|------------|--------|
| **~215 ms serial overhead** | Measured locally vs mock upstream (see `PERFORMANCE.md`) |
| **~4 req/s throughput** | Local benchmark with single uvicorn worker — not production capacity |
| **DB-bound** | ~110 ms in `collect_request_stats` (sequential SQL aggregates) |
| **Concurrent tier** | 20 workers → high latency (~4 s mean) but similar aggregate req/s |

Do **not** extrapolate these numbers to AWS ECS without load testing.

---

## Scaling

| Limitation | Detail |
|------------|--------|
| **Single-process gateway in benchmarks** | Production would need multiple ECS tasks + connection pooling tuning |
| **No auto-scaling configured** | Terraform ECS services have fixed desired counts |
| **RDS connection limits** | Not stress-tested against `db.t4g.micro` limits |
| **In-process worker option** | `AEGIS_IN_PROCESS_WORKER=true` in CI — separate worker recommended for production |

---

## CI / testing

| Limitation | Detail |
|------------|--------|
| **E2E flaky on Windows** | `e2e.py` may fail when Docker port forwarding is unstable |
| **Postgres integration test** | `test_failed_logins_eventually_return_429_postgres` sensitive to polluted DB state |
| **detect-secrets / Terraform** | Not always run locally — CI authoritative |
| **npm audit / Docker Scout** | Non-blocking in CI |
| **Mock upstream only** | Attack lab targets deliberately vulnerable API — not real application stacks |

---

## Security (false positives / negatives)

| Type | Examples |
|------|----------|
| **False positives** | Legitimate SQL-like strings in search queries; aggressive REQUIRE_REVIEW on LLM routes |
| **False negatives** | Novel injection encodings beyond two decode rounds; BOLA on unmodeled resources; semantic prompt attacks |
| **Not covered** | Full OWASP API Top 10 at all layers; DDoS beyond basic rate limits; supply-chain attacks |

AEGIS demonstrates **controlled** detection against **16 scripted scenarios** — not all possible attacks.

---

## Frontend / ops

| Limitation | Detail |
|------------|--------|
| **UI is not a security boundary** | Dashboard reads APIs — enforcement is server-side |
| **Seed credentials in docs** | Development only — never use in production |
| **No SSO / MFA** | JWT username/password only |

---

## Classification

**PRODUCTION-ORIENTED PROTOTYPE** — suitable for portfolio, research, and further hardening. Not a certified production WAF or LLM firewall without substantial additional validation.
