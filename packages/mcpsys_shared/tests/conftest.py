import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.postgres import PostgresContainer

from mcpsys_shared.db import make_engine, make_session_factory
from mcpsys_shared.models import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def pg_url() -> AsyncIterator[str]:
    with PostgresContainer("postgres:16-alpine") as pg:
        raw = pg.get_connection_url()
        # testcontainers returns "postgresql+psycopg2://..."; convert to asyncpg
        url = raw.replace("postgresql+psycopg2", "postgresql+asyncpg")
        yield url


@pytest.fixture(scope="session")
async def engine(pg_url) -> AsyncIterator[AsyncEngine]:
    eng = make_engine(pg_url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    factory = make_session_factory(engine)
    async with factory() as s:
        yield s
        await s.rollback()
