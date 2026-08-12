# Cloud Security Architecture

**Status: TERRAFORM DEFINED / NOT YET DEPLOYED**

See [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md) for the full deployment guide and [verification/CLOUD_READINESS_REPORT.md](verification/CLOUD_READINESS_REPORT.md) for the readiness assessment.

## Architecture

```
Internet
   │
   ▼
AWS WAF (rate limit + AWSManagedRulesCommonRuleSet)
   │
   ▼
Application Load Balancer (public subnets, HTTPS)
   │
   ▼
ECS Fargate — AEGIS backend (private subnets, 2 tasks)
   ├─► RDS PostgreSQL (private subnets, encrypted, no public access)
   ├─► S3 evidence bucket (block public access, SSE-S3, versioning) — *future app use*
   ├─► SQS events queue + DLQ (SSE) — *future app use*
   └─► Secrets Manager (DATABASE_URL, JWT/SECRET_KEY)

ECS Fargate — correlation worker (private subnets, 1 task)
   └─► RDS PostgreSQL (polls security_events — not SQS today)
```

## Application vs Terraform

| Component | Terraform | Application today |
|-----------|-----------|-------------------|
| Gateway enforcement | ECS backend | Synchronous; fail-closed on hard blocks |
| Async worker | ECS worker service | PostgreSQL poll (`app.worker.main`) |
| SQS | Queue defined | Not used (no boto3) |
| S3 | Bucket defined | Not used (no boto3) |
| In-process worker | Disabled on ECS (`AEGIS_IN_PROCESS_WORKER=false`) | Used in local CI via env var |

## Network boundaries

| Zone | Resources | Exposure |
|------|-----------|----------|
| Public subnets | ALB, NAT | Internet-facing ALB only (443) |
| Private subnets | ECS tasks, RDS | No direct internet ingress |
| Security groups | ALB→ECS:8000, ECS→RDS:5432 | Least privilege |

## IAM (least privilege)

| Role | Purpose | Key permissions |
|------|---------|-----------------|
| ECS execution | Pull images, read secrets | `secretsmanager:GetSecretValue` (JWT + DATABASE_URL ARNs) |
| ECS task | Gateway runtime | S3 Put/Get on evidence bucket; SQS SendMessage |
| Worker task | Correlation (future SQS) | SQS Receive/Delete only |

No `Action: "*"` on `Resource: "*"` in module custom policies.

## Secrets flow

1. RDS master password managed by RDS (`manage_master_user_password`)
2. Full connection string secret shell: `aegis/{env}/rds-connection` — **populate after RDS exists**
3. JWT secret: `aegis/{env}/jwt` — **populate before ECS tasks start**
4. ECS task definitions reference secret ARNs — not plaintext
5. Optional `LLM_API_KEY` — manual secret when LLM tier enabled

## Data flows

- **Request path:** Client → WAF → ALB → AEGIS → upstream API
- **Telemetry:** AEGIS → RDS (events, incidents) — synchronous persistence
- **Correlation:** Worker → RDS (reads unprocessed events) — async; does not gate enforcement
- **Evidence (future):** AEGIS → S3
- **Async events (future):** AEGIS → SQS → worker

## Trust boundaries

| Boundary | Trust level |
|----------|-------------|
| Internet → WAF/ALB | Untrusted |
| ALB → AEGIS | Semi-trusted (TLS terminated at ALB) |
| AEGIS → RDS | Trusted internal |
| Frontend → API | Untrusted client; JWT required |

## Attack surface

- ALB HTTPS endpoint (WAF protected)
- No public RDS
- No public S3 (block public access)
- ECS tasks have no SSH access

## Residual risks

- Placeholder ACM certificate and ECR image — must be replaced before deploy
- DATABASE_URL secret empty until post-provision step
- WAF alone insufficient; AEGIS remains application-level enforcement
- Single-region, no DR configuration in skeleton
- S3/SQS IAM permissions exist before application integration

## Validation

```powershell
cd terraform/environments/dev
terraform fmt -recursive ../..
terraform init -backend=false
terraform validate
```

CI runs the above on every push/PR. Do not run `terraform apply` without explicit approval and secret provisioning.
