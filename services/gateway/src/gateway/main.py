from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from mcpsys_shared.db import make_engine, make_session_factory

from .settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = make_engine(settings.database_url)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.state.http = httpx.AsyncClient(timeout=settings.proxy_timeout_seconds)
    yield
    await app.state.http.aclose()
    await app.state.engine.dispose()


app = FastAPI(title="MCPsys Gateway", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
