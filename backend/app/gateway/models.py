"""Gateway request/response context shared by all detection layers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class RequestContext:
    request_id: str
    timestamp: datetime
    method: str
    path: str
    endpoint: str
    query_string: str | None
    headers: dict[str, str]
    body_text: str | None
    body_json: dict | list | None
    body_bytes: int
    source_ip: str | None
    user_agent: str | None
    device_id: str | None
    actor_id: str | None = None
    actor_username: str | None = None
    actor_role: str | None = None
    actor_subject_id: int | None = None
    actor_permissions: list[str] = field(default_factory=list)
    auth_method: str | None = None
    session_id: str | None = None
    country: str | None = None
    route_config: dict | None = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        *,
        request_id: str,
        method: str,
        path: str,
        endpoint: str,
        query_string: str | None,
        headers: dict[str, str],
        body_text: str | None,
        body_json: dict | list | None,
        source_ip: str | None,
        user_agent: str | None,
        device_id: str | None,
        body_bytes: int = 0,
    ) -> "RequestContext":
        return cls(
            request_id=request_id,
            timestamp=datetime.now(timezone.utc),
            method=method.upper(),
            path=path,
            endpoint=endpoint,
            query_string=query_string,
            headers={k.lower(): v for k, v in headers.items()},
            body_text=body_text,
            body_json=body_json,
            body_bytes=body_bytes,
            source_ip=source_ip,
            user_agent=user_agent,
            device_id=device_id,
        )

    def query_params(self) -> dict[str, str]:
        from urllib.parse import unquote_plus

        out: dict[str, str] = {}
        if self.query_string:
            for pair in self.query_string.split("&"):
                if "=" in pair:
                    key, _, value = pair.partition("=")
                    out[unquote_plus(key)] = unquote_plus(value)
        return out


@dataclass
class UpstreamResponse:
    status_code: int
    body_text: str | None
    body_json: Any | None
    headers: dict[str, str]
    bytes_size: int = 0
    latency_ms: float = 0.0
