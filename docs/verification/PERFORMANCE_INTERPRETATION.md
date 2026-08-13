# Performance Interpretation — Live Verification Run

**Date:** 2026-08-13  
**Evidence:** [`docs/benchmarks/live_verification_2026-08-13.json`](../benchmarks/live_verification_2026-08-13.json)  
**Harness:** `backend/scripts/loadtest.py`

---

## 1. How the benchmark is constructed

| Parameter | Value (live run) |
|-----------|------------------|
| Requests per tier | **50** |
| Concurrent workers (tier 5 only) | **10** |
| Gateway | Docker backend `http://127.0.0.1:8000` |
| Upstream | Docker mock-api `http://127.0.0.1:8100` |
| Serial pace | 0.005 s between requests |
| Path (gateway tiers) | `GET /api/gateway/api/public/products` |
| Path (upstream tier) | Direct upstream equivalent |
| Auth | Rotates seed users (admin, operator, alice, bob, mallory) |
| ML tier | Uses active model if present (no retrain in this 50-req run) |
| LLM tier | `POST /api/gateway/ai/chat` with benign prompt |

**Success criterion:** HTTP **200** only (BLOCK/403 counted as errors in throughput stats).

---

## 2. What happens on each gateway request

The gateway pipeline is **synchronous** per request:

1. JWT authentication
2. Rule + behavioral scans (PostgreSQL aggregation queries for actor stats)
3. ML inference (if model loaded)
4. LLM scanner (LLM tier only)
5. Risk + policy engines
6. **Telemetry write** — security event persisted to PostgreSQL
7. Upstream proxy call (ALLOW path)

The **worker** is separate (`AEGIS_IN_PROCESS_WORKER=false` in Docker compose). Incident correlation runs asynchronously and **does not** block the gateway response path.

Connection pooling: SQLAlchemy async engine with pool to PostgreSQL.

---

## 3. Live results (50 requests)

| Tier | p50 (ms) | p95 (ms) | p99 (ms) | req/s |
|------|----------|----------|----------|-------|
| upstream | 4.25 | 5.35 | 6.74 | 64.15 |
| aegis (serial) | 29.94 | 35.41 | 42.49 | 21.36 |
| aegis_ml (serial) | 31.39 | 37.55 | 38.74 | 21.55 |
| aegis_llm (serial) | 28.84 | 31.47 | 32.10 | 21.68 |
| aegis_concurrent (10 workers) | 185.61 | 513.66 | 525.05 | 41.20 |

### Serial gateway overhead

**p50 overhead ≈ 29.9 − 4.3 ≈ 25.6 ms** on this warm Docker stack with 50 requests.

This is **lower** than the prior 100-request dev benchmark (~215 ms in `docs/benchmarks/run1_noml.json`) because:

- Warm PostgreSQL + connection pool
- Fewer total requests (50 vs 100)
- Different load history (no prior burst rate-limit state)
- Docker network path vs prior local uvicorn runs

**Do not treat 25 ms or 215 ms as production SLA.** Both are local measurements with mock upstream.

---

## 4. Concurrent tier interpretation

The concurrent tier fires **50 requests** with **10 simultaneous workers** against the same gateway path.

Observed:

- **Higher p50** (185 ms) vs serial (30 ms) — connection pool contention, PostgreSQL write lock pressure, upstream serialization
- **Very high p95/p99** (513–525 ms) — tail latency from queueing, not representative steady-state capacity
- **Higher req/s** (41.2) than serial (21.4) — parallelism helps throughput but hurts tail latency

This pattern is **expected** for a single-process uvicorn gateway with synchronous DB telemetry on every ALLOW request. Profiling would likely show:

- Behavioral stats SQL (~dominant in prior analysis)
- Event INSERT latency
- Upstream round-trip under contention

---

## 5. ML and LLM tiers

| Tier | ML enabled | LLM scanner | Delta vs aegis (p50) |
|------|------------|-------------|----------------------|
| aegis | optional/none | no | baseline |
| aegis_ml | yes | no | +1.5 ms (within noise at n=50) |
| aegis_llm | optional | yes | −1.1 ms (within noise; different route) |

At 50 requests, ML/LLM overhead is **not statistically distinguishable** from serial gateway variance. Prior 100-request runs showed ~15 ms ML inference when explicitly trained.

---

## 6. What this does NOT prove

- Production capacity or autoscaling behavior
- Multi-instance ECS performance
- WAF/ALB added latency
- Behavior under attack traffic (rate limits, BLOCK paths)
- Cold-start / migration / seed overhead

---

## 7. Profiling before optimization

Recommended next steps (future work, not this release):

1. `EXPLAIN ANALYZE` on behavioral aggregation queries
2. Separate read replica or cached actor stats for hot paths
3. Batch or async telemetry write (without weakening enforcement)
4. Multiple uvicorn workers + connection pool tuning
5. Load test with ≥1000 requests and stable warm-up period

**No optimization applied in v1.0.0-rc1** — live verification establishes baseline only.
