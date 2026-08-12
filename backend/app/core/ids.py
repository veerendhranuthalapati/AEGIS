"""Request/event id generation."""
from __future__ import annotations

import uuid


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:24]}"


def new_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:24]}"


def new_id() -> str:
    return str(uuid.uuid4())
