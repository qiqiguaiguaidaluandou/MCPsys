from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from testcontainers.postgres import PostgresContainer

from mcpsys_shared.db import make_engine, make_session_factory
from mcpsys_shared.models import Base


@pytest.fixture(scope="session")
def pg_url() -> AsyncIterator[str]:
    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url().replace("postgresql+psycopg2", "postgresql+asyncpg")
        yield url


@pytest.fixture(scope="session")
async def engine(pg_url) -> AsyncIterator[AsyncEngine]:
    eng = make_engine(pg_url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session_factory(engine) -> async_sessionmaker:
    return make_session_factory(engine)


@pytest.fixture
async def app(engine, session_factory):
    from control_plane.main import app as fastapi_app

    fastapi_app.state.engine = engine
    fastapi_app.state.session_factory = session_factory
    return fastapi_app


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
