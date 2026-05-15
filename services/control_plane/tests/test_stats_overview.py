import uuid
from datetime import UTC, datetime, timedelta

import pytest
from mcpsys_shared.models import (
    Application,
    CallLog,
    CallStatus,
    McpService,
    ServiceStatus,
    TransportType,
    User,
    UserRole,
    UserStatus,
)

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as s:
        u = User(
            username="stats-admin",
            password_hash=hash_password("p"),
            role=UserRole.admin,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


@pytest.fixture
async def viewer(session_factory):
    async with session_factory() as s:
        u = User(
            username="stats-viewer",
            password_hash=hash_password("p"),
            role=UserRole.viewer,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


@pytest.fixture
async def service_a(session_factory):
    async with session_factory() as s:
        svc = McpService(
            slug="svc-a",
            display_name="A",
            endpoint_url="http://a/mcp",
            transport=TransportType.streamable_http,
            status=ServiceStatus.active,
        )
        s.add(svc)
        await s.commit()
        await s.refresh(svc)
        return svc


@pytest.fixture
async def service_b(session_factory):
    async with session_factory() as s:
        svc = McpService(
            slug="svc-b",
            display_name="B",
            endpoint_url="http://b/mcp",
            transport=TransportType.streamable_http,
            status=ServiceStatus.active,
        )
        s.add(svc)
        await s.commit()
        await s.refresh(svc)
        return svc


def auth_header(user: User) -> dict:
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


async def _add_log(
    s,
    *,
    ts: datetime | None = None,
    status: CallStatus = CallStatus.success,
    duration_ms: int = 10,
    service_id: int | None = None,
    application_id: int | None = None,
    api_key_id: int | None = None,
    tool_name: str = "tools/list",
) -> None:
    s.add(
        CallLog(
            id=uuid.uuid4(),
            ts=ts or datetime.now(UTC),
            service_id=service_id or 1,
            application_id=application_id,
            api_key_id=api_key_id,
            tool_name=tool_name,
            request_id=str(uuid.uuid4()),
            status=status,
            http_status=200 if status == CallStatus.success else 500,
            duration_ms=duration_ms,
            request_bytes=10,
            response_bytes=10,
        )
    )


async def test_overview_24h_happy(client, admin, session_factory):
    now = datetime.now(UTC)
    async with session_factory() as s:
        for i in range(8):
            await _add_log(s, ts=now - timedelta(hours=1), duration_ms=10 + i * 5)
        await _add_log(s, ts=now - timedelta(hours=2), status=CallStatus.error, duration_ms=200)
        await _add_log(s, ts=now - timedelta(hours=2), status=CallStatus.throttled, duration_ms=0)
        await s.commit()

    resp = await client.get("/api/v1/stats/overview?range=24h", headers=auth_header(admin))
    assert resp.status_code == 200
    data = resp.json()
    assert data["calls"] == 10
    assert data["errors"] == 2
    assert data["throttled"] == 1
    assert 0 < data["error_rate"] < 1
    assert data["p50_ms"] is not None
    assert data["last_call_at"] is not None
    assert data["filter"] is None
    assert "from" in data and "to" in data


async def test_overview_empty(client, admin):
    resp = await client.get("/api/v1/stats/overview?range=24h", headers=auth_header(admin))
    data = resp.json()
    assert data["calls"] == 0
    assert data["errors"] == 0
    assert data["error_rate"] == 0.0
    assert data["p50_ms"] is None
    assert data["last_call_at"] is None


async def test_overview_with_service_filter(client, admin, session_factory, service_a, service_b):
    now = datetime.now(UTC)
    async with session_factory() as s:
        for _ in range(100):
            await _add_log(s, ts=now - timedelta(minutes=10), service_id=service_a.id)
        for _ in range(50):
            await _add_log(s, ts=now - timedelta(minutes=10), service_id=service_b.id)
        await s.commit()

    resp = await client.get(
        f"/api/v1/stats/overview?range=24h&service_id={service_a.id}",
        headers=auth_header(admin),
    )
    data = resp.json()
    assert data["calls"] == 100
    assert data["filter"] == {
        "service_id": service_a.id,
        "application_id": None,
        "api_key_id": None,
    }


async def test_overview_filter_priority(client, admin, session_factory, service_a):
    """spec §3.2.1 优先级：service_id > application_id > api_key_id。"""
    async with session_factory() as s:
        await _add_log(s, service_id=service_a.id)
        await s.commit()

    resp = await client.get(
        f"/api/v1/stats/overview?range=24h&service_id={service_a.id}&application_id=999",
        headers=auth_header(admin),
    )
    data = resp.json()
    assert data["filter"]["service_id"] == service_a.id
    assert data["filter"]["application_id"] is None


async def test_overview_viewer_can_read(client, viewer):
    resp = await client.get("/api/v1/stats/overview?range=24h", headers=auth_header(viewer))
    assert resp.status_code == 200


async def test_overview_unauthenticated_rejected(client):
    resp = await client.get("/api/v1/stats/overview?range=24h")
    assert resp.status_code == 401


async def test_overview_invalid_range_422(client, admin):
    resp = await client.get("/api/v1/stats/overview?range=foo", headers=auth_header(admin))
    assert resp.status_code == 422
