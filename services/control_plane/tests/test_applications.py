import asyncio

import pytest
from redis.asyncio import Redis
from sqlalchemy import select

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings
from mcpsys_shared.models import (
    AuditEvent,
    McpService,
    ServicePermission,
    User,
    UserRole,
    UserStatus,
)


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as s:
        u = User(
            username="admin2",
            password_hash=hash_password("p"),
            role=UserRole.admin,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


@pytest.fixture
async def services(session_factory):
    """Two registered services available for grant in this test module."""
    async with session_factory() as s:
        svc_a = McpService(slug="svc-a", display_name="A", endpoint_url="http://a/mcp")
        svc_b = McpService(slug="svc-b", display_name="B", endpoint_url="http://b/mcp")
        s.add_all([svc_a, svc_b])
        await s.commit()
        await s.refresh(svc_a)
        await s.refresh(svc_b)
        return svc_a, svc_b


def auth_header(user):
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


async def _drain(pubsub, expected_data: str, timeout: float = 2.0) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
        if msg is not None and msg.get("data") == expected_data:
            return True
    return False


# --- create -----------------------------------------------------------------


async def test_create_application(client, admin):
    resp = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "billing-agent", "team": "finance", "description": "monthly billing"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "billing-agent"
    assert body["owner_user_id"] == admin.id
    assert body["service_ids"] == []


async def test_create_application_with_service_ids(client, admin, services, session_factory):
    svc_a, svc_b = services
    resp = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={
            "name": "multi-svc-agent",
            "service_ids": [svc_a.id, svc_b.id],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert sorted(body["service_ids"]) == sorted([svc_a.id, svc_b.id])

    async with session_factory() as s:
        rows = (
            await s.execute(
                select(ServicePermission).where(
                    ServicePermission.application_id == body["id"]
                )
            )
        ).scalars().all()
    assert sorted(r.service_id for r in rows) == sorted([svc_a.id, svc_b.id])
    # granted_by tracks the actor of the last edit (here: create)
    assert all(r.granted_by == admin.id for r in rows)


async def test_create_rejects_unknown_service_id(client, admin):
    resp = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "bad-svc-agent", "service_ids": [99999]},
    )
    assert resp.status_code == 400
    # The application must NOT have been created (validation runs before insert,
    # but even if it had been we should not see it persist).
    listing = await client.get("/api/v1/applications", headers=auth_header(admin))
    assert all(a["name"] != "bad-svc-agent" for a in listing.json()["items"])


async def test_list_applications_includes_service_ids(client, admin, services):
    svc_a, _svc_b = services
    await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "ops-agent", "service_ids": [svc_a.id]},
    )
    resp = await client.get("/api/v1/applications", headers=auth_header(admin))
    assert resp.status_code == 200
    target = next(a for a in resp.json()["items"] if a["name"] == "ops-agent")
    assert target["service_ids"] == [svc_a.id]


async def test_create_duplicate_name_conflict(client, admin):
    await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "dup-app"},
    )
    resp = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "dup-app"},
    )
    assert resp.status_code == 409


# --- detail / update --------------------------------------------------------


async def test_get_application_detail(client, admin, services):
    svc_a, _ = services
    create = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "detail-app", "service_ids": [svc_a.id]},
    )
    app_id = create.json()["id"]
    resp = await client.get(f"/api/v1/applications/{app_id}", headers=auth_header(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == app_id
    assert body["service_ids"] == [svc_a.id]


async def test_get_unknown_application_is_404(client, admin):
    resp = await client.get("/api/v1/applications/999999", headers=auth_header(admin))
    assert resp.status_code == 404


async def test_update_scalar_fields_preserves_service_ids(client, admin, services):
    svc_a, _ = services
    create = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "patch-scalar", "team": "x", "service_ids": [svc_a.id]},
    )
    app_id = create.json()["id"]
    # PATCH without service_ids must NOT touch the grant list
    resp = await client.patch(
        f"/api/v1/applications/{app_id}",
        headers=auth_header(admin),
        json={"team": "y"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["team"] == "y"
    assert body["service_ids"] == [svc_a.id]


async def test_update_replaces_service_ids(client, admin, services, session_factory):
    svc_a, svc_b = services
    create = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "patch-svcs", "service_ids": [svc_a.id]},
    )
    app_id = create.json()["id"]

    # Replace [a] -> [b]: should remove a, add b
    resp = await client.patch(
        f"/api/v1/applications/{app_id}",
        headers=auth_header(admin),
        json={"service_ids": [svc_b.id]},
    )
    assert resp.status_code == 200
    assert resp.json()["service_ids"] == [svc_b.id]

    async with session_factory() as s:
        rows = (
            await s.execute(
                select(ServicePermission).where(
                    ServicePermission.application_id == app_id
                )
            )
        ).scalars().all()
    assert [r.service_id for r in rows] == [svc_b.id]


async def test_update_clears_service_ids_with_empty_list(client, admin, services):
    svc_a, svc_b = services
    create = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "patch-clear", "service_ids": [svc_a.id, svc_b.id]},
    )
    app_id = create.json()["id"]
    resp = await client.patch(
        f"/api/v1/applications/{app_id}",
        headers=auth_header(admin),
        json={"service_ids": []},
    )
    assert resp.status_code == 200
    assert resp.json()["service_ids"] == []


