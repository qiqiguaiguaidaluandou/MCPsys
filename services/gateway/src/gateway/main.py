from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from redis.asyncio import Redis

from mcpsys_shared.db import make_engine, make_session_factory

from .resolver import ServiceResolver
from .routers import mcp as mcp_router
from .settings import settings
from .telemetry import TelemetryWriter


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = make_engine(settings.database_url)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.state.http = httpx.AsyncClient(timeout=settings.proxy_timeout_seconds)
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.resolver = ServiceResolver(
        session_factory=app.state.session_factory,
        ttl_seconds=settings.service_cache_ttl_seconds,
    )
    app.state.telemetry = TelemetryWriter(
        session_factory=app.state.session_factory,
        batch_size=settings.telemetry_batch_size,
        flush_interval=settings.telemetry_flush_interval_seconds,
    )
    await app.state.telemetry.start()
    try:
        yield
    finally:
        await app.state.telemetry.stop()
        await app.state.http.aclose()
        await app.state.redis.aclose()
        await app.state.engine.dispose()


app = FastAPI(title="MCPsys Gateway", version="0.1.0", lifespan=lifespan)
app.include_router(mcp_router.router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
