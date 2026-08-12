# AEGIS Architecture

## Overview

```
Client / Agent
      │
      ▼
┌─────────────────────────────────────┐
│  AEGIS Gateway (:8000)              │
│  ├─ Authentication (JWT)            │
│  ├─ API security rules              │
│  ├─ Behavioral statistics           │
│  ├─ ML anomaly detection            │
│  ├─ LLM prompt scanner              │
│  ├─ Agent/tool authorization        │
│  ├─ Risk engine                     │
│  ├─ Policy engine                   │
│  ├─ Decision (ALLOW/BLOCK/REVIEW)   │
│  ├─ Upstream proxy                  │
│  ├─ Response redaction              │
│  └─ Security event persistence      │
└─────────────────────────────────────┘
      │
      ▼
Protected upstream API (:8100 mock in dev)

Async path:
SecurityEvent → Correlation Worker → Incident
```

## Components

| Component | Role | Status |
|-----------|------|--------|
| `backend/app/gateway` | Request inspection pipeline | REAL |
| `backend/app/api` | Control-plane REST API | REAL |
| `backend/app/worker` | Incident correlation | REAL |
| `backend/app/ml` | Isolation Forest / Random Forest | REAL (SYNTHETIC training data) |
| `backend/app/llm` | Prompt/output scanning | REAL (MOCK upstream) |
| `frontend` | SOC dashboard | REAL |
| `attack_lab` | Adversarial test scenarios | REAL |

## Decision path vs async path

**Synchronous (must complete before response):** authentication, rules, behavioral stats, ML inference, LLM scan, risk aggregation, policy evaluation, upstream forward, response inspection.

**Asynchronous (does not affect enforcement):** security event persistence batching, incident correlation, audit log writes where fire-and-forget.

Security decisions are never delegated to the worker.

## Frontend

React + Vite SPA. All dashboard metrics come from `/api/analytics/*`, `/api/events`, `/api/incidents`. The UI is not a security boundary.

## Cloud (planned)

Terraform defines VPC, ALB, ECS/Fargate, RDS PostgreSQL (private), S3 evidence, SQS events, WAF, IAM least-privilege roles, CloudWatch alarms. **NOT YET DEPLOYED.**

See [CLOUD_SECURITY.md](CLOUD_SECURITY.md).
