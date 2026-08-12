# Threat Model

## Assets

- User credentials and JWT tokens
- Protected upstream API data
- Security telemetry and incidents
- LLM prompts/outputs (may contain PII)
- Tool invocation arguments (payments, deletes)

## Trust boundaries

1. **Internet clients → Gateway** — untrusted
2. **Gateway → Upstream** — gateway mediates all access
3. **Control plane API → Admin UI** — authenticated operators
4. **Worker → Database** — internal async processing

## STRIDE summary

| Threat | Mitigation | Residual |
|--------|------------|----------|
| Spoofing | JWT auth, bcrypt | Token theft if leaked |
| Tampering | Policy engine blocks malicious requests | Novel attack encodings |
| Repudiation | Audit logs | Client-side actions outside gateway |
| Info disclosure | Output redaction, RBAC on events | Over-permissive roles |
| DoS | Rate limits, WAF (cloud), LLM cost limits | Single-worker exhaustion |
| Elevation | Tool approval, BOLA checks | Incomplete ownership model |

## Attack scenarios (verified in attack lab)

- API enumeration → BLOCK
- BOLA → BLOCK
- SQLi / SSRF / command injection → BLOCK
- Prompt injection / jailbreak → REVIEW/BLOCK (policy)
- Unauthorized tool → BLOCK
- Payment → REQUIRE_APPROVAL
- Incident correlation → CREATE INCIDENT

Run: `attack_lab/scripts/run_all.py`

## Out of scope

- Physical security
- Supply chain of third-party ML libraries (partially covered by CI scanning)
- Production AWS hardening (skeleton only)
