import pytest

from mcpsys_shared.models import Application, User, UserRole, UserStatus

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as s:
        u = User(
            username="admin",
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
            username="viewer",
            password_hash=hash_password("p"),
            role=UserRole.viewer,
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


async def test_create_user_as_admin(client, admin):
    resp = await client.post(
        "/api/v1/users",
        headers=auth_header(admin),
        json={"username": "bob", "password": "secret123", "role": "operator"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "bob"
    assert body["role"] == "operator"
    assert "password_hash" not in body


async def test_create_user_as_viewer_forbidden(client, viewer):
    resp = await client.post(
        "/api/v1/users",
        headers=auth_header(viewer),
        json={"username": "bob", "password": "secret123", "role": "operator"},
    )
    assert resp.status_code == 403


async def test_list_users_as_admin(client, admin):
    resp = await client.get("/api/v1/users", headers=auth_header(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert any(u["username"] == "admin" for u in body["items"])


async def test_unauthenticated_rejected(client):
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 401


async def test_delete_user_as_admin(client, admin, viewer):
    resp = await client.delete(
        f"/api/v1/users/{viewer.id}",
        headers=auth_header(admin),
    )
    assert resp.status_code == 204
    listing = await client.get("/api/v1/users", headers=auth_header(admin))
    assert all(u["id"] != viewer.id for u in listing.json()["items"])


async def test_delete_self_forbidden(client, admin):
    resp = await client.delete(
        f"/api/v1/users/{admin.id}",
        headers=auth_header(admin),
    )
    assert resp.status_code == 400


async def test_delete_user_as_viewer_forbidden(client, admin, viewer):
    resp = await client.delete(
        f"/api/v1/users/{admin.id}",
        headers=auth_header(viewer),
    )
    assert resp.status_code == 403


async def test_delete_nonexistent_user(client, admin):
    resp = await client.delete(
        "/api/v1/users/999999",
        headers=auth_header(admin),
    )
    assert resp.status_code == 404


async def test_delete_user_with_applications_conflict(client, admin, viewer, session_factory):
    async with session_factory() as s:
        s.add(Application(name="user-app-1", owner_user_id=viewer.id))
        await s.commit()
    resp = await client.delete(
        f"/api/v1/users/{viewer.id}",
        headers=auth_header(admin),
    )
    assert resp.status_code == 409
