# Rate Limiting Semantics

**As of:** 2026-08-13

---

## Implementation

- **Storage:** PostgreSQL table `rate_limit_state`
- **Algorithm:** Fixed window, atomic `UPDATE ... RETURNING` + upsert fallback
- **Scopes:**
  - Login: `login:{client_ip}` — default 10/min
  - Gateway: per actor/IP buckets (auth vs anon limits)

---

## Deployment semantics

| Topology | Behavior |
|----------|----------|
| Single uvicorn worker | **Correct** — one process, DB-backed counters |
| Multiple workers, one Postgres | **Mostly correct** — DB atomicity prevents TOCTOU races |
| Multiple regions / read replicas | **NOT SAFE** — no shared low-latency store; windows may diverge |
| Horizontal scale without sticky sessions | Acceptable for demo; production needs **Redis/ElastiCache** or equivalent |

---

## What this is NOT

- Not a distributed token bucket across edge nodes
- Not immune to IP rotation / botnets
- Not a substitute for WAF rate rules (Terraform WAF is **NOT DEPLOYED**)

---

## Forward path

Document **Redis (or DynamoDB counter)** as future infrastructure for production multi-instance deployments. No Redis added in remediation phase (scope control).
