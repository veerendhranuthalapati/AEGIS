# AEGIS Real LLM Integration

**Status (2026-08-13):**

| Mode | Status |
|------|--------|
| **Mock provider** (`LLM_PROVIDER=mock`) | **VERIFIED** — live Docker stack, attack lab, E2E |
| **Real provider** (`LLM_PROVIDER=real`) | **IMPLEMENTED — NOT LIVE VERIFIED** (no credentials in release environment) |

**Modes:** `MOCK MODE` (default) · `REAL LLM MODE` (opt-in)

AEGIS routes LLM chat traffic through a provider abstraction **behind** the full security pipeline. The model is never reachable directly from clients.

---

## Security flow (unchanged)

```
Client
  ↓
AEGIS Gateway
  ↓
Authentication
  ↓
Deterministic API rules + behavioral stats + ML
  ↓
LLM prompt scanner (+ optional external analyzer)
  ↓
Risk engine
  ↓
Policy engine
  ↓
Decision (BLOCK / REQUIRE_REVIEW → no LLM call)
  ↓
LLM Provider (mock or real)
  ↓
Output inspection + redaction
  ↓
Tool-call authorization (if model emits tools)
  ↓
Client response
```

**BLOCK** and **REQUIRE_REVIEW** decisions do **not** invoke the LLM — reducing attack surface and cost.

---

## Provider architecture

| Component | Path | Role |
|-----------|------|------|
| `LLMProvider` | `backend/app/llm/base.py` | Abstract interface |
| `MockProvider` | `backend/app/llm/mock.py` | Deterministic echo — **CI default** |
| `RealProvider` | `backend/app/llm/real.py` | OpenAI-compatible `/chat/completions` |
| Factory | `backend/app/llm/factory.py` | `init_llm_provider()` at startup |
| Cost controls | `backend/app/llm/cost.py` | Concurrency, session, actor limits |
| Tool inspection | `backend/app/llm/tool_calls.py` | Model tool calls → `ToolSecurityEngine` |

### Operations

- `chat_completion(request)` — primary path
- Tool calls parsed from OpenAI-style responses; **never executed** by the model
- Streaming not implemented (future work)

---

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `mock` | `mock` or `real` |
| `LLM_API_KEY` | empty | Required for `real` mode |
| `LLM_MODEL` | empty | Model name (e.g. `gpt-4o-mini`) |
| `LLM_BASE_URL` | empty | OpenAI-compatible base URL |
| `LLM_ANALYZER_ENABLED` | `false` | Optional security classifier |
| `LLM_ANALYZER_PROVIDER` | `none` | `openai` when analyzer enabled |

Cost / abuse limits (`settings.py`):

- `llm_max_input_tokens`, `llm_max_output_tokens`
- `llm_max_retries`, `llm_timeout_seconds`
- `llm_max_concurrent_requests`
- `llm_max_session_requests`, `llm_max_actor_requests_per_hour`
- `llm_max_tool_call_depth`

### MOCK MODE (default)

```powershell
$env:LLM_PROVIDER = "mock"
# No API key required — deterministic for tests and attack lab
```

### REAL LLM MODE

```powershell
$env:LLM_PROVIDER = "real"
$env:LLM_API_KEY = "<from-secrets-manager-or-env>"
$env:LLM_MODEL = "gpt-4o-mini"
# Optional: $env:LLM_BASE_URL = "https://api.openai.com/v1"
```

Never commit API keys. Production: AWS Secrets Manager → ECS task secret injection.

---

## Secret handling

- API keys read from `LLM_API_KEY` environment variable only
- Never exposed in: frontend, Git, Dockerfile, logs, audit records, incident details, exception messages
- `sanitize_known_secrets()` strips keys from log-safe strings
- Tests: `tests/unit/test_llm_secret_handling.py`

---

## Input security

Before the provider is called:

1. Prompt text extracted from JSON body (`messages` / `prompt`)
2. `LlmScanner` — deterministic rules LLM-001..009
3. PII/secret detection via `find_detections()`
4. Risk aggregation + policy evaluation
5. BLOCK / REQUIRE_REVIEW → **no LLM invocation**

---

## Output security

After the provider returns:

1. Full response body scanned by `scan_output()`
2. PII, API keys, SSN, cards redacted
3. System prompt leakage and dangerous instructions flagged
4. Internal URLs flagged
5. Redacted body returned to client (`x-aegis-redacted: true` when applied)

---

## Tool-call security

If the model returns `tool_calls`:

1. Each call parsed (name + arguments)
2. Evaluated by `ToolSecurityEngine` (same as `/api/tools/invoke`)
3. Unknown tools → **BLOCK**
4. Cross-subject / high-risk → **BLOCK** or **REQUIRE_APPROVAL**
5. Tools are **never executed** from model output — only inspection results returned

---

## Failure handling

| Failure | AEGIS behaviour |
|---------|-----------------|
| LLM unavailable | HTTP 503 JSON error; deterministic security already applied |
| Timeout | 503; scanner/rules still active |
| Rate limit (429) | 429 to client; optional retry inside provider |
| Malformed JSON | 502; no raw provider body leaked |
| Missing API key | 503 in real mode |
| Provider error | Sanitized error — **no API key in message** |

Security enforcement does **not** fail open when the LLM is unavailable.

---

## Testing

| Suite | Purpose | CI |
|-------|---------|-----|
| `tests/unit/test_llm_providers.py` | Mock + real (mock transport) | Yes |
| `tests/unit/test_llm_secret_handling.py` | Key never in errors | Yes |
| `tests/unit/test_llm_upstream_cost.py` | Cost limits | Yes |
| `tests/unit/test_llm_output_security.py` | Output redaction | Yes |
| `tests/unit/test_llm_failure_modes.py` | Provider errors | Yes |
| `tests/unit/test_llm_tool_calls.py` | Tool authorization | Yes |
| `tests/adversarial/test_llm_prompt_adversarial.py` | 12+ injection scenarios | Yes |
| `tests/adversarial/test_llm_output_adversarial.py` | Leaky output cases | Yes |
| `tests/integration/test_llm_real_provider.py` | Real API | **No** — opt-in only |

Run real-provider tests:

```powershell
$env:LLM_REAL_TESTS = "1"
$env:LLM_API_KEY = "<your-key>"
cd backend
.\.venv\Scripts\python.exe -m pytest tests/integration/test_llm_real_provider.py -m real_llm
```

---

## Evidence-based claims

AEGIS **detects and mitigates the tested prompt-injection scenarios** in the deterministic scanner and adversarial test suite. It does **not** claim:

- Secure against all prompt injection
- Zero false positives/negatives
- Production LLM safety certification

The optional external analyzer adds signal only — never sole authority for BLOCK decisions on prompt routes (HIGH scanner findings → REQUIRE_REVIEW).

---

## Remaining limitations

- OpenAI-compatible API shape only (no native Anthropic/Bedrock adapters yet)
- No streaming responses
- Prompt scanner inspects extracted text + raw body — deeply nested JSON attacks need ongoing normalization
- Real-mode output quality depends on the external model; AEGIS redacts but cannot guarantee semantic safety
- Distributed cost limits are per-process (not Redis/global)

See also: [LLM_SECURITY.md](LLM_SECURITY.md), [LLM_COST_SECURITY.md](LLM_COST_SECURITY.md), [LIMITATIONS.md](LIMITATIONS.md).
