import asyncio

import pytest
from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings
from mcpsys_shared.models import User, UserRole, UserStatus
from redis.asyncio import Redis


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


async def test_delete_service_soft_marks_disabled(client, admin):
    await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={"slug": "tmp", "display_name": "Tmp", "endpoint_url": "http://tmp/mcp"},
    )
    resp = await client.delete("/api/v1/services/tmp", headers=auth_header(admin))
    assert resp.status_code == 204
    # Soft-delete: row stays so call_logs history keeps its slug → name mapping.
    resp2 = await client.get("/api/v1/services/tmp", headers=auth_header(admin))
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "disabled"


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
