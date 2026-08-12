# AEGIS AWS Deployment Guide

**Status: TERRAFORM DEFINED — NOT DEPLOYED**

This document describes how to deploy AEGIS to AWS when you are ready. No AWS resources have been created by this repository phase. Do **not** run `terraform apply` until prerequisites below are satisfied and secrets are provisioned.

For the readiness assessment, see [verification/CLOUD_READINESS_REPORT.md](verification/CLOUD_READINESS_REPORT.md).

---

## 1. Architecture

```
                         INTERNET
                            |
                            v
                      AWS WAF (regional)
                   rate limit + CommonRuleSet
                            |
                            v
              Application Load Balancer (HTTPS, public subnets)
                            |
                            v
                   ECS Fargate (private subnets)
                     /              \
                    v                v
              AEGIS backend      Correlation worker
              (uvicorn :8000)    (python -m app.worker.main)
                    |                |
         +----------+--------+-------+
         |          |        |
         v          v        v
       RDS        S3*      SQS*
   PostgreSQL   evidence   events
   (private)    (future)   (future)

* S3 and SQS are defined in Terraform but **not yet used by application code**.
  The worker polls PostgreSQL today, not SQS.

Supporting: Secrets Manager · CloudWatch · IAM · VPC · NAT · ECR
```

**Design rationale:** ALB + ECS Fargate is appropriate for a stateless HTTP gateway with a separate async worker. API Gateway is not required unless you need usage plans, request transformation, or edge authorizers at the gateway layer. WAF on ALB provides perimeter defense; AEGIS remains the application-level enforcement layer.

---

## 2. Prerequisites

Before `terraform plan` / `apply`:

| Requirement | Notes |
|-------------|-------|
| AWS account | Billing alerts recommended |
| IAM permissions | Ability to create VPC, ECS, RDS, IAM roles, Secrets Manager, etc. |
| Terraform ≥ 1.5 | CI validates with 1.9.8 |
| AWS CLI | For ECR push, secret population, ops |
| Domain + ACM certificate | Validated cert in the same region as ALB |
| ECR repository + pushed image | Replace `REPLACE_WITH_ECR_IMAGE` |
| Remote state backend | **Not configured** — add S3 + DynamoDB before team use |
| Upstream API URL | Set `UPSTREAM_BASE_URL` on backend tasks (not in Terraform yet) |
| Database migrations | Run `alembic upgrade head` once after RDS is available |
| Secret values | Populate JWT and full `DATABASE_URL` in Secrets Manager |

---

## 3. AWS services

| Service | Terraform module | Purpose |
|---------|------------------|---------|
| VPC | `network` | Public/private subnets, NAT, IGW, security groups |
| ALB | `ecs` | HTTPS termination, health checks |
| ECS Fargate | `ecs` | Backend (2 tasks) + worker (1 task) |
| RDS PostgreSQL 16 | `rds` | Telemetry, incidents, auth data |
| S3 | `s3` | Evidence artifacts (future app integration) |
| SQS | `sqs` | Async events + DLQ (future app integration) |
| Secrets Manager | `iam`, `rds` | JWT, DATABASE_URL shell, RDS master password |
| WAFv2 | `waf` | Rate limit + managed common rules |
| CloudWatch | `ecs`, `monitoring` | Logs, Container Insights, alarms |
| IAM | `iam` | Execution, task, worker roles |
| ECR | **Manual** | Container images (not created by Terraform) |

---

## 4. IAM

Three runtime roles (see `terraform/modules/iam/`):

| Role | Used by | Permissions |
|------|---------|-------------|
| **ECS execution** | Both tasks | ECR pull, CloudWatch logs, `secretsmanager:GetSecretValue` on JWT + DATABASE_URL secrets only |
| **ECS task (gateway)** | Backend | `s3:PutObject/GetObject` on evidence bucket; `sqs:SendMessage` on events queue |
| **Worker task** | Worker | `sqs:ReceiveMessage/DeleteMessage/...` on events queue only |

No wildcard `Action: "*"` / `Resource: "*"` in module policies.

**Gap:** Worker does not need SQS permissions until the app publishes/consumes SQS. Permissions are pre-provisioned for the target design.

---

## 5. Secrets

