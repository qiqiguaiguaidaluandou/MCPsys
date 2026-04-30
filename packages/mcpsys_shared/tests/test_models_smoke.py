from sqlalchemy import select

from mcpsys_shared.models import McpService, ServiceStatus, TransportType, User, UserRole


async def test_create_user(session):
    u = User(username="alice", role=UserRole.admin)
    session.add(u)
    await session.flush()
    res = await session.execute(select(User).where(User.username == "alice"))
    fetched = res.scalar_one()
    assert fetched.role == UserRole.admin


async def test_create_mcp_service(session):
    svc = McpService(
        slug="hr-bot",
        display_name="HR Bot",
        endpoint_url="http://hr-bot.internal:8000/mcp",
        transport=TransportType.streamable_http,
        status=ServiceStatus.active,
    )
    session.add(svc)
    await session.flush()
    res = await session.execute(select(McpService).where(McpService.slug == "hr-bot"))
    fetched = res.scalar_one()
    assert fetched.endpoint_url == "http://hr-bot.internal:8000/mcp"
