"""Idempotent seed script for local development.

Creates roles, users, default policies and tool definitions. Passwords are
development defaults and must be overridden in production via environment
variables.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.auth.password import hash_password  # noqa: E402
from app.auth.permissions import ROLES  # noqa: E402
from app.database.session import async_session_factory, dispose_engine  # noqa: E402
from app.models import Role, RolePermission, Tool, User  # noqa: E402

ADMIN_PASSWORD = os.environ.get("AEGIS_ADMIN_PASSWORD", "Admin@1234")

DEFAULT_POLICIES = [
    {
        "name": "block-catastrophic-risk",
        "description": "Fail closed: any request with risk >= 80 is blocked.",
        "priority": 10,
        "enabled": True,
        "when": {"all": [{"field": "risk_score", "op": "gte", "value": 80}]},
        "action": "BLOCK",
        "response_actions": ["BLOCK_REQUEST", "RATE_LIMIT"],
        "message": "Blocked: risk score exceeds critical threshold.",
    },
    {
        "name": "deny-admin-to-non-privileged",
        "description": "Non-admin subjects may not access admin endpoints.",
        "priority": 20,
        "enabled": True,
        "when": {
            "all": [
                {"field": "endpoint", "op": "matches", "value": "^/admin"},
                {"field": "actor.role", "op": "nin", "value": ["admin", "operator"]},
            ]
        },
        "action": "BLOCK",
        "response_actions": ["BLOCK_REQUEST"],
        "message": "Admin endpoints require an elevated role.",
    },
    {
        "name": "review-high-risk-llm",
        "description": "High-risk LLM requests are held for review.",
        "priority": 30,
        "enabled": True,
        "when": {
            "all": [
                {"field": "endpoint", "op": "matches", "value": "^/ai/|/chat"},
                {"field": "risk_level", "op": "in", "value": ["HIGH", "CRITICAL"]},
            ]
        },
        "action": "REQUIRE_REVIEW",
        "response_actions": ["REQUIRE_HUMAN_APPROVAL"],
        "message": "High-risk prompt held for review.",
    },
    {
        "name": "warn-suspicious-api",
        "description": "Elevated-risk API requests trigger a warning header.",
        "priority": 40,
        "enabled": True,
        "when": {
            "all": [
                {"field": "endpoint", "op": "matches", "value": "^/api/"},
                {"field": "risk_level", "op": "in", "value": ["MEDIUM", "HIGH"]},
            ]
        },
        "action": "WARN",
        "response_actions": [],
        "message": "Suspicious API activity detected.",
    },
]

DEFAULT_TOOLS = [
    {
        "name": "get_user",
        "description": "Retrieve a user profile by id.",
        "category": "read",
        "default_allowed_roles": ["user", "operator", "admin"],
        "sensitive": False,
        "requires_approval": False,
    },
    {
        "name": "get_order",
        "description": "Retrieve an order by id.",
        "category": "read",
        "default_allowed_roles": ["user", "operator", "admin"],
        "sensitive": True,
        "requires_approval": False,
    },
    {
        "name": "search_database",
        "description": "Run a restricted database search.",
        "category": "read",
        "default_allowed_roles": ["operator", "admin"],
        "sensitive": True,
        "requires_approval": False,
    },
    {
        "name": "create_ticket",
        "description": "Create a support ticket.",
        "category": "write",
        "default_allowed_roles": ["user", "operator", "admin"],
        "sensitive": False,
        "requires_approval": False,
    },
    {
        "name": "send_email",
        "description": "Send an email to a customer.",
        "category": "write",
        "default_allowed_roles": ["operator", "admin"],
        "sensitive": False,
        "requires_approval": False,
        "approval_threshold_risk": 60,
    },
    {
        "name": "upload_file",
        "description": "Upload a file to shared storage.",
        "category": "write",
        "default_allowed_roles": ["operator", "admin"],
        "sensitive": False,
        "requires_approval": True,
    },
    {
        "name": "delete_user",
        "description": "Permanently delete a user account.",
        "category": "destructive",
        "default_allowed_roles": ["operator", "admin"],
        "sensitive": False,
        "requires_approval": True,
    },
    {
        "name": "execute_payment",
        "description": "Execute a customer payment.",
        "category": "payment",
        "default_allowed_roles": ["operator", "admin"],
        "sensitive": True,
        "requires_approval": True,
        "approval_threshold_risk": 40,
    },
    {
        "name": "grant_admin",
        "description": "Grant admin privileges to a user.",
        "category": "destructive",
        "default_allowed_roles": ["admin"],
        "sensitive": True,
        "requires_approval": True,
    },
]

DEFAULT_USERS = [
    {"username": "admin", "email": "admin@aegis.local", "password": ADMIN_PASSWORD, "role": "admin", "subject_id": None, "full_name": "AEGIS Administrator"},
    {"username": "operator", "email": "operator@aegis.local", "password": os.environ.get("AEGIS_OPERATOR_PASSWORD", "Operator@1234"), "role": "operator", "subject_id": None, "full_name": "Security Operator"},
    {"username": "alice", "email": "alice@example.com", "password": "Alice@1234", "role": "user", "subject_id": 1, "full_name": "Alice Anderson"},
    {"username": "bob", "email": "bob@example.com", "password": "Bob@1234", "role": "user", "subject_id": 2, "full_name": "Bob Baker"},
    {"username": "mallory", "email": "mallory@example.com", "password": "Mallory@1234", "role": "user", "subject_id": 3, "full_name": "Mallory Mason"},
]


async def seed(session: AsyncSession) -> None:
    role_ids: dict[str, str] = {}

    for role_name, definition in ROLES.items():
        result = await session.execute(select(Role).where(Role.name == role_name))
        role = result.scalar_one_or_none()
        if role is None:
            role = Role(name=role_name, description=str(definition["description"]))
            session.add(role)
            await session.flush()
        role_ids[role_name] = role.id
        perms = definition["permissions"]
        existing = await session.execute(
            select(RolePermission).where(RolePermission.role_id == role.id)
        )
        existing_perms = {p.permission for p in existing.scalars().all()}
        for permission in perms:
            if permission not in existing_perms:
                session.add(
                    RolePermission(role_id=role.id, permission=permission)
                )

    for user_data in DEFAULT_USERS:
        result = await session.execute(
            select(User).where(User.username == user_data["username"])
        )
        if result.scalar_one_or_none():
            continue
        session.add(
            User(
                username=user_data["username"],
                email=user_data["email"],
                password_hash=hash_password(user_data["password"]),
                full_name=user_data["full_name"],
                subject_id=user_data["subject_id"],
                role_id=role_ids[user_data["role"]],
                is_active=True,
            )
        )

    for tool_data in DEFAULT_TOOLS:
        result = await session.execute(
            select(Tool).where(Tool.name == tool_data["name"])
        )
        if result.scalar_one_or_none():
            continue
        session.add(Tool(**tool_data))

    for policy_data in DEFAULT_POLICIES:
        from app.models import Policy

        result = await session.execute(
            select(Policy).where(Policy.name == policy_data["name"])
        )
        if result.scalar_one_or_none():
            continue
        session.add(
            Policy(
                name=policy_data["name"],
                description=policy_data["description"],
                priority=policy_data["priority"],
                enabled=policy_data["enabled"],
                when=policy_data["when"],
                action=policy_data["action"],
                response_actions=policy_data["response_actions"],
                message=policy_data["message"],
                version=1,
            )
        )

    await session.commit()


async def main() -> None:
    async with async_session_factory() as session:
        await seed(session)
    await dispose_engine()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
