# AEGIS Architecture

## Overview

AEGIS is a security gateway that inspects API and LLM traffic before forwarding to an upstream application. Enforcement is **synchronous**; incident correlation is **asynchronous**.

---

## Request inspection pipeline (LOCAL — implemented)

```mermaid
flowchart TB
    subgraph client["CLIENT (LOCAL)"]
        C[Browser / API client / AI agent]
    end

    subgraph gateway["AEGIS GATEWAY — REAL (FastAPI :8000)"]
        direction TB
        A1[Authentication — JWT]
        A2[Deterministic API rules]
        A3[Behavioral statistics]
        A4[ML inference — SYNTHETIC-trained models]
        A5[LLM security scanner — heuristics]
        A6[Risk engine]
        A7[Policy engine]
        A8[Decision — ALLOW / WARN / REQUIRE_REVIEW / BLOCK / REQUIRE_APPROVAL]
        A9[Upstream proxy]
        A10[Response redaction]
        A1 --> A2 --> A3 --> A4 --> A5 --> A6 --> A7 --> A8 --> A9 --> A10
    end

    subgraph upstream["UPSTREAM — MOCK in dev"]
        U[Vulnerable mock API :8100]
    end

    C --> A1
    A9 --> U
    A10 --> C
```

**Legend:** REAL = running code · MOCK = deliberately vulnerable test upstream · SYNTHETIC = ML trained on generated data

---

## Async incident path

### LOCAL (what runs today)

```mermaid
flowchart LR
    GW[AEGIS Gateway] -->|persist SecurityEvent| PG[(PostgreSQL — REAL)]
    PG -->|FOR UPDATE SKIP LOCKED poll| W[Correlation Worker — REAL]
    W -->|create/update| INC[Incidents — REAL]
    INC --> UI[SOC Dashboard — REAL React UI]
```

### CLOUD-DESIGNED (Terraform only — not deployed, app not wired)

```mermaid
flowchart LR
    GW2[AEGIS Gateway — ECS] -.->|future publish| SQS[SQS events — DESIGNED]
    SQS -.->|future consume| W2[Worker — ECS]
    W2 -.-> PG2[(RDS PostgreSQL)]
    W2 -.-> INC2[Incidents]
```

Dashed lines indicate **designed but not implemented in application code**. The worker today polls PostgreSQL directly, not SQS.

---

## Full system context

```mermaid
flowchart TB
    subgraph internet["INTERNET"]
        CL[Clients]
    end

    subgraph cloud["AWS — CLOUD-DESIGNED, NOT DEPLOYED"]
        WAF[AWS WAF]
        ALB[ALB HTTPS]
        ECS[ECS Fargate]
        RDS[(RDS PostgreSQL — private)]
        S3[S3 evidence — future app use]
        SM[Secrets Manager]
        CW[CloudWatch]
        IAM[IAM roles]
        WAF --> ALB --> ECS
        ECS --> RDS
        ECS -.-> S3
        ECS --> SM
        ECS --> CW
        IAM -.-> ECS
    end

    subgraph local["LOCAL DEV STACK — REAL"]
        GW[AEGIS Gateway]
        PG[(PostgreSQL :5433)]
        MOCK[mock-api — MOCK upstream]
        FE[React SOC UI]
        GW --> MOCK
        GW --> PG
        FE --> GW
    end

    CL -->|production target| WAF
    CL -->|dev| FE
```

---

## Component status

| Component | Role | Status |
|-----------|------|--------|
| `backend/app/gateway` | Request inspection pipeline | **REAL** |
| `backend/app/api` | Control-plane REST API | **REAL** |
| `backend/app/worker` | Incident correlation (DB poll) | **REAL** |
| `backend/app/ml` | Isolation Forest + Random Forest | **REAL** (SYNTHETIC training) |
| `backend/app/security/llm` | Prompt/output scanning | **REAL** (MOCK upstream echo) |
| `frontend` | SOC dashboard | **REAL** |
| `attack_lab` | 16 adversarial scenarios | **REAL** |
| `attack_lab/targets/mock_api` | Test upstream | **MOCK — never for production** |
| Terraform modules | VPC, ALB, ECS, RDS, S3, SQS, WAF | **CLOUD-DESIGNED — not deployed** |

---

## Decision path vs async path

**Synchronous (must complete before response):** authentication, rules, behavioral stats, ML inference, LLM scan, risk aggregation, policy evaluation, upstream forward, response inspection.

**Asynchronous (does not affect enforcement):** security event persistence, incident correlation, some audit writes.

Security decisions are **never** delegated to the worker or SQS.

---

## Frontend

React + Vite SPA. Dashboard metrics from `/api/analytics/*`, `/api/events`, `/api/incidents`. The UI is an operator console, not a security boundary.

---

## Related docs

- [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md) — cloud topology
- [CLOUD_SECURITY.md](CLOUD_SECURITY.md) — network and IAM
- [THREAT_MODEL.md](THREAT_MODEL.md) — trust boundaries
- [PERFORMANCE.md](PERFORMANCE.md) — measured local overhead
