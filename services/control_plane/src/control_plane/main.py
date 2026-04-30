from contextlib import asynccontextmanager

from fastapi import FastAPI

from mcpsys_shared.db import make_engine, make_session_factory

from .routers import auth as auth_router
from .settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = make_engine(settings.database_url)
    app.state.session_factory = make_session_factory(app.state.engine)
    yield
    await app.state.engine.dispose()


app = FastAPI(title="MCPsys Control Plane", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router.router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
