"""Tool execution proxy to the upstream mock tool executor."""
from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger("aegis.tool_executor")


class ToolExecutor:
    """Executes an allowed tool call against the protected upstream."""

    def __init__(self, settings=None) -> None:
        self._settings = settings or get_settings()
        self._client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._settings.upstream_base_url,
                timeout=20.0,
            )
        return self._client

    async def execute(self, tool: str, arguments: dict) -> dict[str, Any]:
        client = await self._http()
        try:
            resp = await client.post(
                "/api/tools/execute",
                json={"tool": tool, "arguments": arguments},
            )
            if resp.status_code == 200:
                data = resp.json()
                return {"status": "success", "result": data.get("result")}
            return {
                "status": "error",
                "error": f"executor returned {resp.status_code}",
            }
        except httpx.HTTPError as exc:
            logger.error("tool_executor.error", error=str(exc))
            return {"status": "error", "error": "executor unreachable"}
        finally:
            pass

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
