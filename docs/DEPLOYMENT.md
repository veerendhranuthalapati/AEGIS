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

The backend container runs `alembic upgrade head`, **`python -m app.scripts.seed`** (demo users/policies), then uvicorn. Without seed, login and attack lab will fail.

Backend sets `AEGIS_IN_PROCESS_WORKER=false` so the dedicated `worker` container handles correlation (avoids duplicate workers).

Verify:

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8100/health
# Login: POST http://127.0.0.1:8000/api/auth/login {"username":"admin","password":"Admin@1234"}
```

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

See [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md) (full guide) and [CLOUD_SECURITY.md](CLOUD_SECURITY.md).

## Secrets

Production secrets MUST come from:

- AWS Secrets Manager (cloud)
- Environment variables / `.env` (local only)

Never embed in Terraform source, Dockerfiles, frontend, or Git.

## Health checks

- Backend liveness: `GET /health` (process up — does not probe Postgres)
- Backend readiness: `GET /ready` (returns 503 if database unavailable)
- Metrics: `GET /metrics` (Prometheus)
- Frontend nginx: `GET /`
