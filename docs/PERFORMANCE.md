# AEGIS Performance Benchmark

Date: 2026-08-12
Deployment: local dev stack (Windows 10, Docker Desktop)
Gateway: `uvicorn app.main:app` single worker, Python 3.13, venv `backend/.venv`
Database: PostgreSQL 16 (docker, port 5433)
Upstream: mock-api (FastAPI, port 8100) — deliberately vulnerable test upstream

## Method

- Tool: `backend/scripts/loadtest.py` (see `python scripts/loadtest.py --help`).
- Actor pool: 5 seed users (admin, operator, alice, bob, mallory) + 25 synthetic
  `loadtest_u1..u25` users (subject_id 1001+). Requests rotate across all actors so
  a single actor does not trip behavioral rate-abuse defenses during the
  steady-state (ALLOW path) measurements.
- Path: `GET /api/gateway/api/public/products` — a benign, non-ownership-checked,
  non-output-inspected upstream route; exercises the full inspection pipeline.
- LLM tier: `POST /api/gateway/ai/chat` (prompt route; LLM scanner runs).
- Per tier: 100 requests. Serial tiers use 5ms pacing. Concurrent tier: 20 workers.
- Warm-up: 10 requests before measuring. Telemetry was reset before each run.
- Two runs: **run 1** with no ML model active; **run 2** with a freshly trained
  model (`aegis-3 v3`, 5000 synthetic samples). JSON artifacts:
  `docs/benchmarks/run1_noml.json`, `docs/benchmarks/run2_ml.json`.

## Results

| tier | run | success | mean | p50 | p90 | p99 | max | req/s |
|---|---|---|---|---|---|---|---|---|
| upstream (no AEGIS) | 1 | 100% | 4.67ms | 4.60 | 5.27 | 5.90 | 6.30 | 64.4 |
| upstream (no AEGIS) | 2 | 100% | 3.77ms | 3.69 | 4.35 | 4.64 | 5.77 | 64.2 |
| aegis (no model) | 1 | 100% | 241.45ms | 238.79 | 264.67 | 281.25 | 347.05 | 3.9 |
| aegis | 2 | 100% | 218.97ms | 215.34 | 250.06 | 267.41 | 318.68 | 4.3 |
| aegis_ml (model active) | 2 | 100% | 218.29ms | 215.70 | 243.30 | 268.69 | 375.39 | 4.3 |
| aegis_llm (prompt route) | 1 | 100% | 224.31ms | 220.44 | 257.24 | 283.72 | 312.87 | 4.2 |
| aegis_llm (prompt route) | 2 | 100% | 220.00ms | 217.91 | 251.33 | 263.08 | 316.08 | 4.3 |
| aegis_concurrent (20w) | 1 | 100% | 4363.02ms | 4144.69 | 6707.00 | 7377.48 | 7593.90 | 4.5 |
| aegis_concurrent (20w) | 2 | 100% | 4054.32ms | 4047.02 | 5832.01 | 6923.43 | 7171.96 | 4.7 |

Latency is per-request wall time measured client-side. `req/s` for the concurrent
tier is the aggregate wall-clock throughput of the 100-request batch.

## Analysis

### Gateway overhead vs upstream

The AEGIS gateway adds ~214ms over the raw upstream (4ms) per request — the
overhead of the full inspection pipeline: behavioral telemetry aggregation,
deterministic rules, ML anomaly detection, risk aggregation, policy evaluation,
forwarding, and telemetry persistence.

### Where the time goes (serial path, instrumented components)

| phase | mean | notes |
|---|---|---|
| `stats` (collect_request_stats) | ~110ms | 9 sequential aggregate SQL queries per request |
| `rate_limit` | ~15ms | sliding-window counter query |
| `ml` | ~15ms | model lookup + inference (negligible when unavailable) |
| `risk` | ~15ms | risk aggregation + attack-history query |
| `policy` | ~15ms | enabled-policy load + tree evaluation |
| `forward` | 5ms | upstream HTTP (after fix; was ~600ms) |
| `persist` | ~7ms | telemetry INSERT + commit |
| `resolve_actor` | ~7ms | token validation + role load |

Aggregate means on `/metrics` skew much higher because the concurrent-tier
requests (which queue on the single worker and DB pool) inflate every phase.

### Findings

