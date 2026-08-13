# JWT Storage — Limitation & Migration Plan

**Current state (2026-08-13):** **DEFERRED** — documented limitation  
**Risk:** MEDIUM (XSS → token theft from localStorage)

---

## Current architecture

- Login: `POST /api/auth/login` → returns `access_token` + `refresh_token` JSON
- Frontend: Zustand persist → **localStorage** key `aegis-auth`
- API calls: `Authorization: Bearer` header via Axios interceptor
- Backend: Stateless JWT validation + DB token revocation (`access_tokens` table)

---

## Why not changed in remediation phase

Moving to httpOnly cookies requires coordinated backend + frontend + CORS changes:

- Cookie flags (`Secure`, `HttpOnly`, `SameSite`)
- CSRF strategy for cookie-based auth
- Refresh token rotation endpoint hardening
- Vite dev proxy cookie forwarding

A partial migration (e.g. access token still in localStorage) would not materially reduce risk.

---

## Recommended migration (future)

1. **Short-lived access token** in memory only (not persisted)
2. **Refresh token** in httpOnly Secure SameSite=Strict cookie
3. **BFF or gateway** sets cookies; frontend never reads refresh material
4. **CSRF token** for state-changing admin routes if using cookies
5. Remove refresh token from localStorage entirely

---

## Interim mitigations

- Strict CSP on frontend nginx build
- Short access token TTL (already configurable)
- Token revocation on logout (implemented)
- Do not store refresh tokens in localStorage when migration starts
