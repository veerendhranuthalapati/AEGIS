# LLM Security

## Scope

AEGIS scans prompts before upstream LLM calls and inspects responses before returning to clients.

## Detected patterns (heuristic)

- Prompt injection attempts
- Jailbreak / role-play override phrases
- System prompt extraction attempts
- Sensitive data in outputs (PII, secrets)

## Decisions

Policy-driven: ALLOW, BLOCK, REQUIRE_REVIEW, REDACT output fields.

## Upstream

**Status: MOCK / ECHO**

The development stack does not call external LLM APIs. The mock upstream echoes prompts for testing.

## UI behavior

The LLM Security page shows events from `GET /api/events` filtered by `llm_*` types. Raw sensitive prompts are not displayed unnecessarily; backend redaction applies first.

## Cost protection

See [LLM_COST_SECURITY.md](LLM_COST_SECURITY.md) for token limits, concurrency caps, and circuit breaker configuration.
