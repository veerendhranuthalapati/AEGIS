# Release Contents — v1.0.0-rc1

**Date:** 2026-08-13  
**Tag:** `v1.0.0-rc1`

---

## SHIPPED (this release)

- FastAPI gateway (rules, behavior, ML V1, risk, policy)
- LLM provider module — **MockProvider default (VERIFIED)**
- Agent tool registry, authorization, approval workflow
- React SOC frontend
- Attack lab with **strict** scenario expectations
- Bypass regression suite (15 tests)
- Docker Compose stack (postgres, mock-api, backend, worker, frontend)
- `/health` + `/ready` endpoints
- Tool BLOCK → HTTP 403
- ML V1 train-split fix (no test leakage in IF fit)
- Terraform modules (validate/fmt pass)
- CI workflow
- Verification documentation + live evidence JSON

---

## IMPLEMENTED — NOT LIVE VERIFIED

| Component | Path |
|-----------|------|
| Real LLM provider | `backend/app/llm/real.py` |
| Real LLM integration test | `tests/integration/test_llm_real_provider.py` (skipped without credentials) |

---

## OFFLINE EVALUATION ONLY

| Component | Path |
|-----------|------|
| ML V2 pipeline | `backend/app/ml/v2_eval.py`, `traffic_generator.py`, … |
| V2 benchmark JSON | `docs/benchmarks/ml_v2_eval.json` |

Not used for online gateway decisions in this release.

---

## MOCK

- Upstream `mock-api`
- `MockProvider` (default LLM)
- Response automation (`ResponseExecutor(mode="mock")`)

---

## SYNTHETIC

- ML V1 training data
- ML V2 controlled telemetry generator

---

## DESIGNED — NOT DEPLOYED

- AWS / `terraform apply`
- SQS / S3 application code
- Redis distributed rate limiting
- WAF/ALB live rules

---

## EXCLUDED FROM GIT

- Generated attack lab output (regenerated per run)
- `.env`, databases, model artifacts, `node_modules`, `dist/`
- Docker Scout JSON exports (documented in audit; not committed)

---

## Feature freeze

**v1.0.0-rc1** is the signed release candidate. Further changes require a new RC or patch release.
