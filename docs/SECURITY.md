# Security Controls

## Threat model

See [THREAT_MODEL.md](THREAT_MODEL.md) for assets, trust boundaries, STRIDE summary, and verified attack scenarios.

## Trust boundaries

1. **Untrusted clients → Gateway (`/api/gateway/*`)** — all enforcement occurs here before upstream forward.
2. **Gateway → Upstream (mock/real API)** — mediated; original request bytes are not rewritten for inspection normalization.
3. **Control-plane API → SOC UI** — authenticated operators; UI is not a security boundary.
4. **Worker → PostgreSQL** — internal async correlation and ML training metadata.

## Authentication

- JWT access + refresh tokens (HS256, configurable secret)
- bcrypt password hashing
- Account lockout after failed attempts
- Login rate limiting (per IP; respects `X-Forwarded-For` when trusted)

## Authorization

- RBAC: admin, operator, analyst, user
- Permission checks on control-plane endpoints
- Tool invocation subject/resource ownership checks
- Approval workflow for high-risk tools (e.g. payments)

## API protection

Deterministic rules (first pipeline layer):

- SQL injection — including URL/form encoding normalization for **inspection only** (`decode_for_inspection`, bounded rounds)
- SSRF — private IPs, metadata endpoints, decimal/hex IP forms, rebinding domains
- Path traversal — encoded `../` variants
- Command injection — shell metacharacters and `${IFS}`-style evasion
- BOLA / IDOR — path and query ownership checks on known resource patterns
- Admin endpoint probing — non-privileged access to `/admin`
- HTTP smuggling indicators, oversized bodies, scanner user-agents

Hard-block rule IDs fail closed at the gateway regardless of policy leniency.

## LLM protection

- Prompt injection, jailbreak, system-prompt extraction heuristics on LLM routes
- Optional external analyzer (disabled by default; requires explicit API key)
- Output scanning and PII/secret redaction on sensitive routes
- Upstream LLM: **MOCK / ECHO** in default stack

## Tool / agent security

- Tool registry with role-based allow lists
- Risk-scored invocations; `REQUIRE_APPROVAL` for sensitive operations (payments)
- Unauthorized or cross-subject tool calls blocked

## Redaction

- Request/response text redaction for logs and persisted query strings
- Upstream sensitive fields redacted on configured routes

## Logging & audit

- Structured logging (structlog)
- Security events and API request telemetry persisted to PostgreSQL
- Audit log for authentication and policy/approval actions

## Secrets

- No secrets committed; `.env` gitignored; use `.env.example` as template
- Production requires strong `SECRET_KEY` and database credentials via environment/Secrets Manager (Terraform design)
- CI runs Bandit and detect-secrets (see `.github/workflows/ci.yml`)

## Rate limiting

- Gateway per-actor/IP rate limits
- Login endpoint rate limits and lockout
- Attack-lab verifies brute-force scenarios

## Incident response

- Security events correlated into incidents by async worker
- SOC dashboard surfaces events, incidents, threats, and response actions
- Block/review/redact decisions recorded with request IDs for traceability

## ML detection

- Isolation Forest + Random Forest on behavioral features
- **Dataset: SYNTHETIC** — see [ML_EVALUATION.md](ML_EVALUATION.md)

## Frontend security note

The React SOC UI is **not** a security boundary. All enforcement is server-side. Hidden routes do not protect privileged operations.

## Known limitations

- Heuristic detectors require ongoing normalization; novel encodings may bypass until covered
- BOLA checks limited to known ownership semantics
- ML trained on synthetic data with trivial separation
- AWS deployment: **Terraform defined, not deployed**

See [BACKEND_SECURITY_HARDENING.md](BACKEND_SECURITY_HARDENING.md) for recent hardening work.
