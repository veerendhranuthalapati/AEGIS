# Development Guide

## Prerequisites

- Python 3.13
- Node.js 20+
- Docker Desktop (PostgreSQL + mock-api)
- Windows PowerShell (primary dev platform)

## Environment variables

| Variable | Example | Required |
|----------|---------|----------|
| `DATABASE_URL` | `postgresql+asyncpg://aegis:aegis@127.0.0.1:5433/aegis` | Yes |
| `SECRET_KEY` | strong random string | Yes |
| `UPSTREAM_BASE_URL` | `http://127.0.0.1:8100` | Yes |
| `ENVIRONMENT` | `development` | No |

Never commit `.env` files.

## Services

| Service | Port | Command |
|---------|------|---------|
| PostgreSQL | 5433 | `docker compose up -d postgres` |
| Mock upstream | 8100 | `docker compose up -d mock-api` |
| Backend | 8000 | `uvicorn app.main:app --host 127.0.0.1 --port 8000` |
| Worker | — | `python -m app.worker.main` |
| Frontend | 5173 | `npm run dev` (proxies `/api` → :8000) |

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m ruff check app tests

cd ..\frontend
npm test
npm run build

cd ..\attack_lab\scripts
..\..\backend\.venv\Scripts\python.exe run_all.py
```

## API documentation

With backend running: http://127.0.0.1:8000/docs (OpenAPI)

## Frontend structure

```
frontend/src/
  api/          Axios client + endpoint wrappers
  pages/        SOC views (dashboard, incidents, …)
  layouts/      Sidebar + protected shell
  stores/       Zustand auth state
  types/        Backend schema types
```
