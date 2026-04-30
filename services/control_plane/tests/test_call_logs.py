from datetime import UTC, datetime, timedelta

import pytest

from mcpsys_shared.models import (
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
async def operator(session_factory):
    async with session_factory() as s:
        u = User(
            username="logs-operator",
            password_hash=hash_password("p"),
            role=UserRole.operator,
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
            username="logs-viewer",
            password_hash=hash_password("p"),
            role=UserRole.viewer,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


@pytest.fixture
async def seeded_logs(session_factory):
    async with session_factory() as s:
        svc = McpService(
            slug="logs-svc",
            display_name="LS",
            endpoint_url="http://x/mcp",
            transport=TransportType.streamable_http,
            status=ServiceStatus.active,
        )
        s.add(svc)
        await s.flush()
        now = datetime.now(UTC)
        for i in range(5):
            s.add(
                CallLog(
                    ts=now - timedelta(minutes=i),
                    service_id=svc.id,
                    status=CallStatus.success if i % 2 == 0 else CallStatus.error,
                    duration_ms=10 + i,
                )
            )
        await s.commit()
        return svc.id


def auth_header(user):
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


async def test_list_logs(client, operator, seeded_logs):
    resp = await client.get(
        f"/api/v1/call-logs?service_id={seeded_logs}",
        headers=auth_header(operator),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 5


async def test_filter_by_status(client, operator, seeded_logs):
    resp = await client.get(
        f"/api/v1/call-logs?service_id={seeded_logs}&status=error",
        headers=auth_header(operator),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert all(i["status"] == "error" for i in body["items"])


async def test_pagination(client, operator, seeded_logs):
    resp = await client.get(
        f"/api/v1/call-logs?service_id={seeded_logs}&limit=2",
        headers=auth_header(operator),
    )
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5


async def test_viewer_forbidden_on_call_logs(client, viewer, seeded_logs):
    """Viewer must not access call_logs (request/response bodies may be sensitive across tenants)."""
    resp = await client.get(
        f"/api/v1/call-logs?service_id={seeded_logs}",
        headers=auth_header(viewer),
    )
    assert resp.status_code == 403