| Secret | Secrets Manager path | Consumed by | Source |
|--------|---------------------|-------------|--------|
| `DATABASE_URL` | `aegis/{env}/rds-connection` | Backend, worker | **Manual post-provision** (see below) |
| RDS master password | RDS-managed secret (auto) | Ops / rotation | RDS `manage_master_user_password` |
| `SECRET_KEY` (JWT) | `aegis/{env}/jwt` | Backend, worker | **Manual** — strong random value |
| `LLM_API_KEY` | Not in Terraform | Backend (optional) | Manual secret + ECS env mapping when LLM enabled |

**Never** store secrets in Git, Docker images, frontend bundles, Terraform source, or CloudWatch logs.

### Populate DATABASE_URL after RDS exists

1. Read RDS endpoint from Terraform output `rds_endpoint`.
2. Read master credentials from `rds_master_user_secret_arn` (JSON: `username`, `password`).
3. Write to `aegis/{env}/rds-connection`:

   ```
   postgresql+asyncpg://USER:PASSWORD@HOST:5432/aegis
   ```

4. ECS tasks reference this ARN; execution role can read it.

---

## 6. Networking

### Subnets

| Type | Routes | Resources |
|------|--------|-----------|
| Public | 0.0.0.0/0 → IGW | ALB, NAT gateways |
| Private | 0.0.0.0/0 → NAT | ECS tasks, RDS |

### Security groups (traffic flow)

```
Internet :443  →  ALB SG
ALB SG       →  ECS SG :8000
ECS SG       →  RDS SG :5432
ECS SG       →  0.0.0.0/0 (egress: upstream API, AWS APIs, NAT)
RDS          →  no public access (publicly_accessible = false)
```

RDS accepts PostgreSQL **only** from the ECS security group. Worker uses the same ECS SG, so it can reach RDS without a separate worker SG.

### NAT

One NAT gateway per AZ in the module (cost vs availability tradeoff). ECS tasks have `assign_public_ip = false`.

---

## 7. Terraform workflow

```powershell
cd terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars
# Edit: acm_certificate_arn, backend_image, worker_image

terraform init          # configure remote backend first for teams
terraform fmt -recursive ../..
terraform validate
terraform plan          # review only — no apply in this phase
```

**Module order:** `network` → `rds` → `s3` / `sqs` → `iam` → `ecs` → `waf` → `monitoring`

**Validation status:**

- CI job `Terraform (fmt, validate)` runs on every push/PR.
- Local Windows dev environment may not have Terraform installed; rely on CI for authoritative validation.

**State:** Default local state. Configure S3 backend + DynamoDB locking before shared/production use.

---

## 8. ECR

Terraform does **not** create ECR repositories. Before deploy:

```bash
aws ecr create-repository --repository-name aegis-backend --region us-east-1
docker build -t aegis-backend ./backend
docker tag aegis-backend:latest ACCOUNT.dkr.ecr.REGION.amazonaws.com/aegis-backend:latest
aws ecr get-login-password | docker login ...
docker push ACCOUNT.dkr.ecr.REGION.amazonaws.com/aegis-backend:latest
```

Set `backend_image` and `worker_image` in `terraform.tfvars` (same image, different command for worker).

---

## 9. ECS

| Setting | Backend | Worker |
|---------|---------|--------|
| CPU / memory | 512 / 1024 | 256 / 512 |
| User | `10001:10001` (matches Dockerfile) | same |
| Health check | `GET /health` | none (batch poller) |
| Logs | `/ecs/{env}-aegis` | same group, prefix `worker` |
| Desired count | 2 | 1 |
| In-process worker | `AEGIS_IN_PROCESS_WORKER=false` | N/A |

**Post-deploy steps:**

1. Run Alembic migrations (one-off ECS task or CI job with VPC access).
2. Set `UPSTREAM_BASE_URL` to your real upstream API (add to task definition or use a secret).
3. For production stacks, set `app_environment = "production"` so JWT default-secret guard activates.

**Not in Terraform yet:** auto-scaling policies, deployment circuit breaker, service connect, upstream URL.

---

## 10. RDS

| Control | Value |
|---------|-------|
| Engine | PostgreSQL 16 |
| Network | Private subnets only |
| Encryption | `storage_encrypted = true` |
| Public access | `false` |
| Backups | 7 days (dev default); increase for prod |
| Master password | RDS-managed → Secrets Manager |
| Multi-AZ | `false` in dev skeleton |

**Production toggles** (before prod apply):

- `db_deletion_protection = true`
- `db_skip_final_snapshot = false`
- Longer `db_backup_retention_days`

---

## 11. S3

Bucket: `{project}-{env}-evidence`

