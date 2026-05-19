import asyncio

import pytest
from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings
from mcpsys_shared.models import AuditEvent, McpService, User, UserRole, UserStatus
from redis.asyncio import Redis
from sqlalchemy import select


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as s:
        u = User(
            username="svc-admin",
            password_hash=hash_password("p"),
            role=UserRole.admin,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


def auth_header(user):
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


async def test_create_service(client, admin):
    resp = await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={
            "slug": "hr-bot",
            "display_name": "HR Bot",
            "description": "internal HR mcp",
            "owner_team": "hr",
            "tags": ["internal"],
            "endpoint_url": "http://hr-bot.internal:8000/mcp",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "hr-bot"
    assert body["transport"] == "streamable_http"
    assert body["status"] == "active"
    assert body["health_status"] == "unknown"


async def test_invalid_slug_rejected(client, admin):
    resp = await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={
            "slug": "Has Spaces",
            "display_name": "x",
            "endpoint_url": "http://x/mcp",
        },
    )
    assert resp.status_code == 422


async def test_get_service_by_slug(client, admin):
    await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={"slug": "crm", "display_name": "CRM", "endpoint_url": "http://crm/mcp"},
    )
    resp = await client.get("/api/v1/services/crm", headers=auth_header(admin))
    assert resp.status_code == 200
    assert resp.json()["slug"] == "crm"


async def test_get_service_includes_timestamps(client, admin):
    """ServiceOut 必须下发 created_at / updated_at / last_health_check_at；
    历史 schema 漏字段导致前端「注册时间」一直显示 -。"""
    await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={"slug": "ts-svc", "display_name": "TS", "endpoint_url": "http://ts/mcp"},
    )
    resp = await client.get("/api/v1/services/ts-svc", headers=auth_header(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body.get("created_at"), str) and body["created_at"]
    assert isinstance(body.get("updated_at"), str) and body["updated_at"]
    # 健康检查 worker 尚未跑过该服务，应为 None
    assert body.get("last_health_check_at") is None


async def test_update_service_endpoint(client, admin):
    await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={"slug": "wiki", "display_name": "Wiki", "endpoint_url": "http://old/mcp"},
    )
    resp = await client.patch(
        "/api/v1/services/wiki",
        headers=auth_header(admin),
        json={"endpoint_url": "http://new/mcp", "status": "disabled"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["endpoint_url"] == "http://new/mcp"
    assert body["status"] == "disabled"


async def test_delete_service_archives(client, admin):
    create = await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={"slug": "tmp", "display_name": "Tmp", "endpoint_url": "http://tmp/mcp"},
    )
    sid = create.json()["id"]
    resp = await client.delete("/api/v1/services/tmp", headers=auth_header(admin))
    assert resp.status_code == 204
    # 原 slug 已释放；归档项可用新 slug 取回
    resp_old = await client.get("/api/v1/services/tmp", headers=auth_header(admin))
    assert resp_old.status_code == 404
    resp_new = await client.get(f"/api/v1/services/__archived_{sid}", headers=auth_header(admin))
    assert resp_new.status_code == 200
    body = resp_new.json()
    assert body["status"] == "disabled"
    assert body["slug"] == f"__archived_{sid}"
    assert body["display_name"] == "Tmp"  # display_name 不动


async def test_delete_then_recreate_same_slug(client, admin):
    """归档式删除的核心收益：原 slug 释放后可以重建同名服务。"""
    create_first = await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={"slug": "weather", "display_name": "Weather v1", "endpoint_url": "http://w1/mcp"},
    )
    assert create_first.status_code == 201
    first_id = create_first.json()["id"]

    del_resp = await client.delete("/api/v1/services/weather", headers=auth_header(admin))
    assert del_resp.status_code == 204

    create_second = await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={"slug": "weather", "display_name": "Weather v2", "endpoint_url": "http://w2/mcp"},
    )
    assert create_second.status_code == 201
    second_id = create_second.json()["id"]
    assert second_id != first_id
    assert create_second.json()["display_name"] == "Weather v2"


