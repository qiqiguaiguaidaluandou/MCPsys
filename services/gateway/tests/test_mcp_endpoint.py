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


@pytest.fixture
async def seed_with_qps_service(session_factory):
    """Same shape as `seed` but sets service.rate_limit_qps=1."""
    async with session_factory() as s:
        u = User(username="rl-svc-owner", role=UserRole.viewer)
        s.add(u)
        await s.flush()
        a = Application(name="rl-svc-app", owner_user_id=u.id)
        s.add(a)
        await s.flush()
        plain = "mcpk_rlsvc_xx"
        k = ApiKey(
            name="rl-svc",
            key_prefix=plain[5:13],
            key_hash=bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode(),
            owner_type=ApiKeyOwnerType.application,
            owner_id=a.id,
        )
        s.add(k)
        svc = McpService(
            slug="rl-svc",
            display_name="RL Svc",
            endpoint_url="http://upstream-rlsvc/mcp",
            transport=TransportType.streamable_http,
            status=ServiceStatus.active,
            rate_limit_qps=1,
        )
        s.add(svc)
        await s.flush()
        s.add(ServicePermission(application_id=a.id, service_id=svc.id, granted_by=u.id))
        await s.commit()
        await s.refresh(svc)
        return plain, svc.id


@pytest.fixture
async def seed_with_qps_key(session_factory):
    """Same shape but sets api_key.rate_limit_qps=1."""
    async with session_factory() as s:
        u = User(username="rl-key-owner", role=UserRole.viewer)
        s.add(u)
        await s.flush()
        a = Application(name="rl-key-app", owner_user_id=u.id)
        s.add(a)
        await s.flush()
        plain = "mcpk_rlkey_xx"
        k = ApiKey(
            name="rl-key",
            key_prefix=plain[5:13],
            key_hash=bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode(),
            owner_type=ApiKeyOwnerType.application,
            owner_id=a.id,
            rate_limit_qps=1,
        )
        s.add(k)
        svc = McpService(
            slug="rl-key",
            display_name="RL Key",
            endpoint_url="http://upstream-rlkey/mcp",
            transport=TransportType.streamable_http,
            status=ServiceStatus.active,
        )
        s.add(svc)
        await s.flush()
        s.add(ServicePermission(application_id=a.id, service_id=svc.id, granted_by=u.id))
        await s.commit()
        await s.refresh(svc)
        return plain, svc.id


@pytest.fixture
async def seed_with_qps_zero(session_factory):
    """Service with rate_limit_qps=0 -> all calls 429 immediately, no Retry-After."""
    async with session_factory() as s:
        u = User(username="rl-zero-owner", role=UserRole.viewer)
        s.add(u)
        await s.flush()
        a = Application(name="rl-zero-app", owner_user_id=u.id)
        s.add(a)
        await s.flush()
        plain = "mcpk_rlzero_xx"
        k = ApiKey(
            name="rl-zero",
            key_prefix=plain[5:13],
            key_hash=bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode(),
            owner_type=ApiKeyOwnerType.application,
            owner_id=a.id,
        )
        s.add(k)
        svc = McpService(
            slug="rl-zero",
            display_name="RL Zero",
            endpoint_url="http://upstream-rlzero/mcp",
            transport=TransportType.streamable_http,
            status=ServiceStatus.active,
            rate_limit_qps=0,
        )
        s.add(svc)
        await s.flush()
        s.add(ServicePermission(application_id=a.id, service_id=svc.id, granted_by=u.id))
        await s.commit()
        await s.refresh(svc)
        return plain, svc.id


@respx.mock
async def test_service_qps_throttles(client, seed_with_qps_service, session_factory):
    plain, svc_id = seed_with_qps_service
    upstream = respx.post("http://upstream-rlsvc/mcp").respond(
        200, json={"jsonrpc": "2.0", "result": {}, "id": 1}
    )
    headers = {"Authorization": f"Bearer {plain}", "content-type": "application/json"}
    body = b'{"jsonrpc":"2.0","method":"tools/list","id":1}'
    r1 = await client.post("/mcp/rl-svc", headers=headers, content=body)
    r2 = await client.post("/mcp/rl-svc", headers=headers, content=body)
    r3 = await client.post("/mcp/rl-svc", headers=headers, content=body)
    # qps=1, burst=2 -> first 2 ok, 3rd throttled
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert r3.json()["detail"] == "service rate limit exceeded"
    assert r3.headers.get("Retry-After")
    # at least one throttled call_log
    await asyncio.sleep(0.3)
    async with session_factory() as s:
        from mcpsys_shared.models import CallStatus
        rows = (
            await s.execute(
                select(CallLog).where(CallLog.service_id == svc_id, CallLog.status == CallStatus.throttled)
            )
        ).scalars().all()
        assert len(rows) >= 1


@respx.mock
async def test_key_qps_throttles(client, seed_with_qps_key, session_factory):
    plain, svc_id = seed_with_qps_key
    respx.post("http://upstream-rlkey/mcp").respond(
        200, json={"jsonrpc": "2.0", "result": {}, "id": 1}
    )
    headers = {"Authorization": f"Bearer {plain}", "content-type": "application/json"}
    body = b'{"jsonrpc":"2.0","method":"tools/list","id":1}'
    r1 = await client.post("/mcp/rl-key", headers=headers, content=body)
    r2 = await client.post("/mcp/rl-key", headers=headers, content=body)
    r3 = await client.post("/mcp/rl-key", headers=headers, content=body)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert r3.json()["detail"] == "key rate limit exceeded"


async def test_qps_zero_blocks_all(client, seed_with_qps_zero):
    plain, _ = seed_with_qps_zero
    r = await client.post(
        "/mcp/rl-zero",
        headers={"Authorization": f"Bearer {plain}", "content-type": "application/json"},
        content=b'{"jsonrpc":"2.0","method":"tools/list","id":1}',
    )
    assert r.status_code == 429
    assert r.headers.get("Retry-After") is None  # qps==0 has no meaningful retry