async def test_update_rejects_unknown_service_id(client, admin, services):
    svc_a, _ = services
    create = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "patch-bad", "service_ids": [svc_a.id]},
    )
    app_id = create.json()["id"]
    resp = await client.patch(
        f"/api/v1/applications/{app_id}",
        headers=auth_header(admin),
        json={"service_ids": [svc_a.id, 99999]},
    )
    assert resp.status_code == 400


# --- audit ------------------------------------------------------------------


async def test_audit_application_create(client, admin, services, session_factory):
    svc_a, _ = services
    resp = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "audit-app", "team": "ops", "service_ids": [svc_a.id]},
    )
    assert resp.status_code == 201
    app_id = resp.json()["id"]
    async with session_factory() as s:
        r = (
            await s.execute(
                select(AuditEvent).where(AuditEvent.action == "application.create")
            )
        ).scalar_one()
    assert r.target_type == "application"
    assert r.target_id == str(app_id)
    assert r.before is None
    assert r.after["name"] == "audit-app"
    assert r.after["service_ids"] == [svc_a.id]
    assert r.actor_user_id == admin.id


async def test_audit_application_update_records_service_diff(
    client, admin, services, session_factory
):
    svc_a, svc_b = services
    create = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "audit-patch", "service_ids": [svc_a.id]},
    )
    app_id = create.json()["id"]
    resp = await client.patch(
        f"/api/v1/applications/{app_id}",
        headers=auth_header(admin),
        json={"service_ids": [svc_a.id, svc_b.id], "team": "renamed"},
    )
    assert resp.status_code == 200

    async with session_factory() as s:
        r = (
            await s.execute(
                select(AuditEvent).where(AuditEvent.action == "application.update")
            )
        ).scalar_one()
    assert r.target_id == str(app_id)
    assert r.before["service_ids"] == [svc_a.id]
    assert r.after["service_ids"] == sorted([svc_a.id, svc_b.id])
    assert r.before.get("team") != r.after.get("team")
    assert r.after["team"] == "renamed"


# --- pubsub: invalidation must follow commit --------------------------------


async def test_create_publishes_policy_invalidate(
    client, admin, services, redis_url
):
    svc_a, _ = services
    sub = Redis.from_url(redis_url, decode_responses=True)
    try:
        async with sub.pubsub() as ps:
            await ps.subscribe("policy:invalidate")
            await asyncio.sleep(0.05)

            resp = await client.post(
                "/api/v1/applications",
                headers=auth_header(admin),
                json={"name": "pub-create", "service_ids": [svc_a.id]},
            )
            assert resp.status_code == 201

            assert await _drain(ps, str(svc_a.id))
    finally:
        await sub.aclose()


async def test_update_publishes_for_added_and_removed_only(
    client, admin, services, redis_url
):
    svc_a, svc_b = services
    create = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "pub-update", "service_ids": [svc_a.id]},
    )
    app_id = create.json()["id"]

    sub = Redis.from_url(redis_url, decode_responses=True)
    try:
        async with sub.pubsub() as ps:
            await ps.subscribe("policy:invalidate")
            await asyncio.sleep(0.05)

            # replace [a] -> [b]: invalidate both a (removed) and b (added)
            resp = await client.patch(
                f"/api/v1/applications/{app_id}",
                headers=auth_header(admin),
                json={"service_ids": [svc_b.id]},
            )
            assert resp.status_code == 200

            saw_a = await _drain(ps, str(svc_a.id))
            saw_b = await _drain(ps, str(svc_b.id))
            assert saw_a and saw_b
    finally:
        await sub.aclose()


async def test_update_with_unchanged_service_ids_does_not_publish(
    client, admin, services, redis_url
):
    svc_a, _ = services
    create = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "pub-noop", "service_ids": [svc_a.id]},
    )
    app_id = create.json()["id"]

    sub = Redis.from_url(redis_url, decode_responses=True)
    try:
        async with sub.pubsub() as ps:
            await ps.subscribe("policy:invalidate")
            await asyncio.sleep(0.05)

            # PATCH same set — diff is empty, must not invalidate.
            resp = await client.patch(
                f"/api/v1/applications/{app_id}",
                headers=auth_header(admin),
                json={"service_ids": [svc_a.id]},
            )
            assert resp.status_code == 200

            saw = await _drain(ps, str(svc_a.id), timeout=0.3)
            assert not saw
    finally:
        await sub.aclose()


async def test_publish_happens_after_commit(
    client, admin, services, redis_url, session_factory
):
    """Regression: publish must happen *after* commit, so a listener that reloads
    from a fresh DB connection sees the new row. Pre-fix bug published inside
    the transaction; another connection reloading immediately would miss the row."""
    svc_a, _ = services
    sub = Redis.from_url(redis_url, decode_responses=True)
    try:
        async with sub.pubsub() as ps:
            await ps.subscribe("policy:invalidate")
            await asyncio.sleep(0.05)

            resp = await client.post(
                "/api/v1/applications",
                headers=auth_header(admin),
                json={"name": "pub-commit-order", "service_ids": [svc_a.id]},
            )
            assert resp.status_code == 201
            app_id = resp.json()["id"]

            assert await _drain(ps, str(svc_a.id))

            async with session_factory() as fresh:
                rows = (
                    await fresh.execute(
                        select(ServicePermission).where(
                            ServicePermission.application_id == app_id,
                            ServicePermission.service_id == svc_a.id,
                        )
                    )
                ).scalars().all()
            assert len(rows) == 1, (
                "broadcast was published before commit — fresh reader missed the row"
            )
    finally:
        await sub.aclose()
