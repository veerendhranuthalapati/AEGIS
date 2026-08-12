# LLM Cost-Abuse Defense

Scope: the optional external LLM security analyzer (`backend/app/security/llm/analyzer.py`).
Document version: 2026-08-12.

## Threat model

When enabled, the gateway can call an external (paid) LLM provider to add a
contextual classification signal on high-risk prompt traffic. That external
call costs money per token. An attacker that can reach prompt routes can try
to drive unbounded spend:

- **Volume abuse** — flood the analyzer with high-risk prompts so every one
  triggers an external call.
- **Prompt-size abuse** — submit maximum-length prompts to inflate prompt
  tokens (and thus cost) per call.
- **Long-output abuse** — craft prompts that coax the classifier into long
  completions.
- **Distributed abuse** — rotate across many gateway accounts/IPs to bypass
  a single global limit.

The analyzer is **never authoritative** and is an optional enhancement only.
Failing closed to the deterministic scanner must never be worse than having
no external signal.

## Controls (enforced process-wide)

The analyzer runs as a **process-wide singleton**
(`init_llm_analyzer` / `get_shared_analyzer` in lifespan), so all cost state
persists across requests. Previously it was instantiated per request, which
silently defeated the rate limit and circuit breaker.

| control | setting | default | effect |
|---|---|---|---|
| Disabled by default | `llm_analyzer_enabled` | `false` | No external calls unless an operator opts in with a key. |
| Global rate limit (fail-fast) | `llm_max_calls_per_minute` | `20` | Shared token bucket; when empty, requests fall back to the deterministic scanner immediately (no request-blocking sleeps). |
| Circuit breaker | (threshold 5 / cooldown 60s) | — | After 5 consecutive failures the external path trips open for 60s. |
| Prompt-size cap | `llm_max_prompt_chars` | `12000` | Prompt truncated before the external call. |
| Output cap | `llm_max_tokens` | `512` | `max_tokens` sent to the provider bounds completion cost per call. |
| Request timeout | `llm_timeout_seconds` | `15` | Bounded call duration. |
| Daily global budget (USD) | `llm_daily_budget_usd` | `10.00` | When today's estimated spend reaches the cap, external calls stop until UTC midnight. |
| Per-actor budget (USD) | `llm_actor_budget_usd` | `1.00` | Per-actor (or source-IP, when unauthenticated) cap stops a single abuser from exhausting the daily budget. |
| Pricing estimate | `llm_price_per_1k_prompt_tokens` / `llm_price_per_1k_completion_tokens` | `0.03` / `0.06` | Converts reported token usage to USD for the budget caps and the metric. |

### Enforcement order (per request)

1. Empty prompt → free, no call.
2. Disabled / no key → deterministic fallback.
3. **Budget exceeded** (daily or per-actor) → deterministic fallback, outcome `budget`.
4. Rate bucket empty → deterministic fallback, outcome `rate_limited` (non-blocking).
5. Circuit open → deterministic fallback, outcome `circuit_open`.
6. External call (bounded by timeout, char cap, `max_tokens`).
7. Success → token usage estimated to USD, added to today's + actor's spend,
   and published to the `aegis_llm_est_cost_usd` gauge.

### Known overshoot

Cost is only known after a call completes, so the single call that crosses a
budget cap completes before enforcement (worst case one `max_tokens` call per
cap per day). This is deliberate: pre-approval of spend would require
predicting token usage. The daily global cap bounds total exposure, and the
per-actor cap bounds the per-attacker share.

## Observability

- `aegis_llm_requests_total{used_llm, outcome}` — outcomes include
  `budget`, `rate_limited`, `circuit_open`, `http_error`, `timeout`, `error`,
  `success`, `fallback`, `empty`.
- `aegis_llm_tokens{kind=prompt|completion}` — token usage histogram.
- `aegis_llm_latency_seconds` — external-call latency.
- `aegis_llm_est_cost_usd` — process-wide cumulative estimated spend.
- `structlog` warnings on `budget_exceeded` / `circuit_open` / provider errors.

Recommended alerting: spend growth rate and daily budget headroom; a sudden
jump in `rate_limited` or `budget` outcomes indicates a cost-abuse attempt or
misconfigured thresholds.

## Operational guidance

- Keep `llm_analyzer_enabled=false` in production until a real API key is
  provisioned through a secrets manager (never an env var in plaintext).
- Set pricing values to the deployed model's list price so the USD budget is
  accurate.
- Alert at ~80% of `llm_daily_budget_usd` rather than only at 100%.
- The deterministic scanner (`backend/app/security/llm/scanner.py`) is always
  the floor: all gateway decisions remain intact even with the external
  analyzer fully unavailable.
