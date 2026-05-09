from contextlib import asynccontextmanager

from fastapi import FastAPI
from mcpsys_shared.db import make_engine, make_session_factory
from redis.asyncio import Redis

from .routers import (
    api_keys as api_keys_router,
)
from .routers import (
    applications as applications_router,
)
from .routers import (
    auth as auth_router,
)
from .routers import (
    call_logs as call_logs_router,
)
from .routers import (
    permissions as permissions_router,
)
from .routers import (
    services as services_router,
)
from .routers import (
    users as users_router,
)
from .settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = make_engine(settings.database_url)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield
    finally:
        await app.state.redis.aclose()
        await app.state.engine.dispose()


app = FastAPI(
    title="MCPsys Control Plane",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    redoc_url="/api/v1/redoc",
)
app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(applications_router.router)
app.include_router(services_router.router)
app.include_router(api_keys_router.router)
app.include_router(call_logs_router.router)
app.include_router(permissions_router.router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
