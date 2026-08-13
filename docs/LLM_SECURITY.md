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

**Default: MOCK MODE** (`LLM_PROVIDER=mock`) — deterministic `MockProvider`, no external API.

**Optional: REAL LLM MODE** (`LLM_PROVIDER=real` + `LLM_API_KEY`) — OpenAI-compatible provider behind the same security pipeline.

See [REAL_LLM_INTEGRATION.md](REAL_LLM_INTEGRATION.md) for architecture, configuration, and testing.

## UI behavior

The LLM Security page shows events from `GET /api/events` filtered by `llm_*` types. Raw sensitive prompts are not displayed unnecessarily; backend redaction applies first.

## Cost protection

See [LLM_COST_SECURITY.md](LLM_COST_SECURITY.md) for token limits, concurrency caps, and circuit breaker configuration.
