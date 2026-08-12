# Deployment Guide

## Local (Docker Compose)

```powershell
$env:AEGIS_SECRET_KEY = "change-me-strong"
$env:AEGIS_POSTGRES_PASSWORD = "change-me-strong"
docker compose up -d
# Optional frontend:
docker compose --profile frontend up -d
```

Services: `postgres`, `mock-api`, `backend`, `worker`. Frontend on `:3000` (profile `frontend`).

## Docker images

- `backend/Dockerfile` — multi-stage, non-root, health check
- `frontend/Dockerfile` — Vite build + nginx (non-root, port 8080)
- `attack_lab/targets/mock_api` — **test only, deliberately vulnerable**

## AWS (Terraform)

**Status: TERRAFORM DEFINED / NOT YET DEPLOYED**

```powershell
cd terraform/environments/dev
terraform init
terraform validate
# Do NOT apply without review
```

Target topology: WAF → ALB → ECS/Fargate → AEGIS | RDS (private) | S3 | SQS | Secrets Manager | CloudWatch.

See [CLOUD_SECURITY.md](CLOUD_SECURITY.md).

## Secrets

Production secrets MUST come from:

- AWS Secrets Manager (cloud)
- Environment variables / `.env` (local only)

Never embed in Terraform source, Dockerfiles, frontend, or Git.

## Health checks

- Backend: `GET /health`
- Metrics: `GET /metrics` (Prometheus)
- Frontend nginx: `GET /`
