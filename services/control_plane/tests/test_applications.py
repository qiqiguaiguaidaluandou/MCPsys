import pytest

from mcpsys_shared.models import User, UserRole, UserStatus

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings


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


def auth_header(user):
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


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


async def test_list_applications(client, admin):
    await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "ops-agent"},
    )
    resp = await client.get("/api/v1/applications", headers=auth_header(admin))
    assert resp.status_code == 200
    names = [a["name"] for a in resp.json()["items"]]
    assert "ops-agent" in names


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
