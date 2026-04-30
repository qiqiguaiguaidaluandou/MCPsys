import pytest

from mcpsys_shared.models import McpService, ServiceStatus, TransportType

from gateway.resolver import ServiceNotFound, ServiceResolver


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as s:
        s.add(
            McpService(
                slug="active-svc",
                display_name="A",
                endpoint_url="http://a.internal/mcp",
                transport=TransportType.streamable_http,
                status=ServiceStatus.active,
            )
        )
        s.add(
            McpService(
                slug="disabled-svc",
                display_name="D",
                endpoint_url="http://d.internal/mcp",
                transport=TransportType.streamable_http,
                status=ServiceStatus.disabled,
            )
        )
        await s.commit()


async def test_resolves_active_service(session_factory, seeded):
    r = ServiceResolver(session_factory=session_factory, ttl_seconds=60)
    info = await r.resolve("active-svc")
    assert info.endpoint_url == "http://a.internal/mcp"
    assert info.service_id is not None


async def test_disabled_service_raises(session_factory, seeded):
    r = ServiceResolver(session_factory=session_factory, ttl_seconds=60)
    with pytest.raises(ServiceNotFound):
        await r.resolve("disabled-svc")


async def test_unknown_service_raises(session_factory, seeded):
    r = ServiceResolver(session_factory=session_factory, ttl_seconds=60)
    with pytest.raises(ServiceNotFound):
        await r.resolve("nope")


async def test_invalidate_clears_cache(session_factory, seeded):
    r = ServiceResolver(session_factory=session_factory, ttl_seconds=60)
    info1 = await r.resolve("active-svc")

    # mutate underlying record
    from sqlalchemy import select

    async with session_factory() as s:
        res = await s.execute(select(McpService).where(McpService.slug == "active-svc"))
        svc = res.scalar_one()
        svc.endpoint_url = "http://a.internal/mcp/v2"
        await s.commit()

    # cached value still old
    info2 = await r.resolve("active-svc")
    assert info2.endpoint_url == info1.endpoint_url

    r.invalidate("active-svc")
    info3 = await r.resolve("active-svc")
    assert info3.endpoint_url == "http://a.internal/mcp/v2"