**F1 — Gateway made a fresh TCP connection per request and hit `localhost`
(IPv6-first) — fixed.** `GatewayService` created a new `httpx.AsyncClient` per
request (new connection every time), and `upstream_base_url` defaulted to
`http://localhost:8100`. On Windows, `localhost` resolves to `::1` first; the
mock binds IPv4 only, so every new connection paid the IPv6→IPv4 fallback
(~280ms+) plus connection setup (~300ms more under load). Measured effect:
`forward` phase ~600ms, total serial ~950ms. Fix (merged):
`backend/app/gateway/service.py` shares one process-wide `httpx.AsyncClient`
(connections pooled/reused), and `backend/app/config/settings.py` defaults
`upstream_base_url` to `http://127.0.0.1:8100`. Result: total serial ~240ms
(**4x improvement**); `forward` ~5ms. Tests: 100/100 pass, ruff clean.

**F2 — Behavioral defenses engage on burst load by design.** The first benchmark
attempt produced 0% success on every gateway tier. Root cause was a
methodology bug plus a real defense response:
1. The benchmark path `/api/public/products` did not exist upstream (the mock
   only had `/public/products`), so ALLOWed requests forwarded into a 404.
2. 30+ 404s from one source IP within 5 minutes tripped **API-015 endpoint
   enumeration** (HIGH), which raised every subsequent request to
   REQUIRE_REVIEW (202), which the harness counted as failure — a self-sustaining
   cascade until the window aged out.
A benchmark that hammers one IP with erroring traffic will engage the same
defenses; that is the system working as designed. Fix: the mock now exposes
`/api/public/products`, and the harness uses only benign 200 paths.
Also observed earlier: a 200-request burst from a single actor tripped
**API-013 rate abuse** (HIGH at ratio ≥20, MEDIUM at ≥8) → CRITICAL BLOCK
(risk 76.6), and load-test users hitting another user's `/api/orders/101` were
correctly blocked by the post-forward BOLA check (~1.2s per blocked request).

**F3 — Throughput ceiling: ~4–5 req/s per worker under 20-way concurrency.**
The concurrent tier completed at 100% success but aggregate throughput (4.5–4.7
req/s) barely exceeds the serial rate (4.2 req/s); effective parallelism capped
at ~5x despite 20 concurrent clients. Cause: single uvicorn worker + a hot path
that issues ~15 sequential DB round-trips per request against a 10-connection
pool. Concurrent clients serialize on DB connection checkout. This is a
scaling property of the architecture, not a defect: production should run
multiple workers (P4 Docker hardening) and consider consolidating the
`collect_request_stats` aggregates into fewer queries (documented below).

**F4 — ML inference and LLM scanning are negligible.** With the model active
(aegis-3 v3), `aegis_ml` (218.3ms) ≈ `aegis` (219.0ms); the in-process sklearn
inference adds ~0.1ms. The prompt route (`aegis_llm`, ~220ms) costs the same —
the deterministic LLM scanner and (unconfigured) external analyzer add nothing
measurable. Only the DB-backed phases dominate.

**F5 — Login rate limit blocks benchmark user-provisioning.** `login_rate_limit_per_min`
defaults to 10/min per source IP. With 30 actors logging in at once, the harness
hit HTTP 429s and ran with only 8 tokens. Benchmarks must set
`LOGIN_RATE_LIMIT_PER_MIN=500` when starting the server. Note the settings class
uses **no env prefix**: the variable is `LOGIN_RATE_LIMIT_PER_MIN`, not
`AEGIS_LOGIN_RATE_LIMIT_PER_MIN`.

## Recommendations

1. **(P4, config)** Run multiple uvicorn/gunicorn workers behind a load balancer
   to lift the per-worker throughput ceiling (F3).
2. **(future)** Consolidate the 9 `collect_request_stats` queries into 1–3
   batched aggregate queries (or a maintained rollup table). This would cut the
   largest single cost (~110ms/request) and is the highest-leverage follow-up.
   Kept out of scope here to avoid changing security-critical logic untested.
3. **(future)** Re-verify with a profiler under a real Postgres placement; the
   dockerized Postgres round-trips (~1–8ms) are the floor for the DB-heavy path.
4. Keep the shared outbound client (F1) — it also removes socket churn under
   concurrency, which materially helped the concurrent tier reach 100% success.

## Reproduction

```bash
# start the backend with a relaxed login limit
LOGIN_RATE_LIMIT_PER_MIN=500 python -m uvicorn app.main:app --port 8000
# run 1: no ML model
python scripts/reset_telemetry.py
python scripts/loadtest.py --requests 100 --concurrency 20 --spawn-users 25 \
    --pace 0.005 --json ../docs/benchmarks/run1_noml.json
# run 2: train a fresh model, then measure
python scripts/reset_telemetry.py
python scripts/loadtest.py --requests 100 --concurrency 20 --spawn-users 25 \
    --pace 0.005 --train-ml --ml-train-size 5000 --json ../docs/benchmarks/run2_ml.json
```
