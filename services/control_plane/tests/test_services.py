import pytest

from mcpsys_shared.models import User, UserRole, UserStatus

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings


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
