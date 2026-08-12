# AEGIS Cloud Readiness Report

**Date:** 2026-08-13  
**Phase:** ARCHITECT → VALIDATE → HARDEN → DOCUMENT  
**Deployment status:** **TERRAFORM DEFINED — NOT DEPLOYED**

No `terraform apply`, `terraform destroy`, or live AWS resource creation was performed in this phase.

---

## Executive summary

AEGIS has a **coherent AWS target architecture** (WAF → ALB → ECS Fargate → RDS) with Terraform modules for network, IAM, ECS, RDS, S3, SQS, WAF, and monitoring. Application security enforcement is **real and synchronous** in the gateway. Cloud integration is a **design skeleton**: S3 and SQS exist in Terraform but are **not wired in application code**; the worker polls PostgreSQL, not SQS.

The repository is **deployable-by-design** but has **explicit blockers** (ECR images, ACM cert, secret population, migrations, upstream URL, remote state) that must be resolved before production apply.

---

## 1. Current state (Phase 1)

### Terraform (`terraform/environments/dev/`)

| Module | Implemented | Production-ready? |
|--------|-------------|-------------------|
| `network` | VPC, 2 AZ public/private, NAT, IGW, ALB/ECS/RDS SGs | Yes for dev skeleton |
| `iam` | Execution, gateway task, worker task roles; JWT secret | Hardened (no duplicate DB secret) |
| `rds` | Postgres 16, private, encrypted, managed password | Dev defaults; enable deletion protection for prod |
| `ecs` | Cluster, ALB, HTTPS listener, backend + worker task defs + services | Blockers: placeholder image/ACM |
| `s3` | Bucket, block public, SSE, versioning, lifecycle | No app integration |
| `sqs` | Queue + DLQ, SSE | No app integration |
| `waf` | Rate limit + CommonRuleSet on ALB | Appropriate perimeter scope |
| `monitoring` | ALB 5xx, RDS CPU, SQS depth alarms | Minimal; expand for prod |

**Terraform validation:** CI runs `terraform fmt -check` and `terraform validate` on Ubuntu. Local Windows environment: **Terraform CLI not in PATH** — static review + CI are authoritative.

### Docker

| Artifact | Notes |
|----------|-------|
| `backend/Dockerfile` | Python 3.13-slim, non-root UID 10001, HEALTHCHECK |
| `frontend/Dockerfile` | nginx SPA (not in AWS Terraform yet) |
| `docker-compose.yml` | postgres, mock-api, backend, worker; hardened compose options |

ECS task definitions now set `user = "10001:10001"` to match the image.

### Application configuration

| Area | Implementation |
|------|----------------|
| Database | asyncpg via `DATABASE_URL`; Alembic migrations |
| Worker | PostgreSQL poll + `FOR UPDATE SKIP LOCKED`; optional in-process via `AEGIS_IN_PROCESS_WORKER` |
| Gateway | Synchronous pipeline; fail-closed on hard-block rules |
| S3 / SQS | **No boto3 usage** |
| Secrets | Env vars: `DATABASE_URL`, `SECRET_KEY`, optional `LLM_API_KEY` |
| ML | Local model dir; continues if model missing |
| LLM | Optional; `llm_fallback_deterministic=true` |

---

## 2. Target architecture assessment (Phase 2)

**Verdict: ALB + ECS Fargate + private RDS is appropriate** for AEGIS.

| Component | Appropriate? | Notes |
|-----------|--------------|-------|
| WAF + ALB | Yes | Standard HTTPS perimeter |
| ECS Fargate | Yes | Stateless gateway + worker |
| API Gateway | Not required now | Add only if API-management features needed |
| RDS PostgreSQL | Yes | Matches app (async SQLAlchemy) |
| S3 | Future | Terraform ready; app not using |
| SQS | Future | Terraform ready; worker uses DB queue pattern today |
| Secrets Manager | Yes | ECS secrets injection pattern in place |

**Not added (deliberately):** Lambda, EKS, CloudFront (unless global edge needed), redundant services without app requirement.

---

## 3. Network security (Phase 3)

### Traffic flow

```
Client ──443──► WAF ──► ALB (public subnet)
                         │
                         └──8000──► ECS backend (private)
                                      │
                                      ├──5432──► RDS (private)
                                      ├──443──► upstream API (via NAT)
                                      └── AWS APIs (Secrets Manager, etc.)

Worker (private, same ECS SG) ──5432──► RDS
```

### Controls verified in Terraform

- RDS `publicly_accessible = false`
- RDS SG ingress: port 5432 **from ECS SG only**
- ALB SG: 443 from `0.0.0.0/0`
- ECS SG: 8000 **from ALB SG only**
- ECS tasks: no public IP

