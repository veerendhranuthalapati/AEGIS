"""Password hashing with bcrypt."""
from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    if not password or len(password) > 1024:
        raise ValueError("password must be 1..1024 characters")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except ValueError:
        return False
