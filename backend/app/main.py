"""AEGIS Security Gateway — FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from app.api.v1 import (
    analytics,
    audit,
    auth,
    events,
    gateway,
    incidents,
    ml,
    policies,
    responses,
    settings as settings_router,
    threats,
    tools,
    users,
)
from app.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.database import async_session_factory, dispose_engine

settings = get_settings()
setup_logging(settings.log_level)
logger = get_logger("aegis.main")

_in_process_worker_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _in_process_worker_task
    from app.security.llm.analyzer import close_llm_analyzer, init_llm_analyzer
    from app.worker.main import run_worker_forever

    init_llm_analyzer(settings)
    if os.environ.get("AEGIS_IN_PROCESS_WORKER", "true").lower() == "true":
        _in_process_worker_task = asyncio.create_task(
            run_worker_forever(async_session_factory, settings)
        )
        logger.info("aegis.in_process_worker_started")
    logger.info("aegis.startup", environment=settings.environment)
    yield
    if _in_process_worker_task is not None:
        _in_process_worker_task.cancel()
        try:
            await _in_process_worker_task
        except asyncio.CancelledError:
            pass
    await close_llm_analyzer()
    await dispose_engine()


app = FastAPI(
    title="AEGIS Security Gateway",
    description=(
        "AI-powered API and LLM security gateway. Detects, scores, explains, "
        "blocks and responds to malicious or anomalous API and AI activity. "
        "Includes ML anomaly detection, prompt-injection defense, agent/tool "
        "security, incident correlation and policy enforcement."
    ),
    version=settings.version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = settings.api_prefix

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(gateway.router, prefix=API_PREFIX)
app.include_router(incidents.router, prefix=API_PREFIX)
app.include_router(events.router, prefix=API_PREFIX)
app.include_router(policies.router, prefix=API_PREFIX)
app.include_router(ml.router, prefix=API_PREFIX)
app.include_router(tools.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(audit.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)
app.include_router(threats.router, prefix=API_PREFIX)
app.include_router(responses.router, prefix=API_PREFIX)
app.include_router(settings_router.router, prefix=API_PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name, "version": settings.version}


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "req_" + __import__("uuid").uuid4().hex[:20])
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response
