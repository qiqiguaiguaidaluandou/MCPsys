import asyncio

import pytest
from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings
from mcpsys_shared.models import Application, McpService, User, UserRole, UserStatus
from redis.asyncio import Redis


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as s:
        u = User(
            username="admin-perm",
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
            username="viewer-perm",
            password_hash=hash_password("p"),
            role=UserRole.viewer,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


@pytest.fixture
async def app_row(session_factory, admin):
    async with session_factory() as s:
        a = Application(name="perm-app", owner_user_id=admin.id, team="t")
        s.add(a)
        await s.commit()
        await s.refresh(a)
        return a


@pytest.fixture
async def svc_row(session_factory):
    async with session_factory() as s:
        svc = McpService(slug="perm-svc", display_name="P", endpoint_url="http://p/mcp")
        s.add(svc)
        await s.commit()
        await s.refresh(svc)
        return svc


def auth_header(user):
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


async def test_grant_permission(client, admin, app_row, svc_row):
    resp = await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id, "note": "for crm bot"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["application_id"] == app_row.id
    assert body["service_id"] == svc_row.id
    assert body["note"] == "for crm bot"
    assert body["granted_by"] == admin.id


async def test_grant_is_idempotent(client, admin, app_row, svc_row):
    await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id},
    )
    resp = await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id, "note": "second call"},
    )
    assert resp.status_code == 200  # 200 not 201, not 409
    assert resp.json()["application_id"] == app_row.id


async def test_list_service_permissions(client, admin, app_row, svc_row):
    await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id},
    )
    resp = await client.get(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(it["application_id"] == app_row.id for it in items)


async def test_revoke_permission(client, admin, app_row, svc_row):
    await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id},
    )
    resp = await client.delete(
        f"/api/v1/services/{svc_row.slug}/permissions/{app_row.id}",
        headers=auth_header(admin),
    )
    assert resp.status_code == 204


async def test_revoke_unknown_grant_is_204(client, admin, app_row, svc_row):
    resp = await client.delete(
        f"/api/v1/services/{svc_row.slug}/permissions/{app_row.id}",
        headers=auth_header(admin),
    )
    assert resp.status_code == 204  # idempotent


async def test_reverse_list_by_application(client, admin, app_row, svc_row):
    await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id},
    )
    resp = await client.get(
        f"/api/v1/applications/{app_row.id}/permissions",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(it["service_id"] == svc_row.id for it in items)


async def test_viewer_cannot_write_permission(client, viewer, app_row, svc_row):
    resp = await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(viewer),
        json={"application_id": app_row.id},
    )
    assert resp.status_code == 403


async def test_grant_unknown_service_is_404(client, admin, app_row):
    resp = await client.post(
        "/api/v1/services/no-such-svc/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id},
    )
    assert resp.status_code == 404


async def test_viewer_can_read_permissions(client, admin, viewer, app_row, svc_row):
    # admin grants, viewer reads
    await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id},
    )
    resp = await client.get(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(viewer),
    )
    assert resp.status_code == 200
    assert any(it["application_id"] == app_row.id for it in resp.json()["items"])


async def _drain(pubsub, expected_data: str, timeout: float = 2.0) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
        if msg is not None and msg.get("data") == expected_data:
            return True
    return False


async def test_grant_publishes_policy_invalidate(
    client, admin, app_row, svc_row, redis_url
):
    sub = Redis.from_url(redis_url, decode_responses=True)
    try:
        async with sub.pubsub() as ps:
            await ps.subscribe("policy:invalidate")
            await asyncio.sleep(0.05)  # allow SUBSCRIBE to register

            resp = await client.post(
                f"/api/v1/services/{svc_row.slug}/permissions",
                headers=auth_header(admin),
                json={"application_id": app_row.id},
            )
            assert resp.status_code == 201

            assert await _drain(ps, str(svc_row.id)), (
                "expected policy:invalidate broadcast with service_id payload"
            )
    finally:
        await sub.aclose()


async def test_idempotent_grant_does_not_publish(
    client, admin, app_row, svc_row, redis_url
):
    # First grant — should publish.
    await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id},
    )

    sub = Redis.from_url(redis_url, decode_responses=True)
    try:
        async with sub.pubsub() as ps:
            await ps.subscribe("policy:invalidate")
            await asyncio.sleep(0.05)

            # Second identical grant — idempotent path, should NOT publish.
            resp = await client.post(
                f"/api/v1/services/{svc_row.slug}/permissions",
                headers=auth_header(admin),
                json={"application_id": app_row.id},
            )
            assert resp.status_code == 200

            # Allow a small window; we want to confirm NO message arrives.
            saw = await _drain(ps, str(svc_row.id), timeout=0.3)
            assert not saw, "idempotent grant should not re-publish invalidation"
    finally:
        await sub.aclose()


async def test_revoke_publishes_policy_invalidate(
    client, admin, app_row, svc_row, redis_url
):
    # seed a grant
    await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id},
    )

    sub = Redis.from_url(redis_url, decode_responses=True)
    try:
        async with sub.pubsub() as ps:
            await ps.subscribe("policy:invalidate")
            await asyncio.sleep(0.05)

            resp = await client.delete(
                f"/api/v1/services/{svc_row.slug}/permissions/{app_row.id}",
                headers=auth_header(admin),
            )
            assert resp.status_code == 204

            assert await _drain(ps, str(svc_row.id))
    finally:
        await sub.aclose()


async def test_revoke_missing_grant_does_not_publish(
    client, admin, app_row, svc_row, redis_url
):
    sub = Redis.from_url(redis_url, decode_responses=True)
    try:
        async with sub.pubsub() as ps:
            await ps.subscribe("policy:invalidate")
            await asyncio.sleep(0.05)

            resp = await client.delete(
                f"/api/v1/services/{svc_row.slug}/permissions/{app_row.id}",
                headers=auth_header(admin),
            )
            assert resp.status_code == 204  # idempotent

            saw = await _drain(ps, str(svc_row.id), timeout=0.3)
            assert not saw, "revoke of non-existent grant should not publish"
    finally:
        await sub.aclose()
