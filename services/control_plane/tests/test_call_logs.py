from datetime import UTC, datetime, timedelta
from uuid import uuid4

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
async def admin(session_factory):
    async with session_factory() as s:
        u = User(
            username="logs-admin",
            password_hash=hash_password("p"),
            role=UserRole.admin,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


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


@pytest.fixture
async def tool_seeded_logs(session_factory):
    async with session_factory() as s:
        svc = McpService(
            slug="tool-svc",
            display_name="TS",
            endpoint_url="http://x/mcp",
            transport=TransportType.streamable_http,
            status=ServiceStatus.active,
        )
        s.add(svc)
        await s.flush()
        now = datetime.now(UTC)
        for i, tname in enumerate(["get_weather", "get_weather", "send_email", "send_email", "list_users"]):
            s.add(
                CallLog(
                    ts=now - timedelta(minutes=i),
                    service_id=svc.id,
                    tool_name=tname,
                    status=CallStatus.success,
                    duration_ms=10,
                )
            )
        await s.commit()
        return svc.id


async def test_filter_by_tool(client, operator, tool_seeded_logs):
    resp = await client.get(
        f"/api/v1/call-logs?service_id={tool_seeded_logs}&tool=get_weather",
        headers=auth_header(operator),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert all(i["tool_name"] == "get_weather" for i in body["items"])


async def test_filter_by_tool_empty_value_is_noop(client, operator, tool_seeded_logs):
    # tool="" 应当被视作未过滤，否则前端清空输入框会查不到任何 tool_name=NULL 的记录
    resp = await client.get(
        f"/api/v1/call-logs?service_id={tool_seeded_logs}&tool=",
        headers=auth_header(operator),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 5


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


@pytest.fixture
async def call_log_with_body(session_factory):
    async with session_factory() as s:
        svc = McpService(
            slug="detail-svc",
            display_name="Detail Svc",
            endpoint_url="http://x/mcp",
            transport=TransportType.streamable_http,
            status=ServiceStatus.active,
        )
        s.add(svc)
        await s.flush()
        row = CallLog(
            ts=datetime.now(UTC),
            service_id=svc.id,
            service_version="1.0",
            tool_name="echo",
            request_id="req-abc",
            status=CallStatus.success,
            http_status=200,
            duration_ms=42,
            request_body='{"x":1}',
            response_body='{"ok":true}',
            client_ip="10.0.0.5",
        )
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return row


@pytest.fixture
async def call_log_null_bodies(session_factory):
    async with session_factory() as s:
        svc = McpService(
            slug="null-body-svc",
            display_name="NB",
            endpoint_url="http://x/mcp",
            transport=TransportType.streamable_http,
            status=ServiceStatus.active,
        )
        s.add(svc)
        await s.flush()
        row = CallLog(
            ts=datetime.now(UTC),
            service_id=svc.id,
            status=CallStatus.success,
            duration_ms=5,
            request_body=None,
            response_body=None,
        )
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return row


async def test_get_call_log_as_admin(client, admin, call_log_with_body):
    resp = await client.get(
        f"/api/v1/call-logs/{call_log_with_body.id}",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(call_log_with_body.id)
    assert body["request_body"] == '{"x":1}'
    assert body["response_body"] == '{"ok":true}'
    assert body["service_version"] == "1.0"
    assert body["request_id"] == "req-abc"
    assert body["client_ip"] == "10.0.0.5"
    assert body["tool_name"] == "echo"


async def test_get_call_log_as_operator(client, operator, call_log_with_body):
    resp = await client.get(
        f"/api/v1/call-logs/{call_log_with_body.id}",
        headers=auth_header(operator),
    )
    assert resp.status_code == 200


async def test_get_call_log_as_viewer_forbidden(client, viewer, call_log_with_body):
    resp = await client.get(
        f"/api/v1/call-logs/{call_log_with_body.id}",
        headers=auth_header(viewer),
    )
    assert resp.status_code == 403


async def test_get_call_log_unauthenticated(client, call_log_with_body):
    resp = await client.get(f"/api/v1/call-logs/{call_log_with_body.id}")
    assert resp.status_code == 401


async def test_get_call_log_not_found(client, admin):
    resp = await client.get(
        f"/api/v1/call-logs/{uuid4()}",
        headers=auth_header(admin),
    )
    assert resp.status_code == 404


async def test_get_call_log_with_null_bodies(client, admin, call_log_null_bodies):
    resp = await client.get(
        f"/api/v1/call-logs/{call_log_null_bodies.id}",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["request_body"] is None
    assert body["response_body"] is None
