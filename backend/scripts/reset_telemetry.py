"""Reset telemetry tables for a clean benchmark baseline.

Deletes only test/telemetry rows (requests, events, incidents, model
predictions) so behavioral statistics and the worker queue start empty.
Seed users, roles, tools and policies are left untouched.

Optional flag ``--deprecate-models`` also marks every model version
``deprecated`` so the ML tier can be benchmarked as "no active model".

Usage:
    python scripts/reset_telemetry.py [--deprecate-models]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.database.session import async_session_factory, dispose_engine  # noqa: E402
from app.models import (  # noqa: E402
    ApiRequest,
    Incident,
    ModelPrediction,
    SecurityEvent,
)

_TABLES = (ModelPrediction, ApiRequest, SecurityEvent, Incident)


async def main(deprecate_models: bool) -> None:
    try:
        async with async_session_factory() as session:
            for model in _TABLES:
                await session.execute(text(f"DELETE FROM {model.__tablename__}"))
            if deprecate_models:
                await session.execute(
                    text("UPDATE model_version SET status = 'deprecated' WHERE status = 'active'")
                )
            await session.commit()
            print("Telemetry reset complete.")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset AEGIS telemetry tables")
    parser.add_argument("--deprecate-models", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.deprecate_models))