| Control | Status |
|---------|--------|
| Block Public Access | All four flags enabled |
| Encryption | SSE-S3 (AES256) |
| Versioning | Enabled |
| Lifecycle | Expire objects after 365d; noncurrent versions after 90d |

**Application:** No boto3 S3 usage in backend today. IAM permissions are pre-provisioned for future evidence storage.

---

## 12. SQS

Queue: `{project}-{env}-events` + DLQ after 5 failed receives.

**Application:** No SQS integration today. Worker uses PostgreSQL `FOR UPDATE SKIP LOCKED` on `security_events`.

**Security invariant:** Gateway enforcement is **synchronous**. Worker/SQS failure must not weaken request-time BLOCK decisions. Correlation and incident creation are async-only concerns.

---

## 13. WAF

Attached to ALB (`terraform/modules/waf/`):

1. **RateLimit** — 2000 requests / 5 min / IP (block)
2. **AWSManagedRulesCommonRuleSet** — common injection/XSS patterns

WAF is **perimeter defense only**. Do not duplicate every AEGIS rule in WAF. Tune rate limits after observing real traffic.

---

## 14. Monitoring

| Signal | Alarm |
|--------|-------|
| ALB target 5xx | `>{env}-aegis-alb-5xx` (>10 / 5min) |
| RDS CPU | `>{env}-aegis-rds-cpu` (>80%) |
| SQS depth | `>{env}-aegis-sqs-depth` (>1000) |

ECS Container Insights enabled on cluster. Log retention: 14 days.

**Recommended additions (manual):** ECS CPU/memory, custom application metrics from `/metrics`, WAF blocked request count, worker batch latency.

**Logging hygiene:** Do not log JWTs, API keys, passwords, raw LLM prompts, or PII.

---

## 15. Rollback

| Layer | Rollback |
|-------|----------|
| ECS | Revert task definition to previous revision; update service |
| Terraform | `terraform plan` with previous code; apply previous image tag |
| RDS | Restore from snapshot (see DR) — **not** reversible by ECS alone |
| WAF | Re-associate previous Web ACL or disable rules |

Always keep previous ECR image tags immutable.

---

## 16. Disaster recovery considerations

| Asset | Protection | Restore |
|-------|------------|---------|
| RDS | Automated backups (retention configurable) | Restore snapshot to new instance; update DATABASE_URL secret |
| S3 | Versioning + AWS durability | Revert object version or cross-region replication (not configured) |
| SQS | Messages ephemeral (1 day retention) | Replay from DLQ if app integrated |
| ECS tasks | Stateless | Redeploy from ECR |
| Secrets | Secrets Manager | Restore from backup/replica (not configured) |
| Terraform state | **Local by default** | Remote backend + versioning required |

**RPO/RTO:** Not measured. Design targets depend on backup retention and operational runbooks — document actual values after DR drill.

---

## 17. Security checklist

Before first production apply:

- [ ] Replace `REPLACE_WITH_ACM_CERTIFICATE_ARN`
- [ ] Replace `REPLACE_WITH_ECR_IMAGE` with pinned digest/tag
- [ ] Populate JWT secret in Secrets Manager
- [ ] Populate full DATABASE_URL secret
- [ ] Set `app_environment = "production"`
- [ ] Set `db_deletion_protection = true`
- [ ] Configure remote Terraform state with locking
- [ ] Run `alembic upgrade head`
- [ ] Set `UPSTREAM_BASE_URL` to production upstream (not mock-api)
- [ ] Remove mock-api from any production topology
- [ ] Configure CORS for production frontend origin
- [ ] Review WAF rate limit for expected traffic
- [ ] Enable AWS GuardDuty / Security Hub (optional, not in Terraform)
- [ ] Confirm no secrets in logs or Git (`detect-secrets` baseline)

---

## What still must happen before real deployment

1. **Provision secrets** (JWT, DATABASE_URL assembly)
2. **Build and push ECR images**
3. **Validate ACM certificate** for production hostname
4. **Configure remote state** backend
5. **Run database migrations**
6. **Wire upstream URL** and production CORS
7. **Load test** in AWS — local benchmark (~4 req/s per worker) is not production capacity
8. **Optional:** Integrate S3/SQS in application code if async evidence/events are required
9. **`terraform apply`** — only after explicit approval

See [CLOUD_READINESS_REPORT.md](verification/CLOUD_READINESS_REPORT.md) for blockers and failure-mode analysis.
