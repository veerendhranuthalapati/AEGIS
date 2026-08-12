"""E2E telemetry reset (invoked in a fresh interpreter)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
# Force E2E database target (avoid stale env / localhost IPv6 issues on Windows).
os.environ["DATABASE_URL"] = "postgresql+asyncpg://aegis:aegis@127.0.0.1:5433/aegis"

from app.config import get_settings

get_settings.cache_clear()

from app.database import async_session_factory, dispose_engine
from app.models import (
    Approval,
    ApiRequest,
    AuditLog,
    Incident,
    IpBlock,
    ModelPrediction,
    ModelVersion,
    RateLimitState,
    SecurityEvent,
    ToolInvocation,
)


async def _clear() -> None:
    async with async_session_factory() as session:
        for model in (
            Approval,
            ModelPrediction,
            ToolInvocation,
            SecurityEvent,
            Incident,
            RateLimitState,
            IpBlock,
            ApiRequest,
            ModelVersion,
            AuditLog,
        ):
            await session.execute(model.__table__.delete())
        await session.commit()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_clear())
