import pytest

from mcpsys_shared.models import Application, User, UserRole, UserStatus

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings


@pytest.fixture
async def admin_and_app(session_factory):
    async with session_factory() as s:
        u = User(
            username="key-admin",
            password_hash=hash_password("p"),
            role=UserRole.admin,
            status=UserStatus.active,
        )
        s.add(u)
        await s.flush()
        a = Application(name="agent-x", owner_user_id=u.id)
        s.add(a)
        await s.commit()
        await s.refresh(u)
        await s.refresh(a)
        return u, a


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as s:
        u = User(
            username="qps-key-admin",
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


async def test_create_api_key_returns_plaintext_once(client, admin_and_app):
    admin, app_obj = admin_and_app
    resp = await client.post(
        "/api/v1/api-keys",
        headers=auth_header(admin),
        json={
            "name": "agent-x main",
            "owner_type": "application",
            "owner_id": app_obj.id,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["plaintext"].startswith("mcpk_")
    assert body["key_prefix"] and len(body["key_prefix"]) == 8
    assert body["id"]


async def test_list_api_keys_no_plaintext(client, admin_and_app):
    admin, app_obj = admin_and_app
    await client.post(
        "/api/v1/api-keys",
        headers=auth_header(admin),
        json={"name": "k1", "owner_type": "application", "owner_id": app_obj.id},
    )
    resp = await client.get("/api/v1/api-keys", headers=auth_header(admin))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all("plaintext" not in i for i in items)
    assert all("key_hash" not in i for i in items)
    assert any(i["name"] == "k1" for i in items)


async def test_revoke_api_key(client, admin_and_app):
    admin, app_obj = admin_and_app
    create = await client.post(
        "/api/v1/api-keys",
        headers=auth_header(admin),
        json={"name": "k2", "owner_type": "application", "owner_id": app_obj.id},
    )
    key_id = create.json()["id"]
    resp = await client.delete(f"/api/v1/api-keys/{key_id}", headers=auth_header(admin))
    assert resp.status_code == 204
    listing = await client.get("/api/v1/api-keys", headers=auth_header(admin))
    target = next(i for i in listing.json()["items"] if i["id"] == key_id)
    assert target["revoked_at"] is not None


async def test_permanent_delete_requires_revoke(client, admin_and_app):
    admin, app_obj = admin_and_app
    create = await client.post(
        "/api/v1/api-keys",
        headers=auth_header(admin),
        json={"name": "k3", "owner_type": "application", "owner_id": app_obj.id},
    )
    key_id = create.json()["id"]

    # active key: permanent delete refused
    refused = await client.delete(f"/api/v1/api-keys/{key_id}/permanent", headers=auth_header(admin))
    assert refused.status_code == 409

    # revoke first
    await client.delete(f"/api/v1/api-keys/{key_id}", headers=auth_header(admin))

    # now permanent delete succeeds
    deleted = await client.delete(f"/api/v1/api-keys/{key_id}/permanent", headers=auth_header(admin))
    assert deleted.status_code == 204

    listing = await client.get("/api/v1/api-keys", headers=auth_header(admin))
    assert all(i["id"] != key_id for i in listing.json()["items"])

    # second permanent delete: 404
    again = await client.delete(f"/api/v1/api-keys/{key_id}/permanent", headers=auth_header(admin))
    assert again.status_code == 404


async def test_create_api_key_with_qps(client, admin):
    # need an application to own the key
    app_resp = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "qps-key-app"},
    )
    assert app_resp.status_code == 201
    app_id = app_resp.json()["id"]

    resp = await client.post(
        "/api/v1/api-keys",
        headers=auth_header(admin),
        json={
            "name": "qps-key",
            "owner_type": "application",
            "owner_id": app_id,
            "rate_limit_qps": 10,
        },
    )
    assert resp.status_code == 201
    # ApiKeyCreated does not include rate_limit_qps; just verify create succeeded.
    key_id = resp.json()["id"]

    # Read back via list, find this key, confirm rate_limit_qps stored
    list_resp = await client.get("/api/v1/api-keys", headers=auth_header(admin))
    rows = [k for k in list_resp.json()["items"] if k["id"] == key_id]
    assert rows and rows[0]["rate_limit_qps"] == 10


async def test_patch_api_key_qps(client, admin):
    app_resp = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "qps-key-app2"},
    )
    app_id = app_resp.json()["id"]

    create_resp = await client.post(
        "/api/v1/api-keys",
        headers=auth_header(admin),
        json={"name": "k2", "owner_type": "application", "owner_id": app_id},
    )
    key_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/api-keys/{key_id}",
        headers=auth_header(admin),
        json={"rate_limit_qps": 7},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["rate_limit_qps"] == 7

    # Patch to null clears it
    clear_resp = await client.patch(
        f"/api/v1/api-keys/{key_id}",
        headers=auth_header(admin),
        json={"rate_limit_qps": None},
    )
    assert clear_resp.status_code == 200
    assert clear_resp.json()["rate_limit_qps"] is None
