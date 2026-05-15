"""Service-permission *read-only* endpoints.

Grants are now managed exclusively from the application side (see
test_applications.py for create / update / publish-on-commit / audit tests).
This file covers only the two GET endpoints and the absence of the legacy
write endpoints.
"""

import pytest
from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings
from mcpsys_shared.models import (
    Application,
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


@pytest.fixture
async def existing_permission(session_factory, app_row, svc_row, admin):
    async with session_factory() as s:
        perm = ServicePermission(
            application_id=app_row.id,
            service_id=svc_row.id,
            granted_by=admin.id,
        )
        s.add(perm)
        await s.commit()
        await s.refresh(perm)
        return perm


def auth_header(user):
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


async def test_list_service_permissions(client, admin, existing_permission, svc_row, app_row):
    resp = await client.get(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(it["application_id"] == app_row.id for it in items)
    # note column was dropped — response must not surface it
    assert all("note" not in it for it in items)


async def test_list_application_permissions(client, admin, existing_permission, svc_row, app_row):
    resp = await client.get(
        f"/api/v1/applications/{app_row.id}/permissions",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(it["service_id"] == svc_row.id for it in items)


async def test_viewer_can_read_service_permissions(
    client, viewer, existing_permission, svc_row, app_row
):
    resp = await client.get(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(viewer),
    )
    assert resp.status_code == 200
    assert any(it["application_id"] == app_row.id for it in resp.json()["items"])


async def test_list_unknown_service_is_404(client, admin):
    resp = await client.get(
        "/api/v1/services/no-such-svc/permissions",
        headers=auth_header(admin),
    )
    assert resp.status_code == 404


async def test_legacy_grant_endpoint_removed(client, admin, svc_row, app_row):
    """POST /services/{slug}/permissions is no longer registered."""
    resp = await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id},
    )
    assert resp.status_code in (404, 405)


async def test_legacy_revoke_endpoint_removed(client, admin, svc_row, app_row):
    """DELETE /services/{slug}/permissions/{id} is no longer registered."""
    resp = await client.delete(
        f"/api/v1/services/{svc_row.slug}/permissions/{app_row.id}",
        headers=auth_header(admin),
    )
    assert resp.status_code in (404, 405)
