import asyncio
import json

import bcrypt
import pytest
import respx
from httpx import Response as HxResponse
from sqlalchemy import func, select

from mcpsys_shared.models import (
    ApiKey,
    ApiKeyOwnerType,
    Application,
    CallLog,
    McpService,
    ServicePermission,
    ServiceStatus,
    TransportType,
    User,
    UserRole,
)


@pytest.fixture
async def seed(session_factory):
    async with session_factory() as s:
        u = User(username="agent-owner", role=UserRole.viewer)
        s.add(u)
        await s.flush()
        a = Application(name="agent-z", owner_user_id=u.id)
        s.add(a)
        await s.flush()
        plain = "mcpk_e2etestkey_zzz"
        k = ApiKey(
            name="e2e",
            key_prefix=plain[5:13],
            key_hash=bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode(),
            owner_type=ApiKeyOwnerType.application,
            owner_id=a.id,
        )
        s.add(k)
        svc = McpService(
            slug="echo",
            display_name="Echo",
            endpoint_url="http://upstream-echo/mcp",
            transport=TransportType.streamable_http,
            status=ServiceStatus.active,
        )
        s.add(svc)
        await s.flush()
        s.add(ServicePermission(application_id=a.id, service_id=svc.id, granted_by=u.id))
        await s.commit()
        await s.refresh(svc)
        return plain, svc.id


@respx.mock
async def test_proxy_success_path(client, seed, session_factory):
    plain, svc_id = seed
    upstream = respx.post("http://upstream-echo/mcp").respond(
        200, json={"jsonrpc": "2.0", "result": {"echo": "hi"}, "id": 7}
    )
    resp = await client.post(
        "/mcp/echo",
        headers={"Authorization": f"Bearer {plain}", "content-type": "application/json"},
        content=json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "echo", "arguments": {"msg": "hi"}},
                "id": 7,
            }
        ),
    )
    assert resp.status_code == 200
    assert resp.json()["result"]["echo"] == "hi"
    assert upstream.called
    assert resp.headers.get("x-request-id")

    # wait briefly for telemetry flush
    await asyncio.sleep(0.3)
    async with session_factory() as s:
        n = (
            await s.execute(
                select(func.count()).select_from(CallLog).where(CallLog.service_id == svc_id)
            )
        ).scalar_one()
        assert n == 1


async def test_missing_auth_returns_401(client):
    resp = await client.post("/mcp/echo", content=b"{}")
    assert resp.status_code == 401


async def test_unknown_service_returns_404(client, seed):
    plain, _ = seed
    resp = await client.post(
        "/mcp/no-such-service",
        headers={"Authorization": f"Bearer {plain}"},
        content=b"{}",
    )
    assert resp.status_code == 404


@respx.mock
async def test_upstream_5xx_passes_through_and_logged_as_error(client, seed, session_factory):
    plain, svc_id = seed
    respx.post("http://upstream-echo/mcp").mock(return_value=HxResponse(503, text="busy"))
    resp = await client.post(
        "/mcp/echo",
        headers={"Authorization": f"Bearer {plain}", "content-type": "application/json"},
        content=b'{"jsonrpc":"2.0","method":"tools/list","id":1}',
    )
    assert resp.status_code == 503
    await asyncio.sleep(0.3)
    async with session_factory() as s:
        from mcpsys_shared.models import CallStatus
        res = await s.execute(
            select(CallLog).where(CallLog.service_id == svc_id, CallLog.http_status == 503)
        )
        log = res.scalars().first()
        assert log is not None
        assert log.status == CallStatus.error


@pytest.fixture
async def seed_no_permission(session_factory):
    """Seed app+key+service WITHOUT a ServicePermission grant."""
    async with session_factory() as s:
        u = User(username="orphan-owner", role=UserRole.viewer)
        s.add(u)
        await s.flush()
        a = Application(name="orphan-app", owner_user_id=u.id)
        s.add(a)
        await s.flush()
        plain = "mcpk_orphankey_xx"
        k = ApiKey(
            name="orphan",
            key_prefix=plain[5:13],
            key_hash=bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode(),
            owner_type=ApiKeyOwnerType.application,
            owner_id=a.id,
        )
        s.add(k)
        svc = McpService(
            slug="locked",
            display_name="Locked",
            endpoint_url="http://upstream-locked/mcp",
            transport=TransportType.streamable_http,
            status=ServiceStatus.active,
        )
        s.add(svc)
        await s.commit()
        await s.refresh(svc)
        return plain, svc.id


@respx.mock
async def test_unauthorized_application_returns_403(client, seed_no_permission, session_factory):
    plain, svc_id = seed_no_permission
    # If the upstream is hit, this mock would fire — we will assert it does NOT.
    upstream = respx.post("http://upstream-locked/mcp").respond(200, json={"ok": True})

    resp = await client.post(
        "/mcp/locked",
        headers={"Authorization": f"Bearer {plain}", "content-type": "application/json"},
        content=b'{"jsonrpc":"2.0","method":"tools/list","id":1}',
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "application not authorized for this service"
    assert not upstream.called

    # call_log row is written even on deny
    await asyncio.sleep(0.3)
    async with session_factory() as s:
        from mcpsys_shared.models import CallStatus
        res = await s.execute(
            select(CallLog).where(CallLog.service_id == svc_id, CallLog.http_status == 403)
        )
        log = res.scalars().first()
        assert log is not None
        assert log.error_code == "permission_denied"
        assert log.status == CallStatus.denied
