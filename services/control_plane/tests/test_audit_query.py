from datetime import UTC, datetime, timedelta

import pytest
from mcpsys_shared.models import AuditEvent, User, UserRole, UserStatus

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings


def auth_header(user):
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as s:
        u = User(username="admin", password_hash=hash_password("p"), role=UserRole.admin, status=UserStatus.active)
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


@pytest.fixture
async def viewer(session_factory):
    async with session_factory() as s:
        u = User(username="viewer", password_hash=hash_password("p"), role=UserRole.viewer, status=UserStatus.active)
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


@pytest.fixture
async def seed_events(session_factory, admin):
    """填 5 条混合 audit_events 用于查询测试。"""
    now = datetime.now(UTC)
    async with session_factory() as s:
        s.add_all([
            AuditEvent(actor_user_id=admin.id, action="user.create", target_type="user", target_id="10",
                       before=None, after={"id": 10}, ts=now - timedelta(minutes=5)),
            AuditEvent(actor_user_id=admin.id, action="service.create", target_type="mcp_service", target_id="20",
                       before=None, after={"slug": "a"}, ts=now - timedelta(minutes=4)),
            AuditEvent(actor_user_id=admin.id, action="service.update", target_type="mcp_service", target_id="20",
                       before={"slug": "a"}, after={"slug": "b"}, ts=now - timedelta(minutes=3)),
            AuditEvent(actor_user_id=admin.id, action="user.delete", target_type="user", target_id="10",
                       before={"id": 10}, after=None, ts=now - timedelta(minutes=2)),
            AuditEvent(actor_user_id=admin.id, action="application.create", target_type="application", target_id="30",
                       before=None, after={"name": "x"}, ts=now - timedelta(minutes=1)),
        ])
        await s.commit()


async def test_unauthenticated(client):
    resp = await client.get("/api/v1/audit-events")
    assert resp.status_code == 401


async def test_viewer_forbidden(client, viewer):
    resp = await client.get("/api/v1/audit-events", headers=auth_header(viewer))
    assert resp.status_code == 403


async def test_admin_lists_all_desc(client, admin, seed_events):
    resp = await client.get("/api/v1/audit-events", headers=auth_header(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    actions = [it["action"] for it in body["items"]]
    assert actions == [
        "application.create", "user.delete", "service.update", "service.create", "user.create",
    ]


async def test_filter_action(client, admin, seed_events):
    resp = await client.get(
        "/api/v1/audit-events",
        headers=auth_header(admin),
        params={"action": "service.update"},
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["action"] == "service.update"


async def test_filter_target(client, admin, seed_events):
    resp = await client.get(
        "/api/v1/audit-events",
        headers=auth_header(admin),
        params={"target_type": "mcp_service", "target_id": "20"},
    )
    body = resp.json()
    assert body["total"] == 2
    assert {it["action"] for it in body["items"]} == {"service.create", "service.update"}


async def test_filter_time_window(client, admin, seed_events):
    """from_ts 卡到 user.delete + application.create，期望剩 2。"""
    now = datetime.now(UTC)
    resp = await client.get(
        "/api/v1/audit-events",
        headers=auth_header(admin),
        params={"from_ts": (now - timedelta(minutes=2, seconds=30)).isoformat()},
    )
    body = resp.json()
    assert body["total"] == 2


async def test_pagination(client, admin, seed_events):
    p1 = await client.get(
        "/api/v1/audit-events",
        headers=auth_header(admin),
        params={"page_size": 2, "page": 1},
    )
    p2 = await client.get(
        "/api/v1/audit-events",
        headers=auth_header(admin),
        params={"page_size": 2, "page": 2},
    )
    p3 = await client.get(
        "/api/v1/audit-events",
        headers=auth_header(admin),
        params={"page_size": 2, "page": 3},
    )
    assert p1.json()["total"] == 5
    assert len(p1.json()["items"]) == 2
    assert len(p2.json()["items"]) == 2
    assert len(p3.json()["items"]) == 1


async def test_page_size_over_max_rejected(client, admin):
    resp = await client.get(
        "/api/v1/audit-events",
        headers=auth_header(admin),
        params={"page_size": 500},
    )
    assert resp.status_code == 422
