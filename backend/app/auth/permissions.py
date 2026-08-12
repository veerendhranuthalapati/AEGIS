"""Permission and role definitions.

Permissions use ``<domain>:<action>`` naming. Every security-sensitive
endpoint is guarded server-side with these permissions — never rely on the
frontend for authorization.
"""
from __future__ import annotations

# Domain actions
USERS_READ = "users:read"
USERS_WRITE = "users:write"
POLICIES_READ = "policies:read"
POLICIES_WRITE = "policies:write"
INCIDENTS_READ = "incidents:read"
INCIDENTS_WRITE = "incidents:write"
EVENTS_READ = "events:read"
TOOLS_READ = "tools:read"
TOOLS_WRITE = "tools:write"
MODELS_READ = "models:read"
MODELS_TRAIN = "models:train"
AUDIT_READ = "audit:read"
RESPONSES_EXECUTE = "responses:execute"
APPROVALS_DECIDE = "approvals:decide"
SETTINGS_WRITE = "settings:write"
AGENTS_INVOKE = "agents:invoke"
THREATS_WRITE = "threats:write"

ALL_PERMISSIONS = [
    USERS_READ,
    USERS_WRITE,
    POLICIES_READ,
    POLICIES_WRITE,
    INCIDENTS_READ,
    INCIDENTS_WRITE,
    EVENTS_READ,
    TOOLS_READ,
    TOOLS_WRITE,
    MODELS_READ,
    MODELS_TRAIN,
    AUDIT_READ,
    RESPONSES_EXECUTE,
    APPROVALS_DECIDE,
    SETTINGS_WRITE,
    AGENTS_INVOKE,
    THREATS_WRITE,
]

ROLES: dict[str, dict[str, object]] = {
    "admin": {
        "description": "Full administrative access to all AEGIS controls.",
        "permissions": list(ALL_PERMISSIONS),
    },
    "operator": {
        "description": "Operate the gateway: triage incidents, adjust policies, "
        "execute responses and decide approvals.",
        "permissions": [
            USERS_READ,
            POLICIES_READ,
            POLICIES_WRITE,
            INCIDENTS_READ,
            INCIDENTS_WRITE,
            EVENTS_READ,
            TOOLS_READ,
            MODELS_READ,
            AUDIT_READ,
            RESPONSES_EXECUTE,
            APPROVALS_DECIDE,
            THREATS_WRITE,
            AGENTS_INVOKE,
        ],
    },
    "analyst": {
        "description": "Read-only security analysis plus incident triage.",
        "permissions": [
            USERS_READ,
            POLICIES_READ,
            INCIDENTS_READ,
            INCIDENTS_WRITE,
            EVENTS_READ,
            TOOLS_READ,
            MODELS_READ,
            AUDIT_READ,
            APPROVALS_DECIDE,
        ],
    },
    "user": {
        "description": "Standard authenticated API user.",
        "permissions": [AGENTS_INVOKE],
    },
    "service": {
        "description": "Service account used by protected upstream APIs.",
        "permissions": [AGENTS_INVOKE, EVENTS_READ],
    },
}