### Residual exposure

- ALB is internet-facing (required)
- ECS egress is open to `0.0.0.0/0` (needed for upstream + AWS APIs)
- No VPC endpoints (Secrets Manager/ECR traffic goes via NAT — cost/latency consideration)

---

## 4. ECS security (Phase 4)

| Control | Status |
|---------|--------|
| Non-root container user | Dockerfile + ECS `user: 10001:10001` |
| No hardcoded credentials | Secrets via Secrets Manager ARNs |
| Separate worker task role | Yes (SQS consume only vs gateway publish) |
| Health checks | Backend: `/health` |
| Logging | awslogs driver, 14-day retention |
| CPU/memory | Backend 512/1024, worker 256/512 |

**Gaps:**

- No ECS auto-scaling
- No deployment circuit breaker
- `UPSTREAM_BASE_URL` not in task definition
- Alembic not run automatically on task start

---

## 5. IAM review (Phase 5)

| Policy | Who | Why | Narrowed? |
|--------|-----|-----|-----------|
| `AmazonECSTaskExecutionRolePolicy` | Execution role | ECR + logs | AWS managed |
| `secrets-read` | Execution role | Inject DATABASE_URL, SECRET_KEY | Specific ARNs only |
| `task-permissions` | Gateway task | Future S3 evidence + SQS publish | Bucket prefix + named queue |
| `worker-permissions` | Worker task | Future SQS consume | Named queue only |

**No `Action: "*"` on `Resource: "*"`** in custom policies.

**Note:** Gateway has SQS/S3 permissions before app uses them — acceptable for forward compatibility; remove if strict least-privilege required pre-integration.

---

## 6. Database (Phase 6)

| Requirement | Status |
|-------------|--------|
| Private subnets | Yes |
| Encryption at rest | Yes |
| Backups | 7 days (dev) |
| Security group | ECS only |
| Credentials via Secrets Manager | RDS master auto; app URL manual |
| No public access | Yes |

**Allowed to reach RDS:** ECS tasks (backend + worker) in the ECS security group only.

---

## 7. S3 (Phase 7)

| Requirement | Status |
|-------------|--------|
| Block Public Access | All four flags |
| Encryption | SSE-S3 |
| Least privilege IAM | Gateway task: Put/Get on bucket objects |
| Versioning | Enabled |
| Lifecycle | 365d expiration, 90d noncurrent |

Sensitive evidence **cannot become public** via bucket policy (BPA enforced). Application does not upload evidence yet.

---

## 8. SQS (Phase 8)

| Aspect | Status |
|--------|--------|
| Queue + DLQ in Terraform | Yes |
| SSE | Enabled |
| App integration | **None** |
| Worker architecture | PostgreSQL poll |

**Security invariant (verified in code):** Gateway decisions (`BLOCK`, `REQUIRE_REVIEW`, etc.) are resolved synchronously in `gateway/service.py` before response. Worker processes `SecurityEvent` rows for correlation/incidents only. If worker, SQS, or correlation fails, **request-time enforcement still operates**.

---

## 9. Secrets map (Phase 9)

| Secret | Env var | In Git? | In Docker image? | In Terraform plaintext? | Runtime source |
|--------|---------|---------|------------------|-------------------------|----------------|
| DB connection | `DATABASE_URL` | No (.env.example only) | No | No | Secrets Manager |
| JWT signing | `SECRET_KEY` | No | No | No | Secrets Manager |
| LLM provider | `LLM_API_KEY` | No | No | No | Manual (not in TF) |
| AWS creds | N/A on ECS | No | No | No | Task IAM roles |

Production startup **refuses default JWT secret** unless `AEGIS_ALLOW_INSECURE_SECRET=true`.

---

## 10. WAF (Phase 10)

| Rule | Purpose |
|------|---------|
| RateLimit (2000/IP/5min) | Abuse / volumetric |
| AWSManagedRulesCommonRuleSet | Common web attacks |

WAF does **not** replace AEGIS SQLi/BOLA/policy logic. Application remains authoritative for security decisions.

---

## 11. Observability (Phase 11)

| Signal | Available today |
|--------|-----------------|
| ECS logs | CloudWatch log group |
| ALB 5xx | Alarm |
| RDS CPU | Alarm |
| SQS depth | Alarm (queue unused) |
| App `/metrics` | Prometheus format (not wired to CloudWatch) |
| Security events | RDS tables |

**Logging hygiene:** structlog in app; avoid logging tokens, keys, raw prompts.

**Gap:** No CloudWatch dashboard, no custom metric alarms for gateway latency or blocked-request rate.

---

