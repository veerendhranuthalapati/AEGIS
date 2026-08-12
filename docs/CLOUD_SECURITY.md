# Cloud Security Architecture

**Status: TERRAFORM DEFINED / NOT YET DEPLOYED**

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
ECS Fargate — AEGIS backend (private subnets)
   ├─► RDS PostgreSQL (private subnets, encrypted, no public access)
   ├─► S3 evidence bucket (block public access, SSE-S3)
   ├─► SQS events queue (SSE enabled)
   └─► Secrets Manager (DATABASE_URL, JWT/SECRET_KEY)

ECS Fargate — correlation worker (private subnets, SQS consume only)
```

## Network boundaries

| Zone | Resources | Exposure |
|------|-----------|----------|
| Public subnets | ALB, NAT | Internet-facing ALB only (443) |
| Private subnets | ECS tasks, RDS | No direct internet ingress |
| Security groups | ALB→ECS:8000, ECS→RDS:5432 | Least privilege |

## IAM (least privilege)

| Role | Purpose | Key permissions |
|------|---------|-----------------|
| ECS execution | Pull images, read secrets | `secretsmanager:GetSecretValue` (specific ARNs) |
| ECS task | Gateway runtime | S3 Put/Get on evidence bucket; SQS SendMessage |
| Worker task | Correlation | SQS Receive/Delete only |

No `Action: "*"` on `Resource: "*"` in module policies.

## Secrets flow

1. RDS master password managed by RDS (`manage_master_user_password`)
2. Connection string stored in Secrets Manager (`aegis/{env}/rds-connection`)
3. JWT secret in Secrets Manager (`aegis/{env}/jwt`)
4. ECS task definitions reference secret ARNs — not plaintext

## Data flows

- **Request path:** Client → WAF → ALB → AEGIS → upstream API
- **Telemetry:** AEGIS → RDS (events, incidents)
- **Evidence (future):** AEGIS → S3 (encrypted objects)
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
- No public S3
- ECS tasks have no SSH access

## Residual risks

- Placeholder ACM certificate in Terraform — must be replaced before deploy
- ECS task image `REPLACE_WITH_ECR_IMAGE` — not wired
- WAF alone insufficient; AEGIS remains application-level enforcement
- Single-region, no DR configuration in skeleton

## Validation

```powershell
cd terraform/environments/dev
terraform fmt -recursive ../..
terraform init -backend=false
terraform validate
```

Do not run `terraform apply` without explicit approval and secret provisioning.
