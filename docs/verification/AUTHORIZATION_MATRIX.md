# AEGIS Authorization & BOLA Coverage Matrix

**As of:** 2026-08-13 audit remediation  
**Scope:** Documented enforcement — not universal IDOR protection

---

## Gateway BOLA / ownership (REAL)

| Resource path | Owner field | User A → own | User A → other | Admin/operator |
|---------------|-------------|--------------|----------------|----------------|
| `/api/users/{id}` | `subject_id` vs path id | ALLOW (forward) | BLOCK API-016 pre/post | ALLOW |
| `/api/orders/{id}` | upstream `user_id` / `owner_id` | ALLOW if upstream agrees | BLOCK post-forward API-016 | ALLOW |
| `/api/customers` | collection | BLOCK API-016 (non-privileged) | BLOCK | ALLOW |
| `/api/payments` | collection | BLOCK API-016 | BLOCK | ALLOW |
| `/api/payments/summary` | collection | BLOCK API-016 | BLOCK | ALLOW |
| `/api/public/products` | none (public) | ALLOW | ALLOW | ALLOW |
| `/admin/*` | role gate | BLOCK API-017 | BLOCK | ALLOW |

**Not modeled:** Arbitrary upstream resources without owner keys in response JSON. Those rely on upstream authorization — **documented limitation**.

---

## Tool security (REAL — `/api/tools/invoke`)

| Tool | Roles allowed | Approval | Cross-subject |
|------|---------------|------------|---------------|
| `get_user` | user, operator, admin | No | BLOCK if `resource_owner_id` ≠ actor |
| `get_order` | user, operator, admin | No | BLOCK cross-subject |
| `delete_user` | operator, admin | Yes | Policy + role |
| `execute_payment` | operator, admin | Yes (large amounts) | BLOCK cross-subject |
| Unknown tool | — | — | BLOCK |

**HTTP contract (post-remediation):** `decision=BLOCK` → **HTTP 403** with JSON body. `REQUIRE_APPROVAL` → HTTP 200.

---

## Admin API (permission-gated)

| Endpoint | Permission | user | operator | admin |
|----------|------------|------|----------|-------|
| `/api/users` | `users:read/write` | deny | read | full |
| `/api/incidents` | `incidents:*` | deny | read/write | full |
| `/api/ml/train` | `models:train` | deny | deny | yes |
| `/api/tools/approvals/*/decide` | `approvals:decide` | deny | yes | yes |

Permissions enforced via `require_permission()` on admin routes; tool invoke checks `agents:invoke` inside `ToolSecurityEngine`.

---

## Intentionally globally readable

- `/api/public/*` (mock upstream catalog)
- `/health`, `/ready` (liveness/readiness — no auth)

---

## JWT / session

- Tokens issued via `/api/auth/login`; validated server-side on every protected route.
- **Frontend stores tokens in localStorage** — see [JWT_STORAGE_MIGRATION.md](JWT_STORAGE_MIGRATION.md).