## 12. Scalability (Phase 12)

### CURRENT LOCAL BENCHMARK (not production capacity)

From [PERFORMANCE.md](../PERFORMANCE.md) — local Docker, single uvicorn worker:

| Metric | Value |
|--------|-------|
| Gateway overhead vs upstream | ~215 ms serial |
| Throughput (serial) | ~4 req/s |
| Throughput (20 concurrent workers) | ~4–5 req/s aggregate |
| Primary bottleneck | ~15 sequential DB queries in `collect_request_stats` (~110 ms) |

**Limits throughput today:**

1. Serial DB aggregation per request
2. Single-process uvicorn in benchmarks
3. No connection pool tuning documented for RDS
4. No ECS auto-scaling configured

Do **not** promise production scale without AWS load testing.

---

## 13. Failure modes (Phase 13)

| Failure | Expected behavior | Safe? |
|---------|-------------------|-------|
| RDS unavailable | Gateway DB ops fail → 5xx; no silent allow on hard blocks | Fail closed on errors in critical path |
| SQS unavailable | No impact today (unused) | N/A |
| Worker unavailable | Events queue in DB; correlation delayed; sync enforcement unaffected | Yes |
| LLM provider unavailable | Deterministic + ML + policy continue; `llm_fallback_deterministic` | Yes |
| ML model unavailable | Inference skipped; rules/policy continue | Yes |
| Secrets Manager unavailable | ECS task fails to start (cannot inject secrets) | Fail closed (no start) |
| CloudWatch unavailable | App continues; logs may buffer/drop locally | Security enforcement independent |

**Hard-block rules** (API-005–009, 016, 017) always prefer BLOCK when matched, regardless of async components.

---

## 14. Terraform quality (Phase 14)

### Changes made in this phase

- Module order: RDS before IAM (single DATABASE_URL secret ARN)
- Removed duplicate IAM `database-url` secret
- Added worker task definition + ECS service
- Parameterized `aws_region` in log configuration
- Added container user, health check, `app_environment`
- S3 versioning + lifecycle
- SQS DLQ
- SQS depth alarm
- RDS outputs for master user secret
- `terraform.tfvars.example`

### Remaining quality gaps

- No remote state backend
- No `prod` environment directory (only `dev`)
- Placeholder ACM + ECR values
- No VPC endpoints
- ECS services will fail until images/cert valid

---

## 15. Terraform security (Phase 15)

Static review findings:

| Finding | Severity | Status |
|---------|----------|--------|
| Placeholder ACM cert | Blocker | Documented; replace before apply |
| `skip_final_snapshot=true` (dev) | Medium | Toggle for prod |
| `deletion_protection=false` (dev) | Medium | Toggle for prod |
| Open ALB 443 from internet | Expected | WAF attached |
| ECS egress 0.0.0.0/0 | Expected | Required for upstream |
| No wildcard IAM in custom policies | Good | Verified |
| No hardcoded secrets in `.tf` | Good | Verified |

**Tools not run locally:** tfsec/checkov — recommend in CI as non-blocking.

---

## 16–17. Documentation & DR

Created:

- [AWS_DEPLOYMENT.md](../AWS_DEPLOYMENT.md) — full deployment guide (17 sections)
- This report

DR: RDS backups configured; cross-region replication, secrets replica, and measured RPO/RTO **not implemented**.

---

## Deployment blockers

| # | Blocker | Owner action |
|---|---------|--------------|
| 1 | ECR image push + task definition URI | DevOps |
| 2 | ACM certificate for production domain | DevOps |
| 3 | Populate JWT + DATABASE_URL secrets | DevOps |
| 4 | Run Alembic migrations | DevOps |
| 5 | Set UPSTREAM_BASE_URL (real upstream) | DevOps |
| 6 | Remote Terraform state | DevOps |
| 7 | Production toggles (deletion protection, app_environment) | DevOps |
| 8 | AWS load test | SRE |
| 9 | Optional S3/SQS app integration | Engineering |

---

## Known limitations

1. S3/SQS in Terraform only — not in application
2. Worker uses PostgreSQL queue, not SQS
3. Frontend not deployed in AWS Terraform
4. mock-api must never ship to production
5. ~4 req/s local benchmark — not production capacity proof
6. Single-region, no DR drill
7. LLM secret not in Terraform ECS task definition

---

## Conclusion

AEGIS is **architecturally ready for AWS deployment planning** with hardened Terraform modules and comprehensive documentation. The system **must not be considered production-deployed** until blockers are cleared and `terraform apply` is explicitly approved.

**Next step:** Complete blockers → `terraform plan` review → staged apply in a non-production AWS account → load test → production cutover.