async def test_create_service_with_qps(client, admin):
    resp = await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={
            "slug": "qps-svc",
            "display_name": "Q",
            "endpoint_url": "http://q/mcp",
            "rate_limit_qps": 5,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["rate_limit_qps"] == 5


async def test_patch_qps_to_null_clears(client, admin):
    await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={"slug": "qps-clear", "display_name": "Q", "endpoint_url": "http://q/mcp", "rate_limit_qps": 5},
    )
    resp = await client.patch(
        "/api/v1/services/qps-clear",
        headers=auth_header(admin),
        json={"rate_limit_qps": None},
    )
    assert resp.status_code == 200
    assert resp.json()["rate_limit_qps"] is None


async def test_patch_qps_to_zero_blocks(client, admin):
    await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={"slug": "qps-zero", "display_name": "Q", "endpoint_url": "http://q/mcp"},
    )
    resp = await client.patch(
        "/api/v1/services/qps-zero",
        headers=auth_header(admin),
        json={"rate_limit_qps": 0},
    )
    assert resp.status_code == 200
    assert resp.json()["rate_limit_qps"] == 0


async def _drain(pubsub, expected_data: str, timeout: float = 2.0) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
        if msg is not None and msg.get("data") == expected_data:
            return True
    return False


async def test_patch_publishes_service_invalidate(client, admin, redis_url):
    await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={"slug": "broadcast", "display_name": "B", "endpoint_url": "http://b/mcp"},
    )
    sub = Redis.from_url(redis_url, decode_responses=True)
    try:
        async with sub.pubsub() as ps:
            await ps.subscribe("service:invalidate")
            await asyncio.sleep(0.05)

            resp = await client.patch(
                "/api/v1/services/broadcast",
                headers=auth_header(admin),
                json={"endpoint_url": "http://b2/mcp"},
            )
            assert resp.status_code == 200

            assert await _drain(ps, "broadcast")
    finally:
        await sub.aclose()


async def test_delete_publishes_service_invalidate(client, admin, redis_url):
    await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={"slug": "byebye", "display_name": "B", "endpoint_url": "http://b/mcp"},
    )
    sub = Redis.from_url(redis_url, decode_responses=True)
    try:
        async with sub.pubsub() as ps:
            await ps.subscribe("service:invalidate")
            await asyncio.sleep(0.05)

            resp = await client.delete(
                "/api/v1/services/byebye", headers=auth_header(admin)
            )
            assert resp.status_code == 204

            assert await _drain(ps, "byebye")
    finally:
        await sub.aclose()


@pytest.fixture
async def existing_service(session_factory):
    async with session_factory() as s:
        svc = McpService(
            slug="audit-existing",
            display_name="Audit Existing",
            endpoint_url="http://audit-existing.internal:8000/mcp",
        )
        s.add(svc)
        await s.commit()
        await s.refresh(svc)
        return svc


async def test_audit_service_create(client, admin, session_factory):
    resp = await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={
            "slug": "audit-svc",
            "display_name": "Audit Svc",
            "endpoint_url": "http://audit-svc.internal:8000/mcp",
        },
    )
    assert resp.status_code == 201
    async with session_factory() as s:
        r = (await s.execute(select(AuditEvent).where(AuditEvent.action == "service.create"))).scalar_one()
    assert r.target_type == "mcp_service"
    assert r.before is None
    assert r.after["slug"] == "audit-svc"
    assert r.actor_user_id == admin.id


async def test_audit_service_update(client, admin, existing_service, session_factory):
    resp = await client.patch(
        f"/api/v1/services/{existing_service.slug}",
        headers=auth_header(admin),
        json={"display_name": "Renamed"},
    )
    assert resp.status_code == 200
    async with session_factory() as s:
        r = (await s.execute(select(AuditEvent).where(AuditEvent.action == "service.update"))).scalar_one()
    assert r.before["display_name"] != "Renamed"
    assert r.after["display_name"] == "Renamed"


async def test_audit_service_delete(client, admin, existing_service, session_factory):
    resp = await client.delete(
        f"/api/v1/services/{existing_service.slug}",
        headers=auth_header(admin),
    )
    assert resp.status_code in (200, 204)
    async with session_factory() as s:
        r = (await s.execute(select(AuditEvent).where(AuditEvent.action == "service.delete"))).scalar_one()
    assert r.target_id == str(existing_service.id)
    assert r.before is not None
    assert r.before["slug"] == "audit-existing"  # 原始 slug 完整保留
    assert r.after is not None
    assert r.after["status"] == "disabled"
    assert r.after["slug"] == f"__archived_{existing_service.id}"
