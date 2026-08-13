# AEGIS v1.0.0-rc1 — Release Notes

**Date:** 2026-08-13  
**Tag:** `v1.0.0-rc1`  
**Classification:** **PRODUCTION-ORIENTED PROTOTYPE**

---

## Highlights

- Unified API + LLM + agent tool security gateway with layered detection
- Strict attack-lab assertions (16 scenarios) with rule-ID verification
- Live-verified Docker Compose stack (postgres, mock-api, backend, worker, frontend)
- SOC React dashboard with real backend integration
- Human approval workflow with duplicate-decision protection (HTTP 409)
- Incident correlation worker with MITRE-tagged events
- Terraform AWS architecture defined (not deployed)

---

## Security capabilities

| Capability | Status |
|------------|--------|
| Rule-based API detection (SQLi, SSRF, traversal, cmd inj, BOLA modeled routes) | **VERIFIED** |
| LLM prompt scanner (injection, jailbreak, extraction) | **VERIFIED** (mock provider) |
| Agent tool authorization + cross-subject checks | **VERIFIED** |
| Approval workflow | **VERIFIED** |
| Login rate limiting (PostgreSQL) | **VERIFIED** |
| Output redaction | **VERIFIED** |
| Behavioral + ML V1 scoring | **VERIFIED** (synthetic training data) |

---

## Verification

| Suite | Result |
|-------|--------|
| pytest | 224 pass, 1 skipped, 225 collected |
| Attack lab (strict) | 16/16 |
| Bypass suite | 15/15 |
| E2E | PASS |
| Frontend vitest + build | PASS |
| Terraform validate/fmt | PASS |
| Live Docker stack | PASS |

Evidence: [FINAL_LIVE_SECURITY_VERIFICATION.md](FINAL_LIVE_SECURITY_VERIFICATION.md)

---

## Known limitations

- **Not production-ready** — heuristic detection, synthetic ML, local throughput only
- **AWS not deployed** — Terraform is design-only
- **SQS/S3 not in application code** — worker polls PostgreSQL
- **JWT in localStorage** — XSS risk documented; migration plan deferred
- **BOLA partial** — modeled routes only
- **Rate limiting** — PostgreSQL single-store, not distributed
- **Browser visual QA** — NOT VERIFIED (HTTP smoke only)

---

## Deployment status

| Target | Status |
|--------|--------|
| Docker Compose (local) | **VERIFIED** |
| AWS ECS/RDS/WAF | **NOT DEPLOYED** |
| `terraform apply` | **NOT RUN** |

---

## Docker security status

Scanned 2026-08-13 with Docker Scout. See [FINAL_RELEASE_AUDIT.md](FINAL_RELEASE_AUDIT.md) § Docker.

- **backend/worker:** base-image perl/openssl findings; fixable msgpack HIGH in image (1.1.2)
- **frontend runtime:** nginx:1.27-alpine CVEs (build-stage node image not in runtime)
- **mock-api:** non-root user added in rc1; perl base-image CVEs remain

---

## Real LLM status

| Provider | Status |
|----------|--------|
| Mock | **VERIFIED** (default) |
| Real (OpenAI-compatible) | **IMPLEMENTED — NOT LIVE VERIFIED** |

No API keys in repository. Default remains `LLM_PROVIDER=mock`.

---

## ML status

| Component | Status |
|-----------|--------|
| ML V1 (online Isolation Forest + RF) | **SHIPPED** — synthetic data; train-split fix applied |
| ML V2 evaluation pipeline | **OFFLINE ONLY** — not online detection |

---

## Performance

Live Docker benchmark (50 requests): ~26 ms p50 serial gateway overhead vs ~4 ms upstream.

**Not production capacity.** See [PERFORMANCE_INTERPRETATION.md](PERFORMANCE_INTERPRETATION.md).

---

## Future work

- Real LLM live verification with credentials in secure environment
- Browser E2E (Playwright)
- JWT httpOnly cookie migration
- Redis-backed distributed rate limiting
- Base image CVE remediation (msgpack pin, alpine/nginx refresh)
- AWS deployment rehearsal (no apply without explicit approval)
- SQS application integration

---

## Upgrade from HEAD `0bb2659`

This release candidate includes audit remediation, strict attack-lab assertions, `/ready` endpoint, tool BLOCK→403, ML V1 leakage fix, LLM provider module (mock default), and full verification documentation.
