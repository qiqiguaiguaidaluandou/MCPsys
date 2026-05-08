import pytest
from sqlalchemy import select

from mcpsys_shared.models import Application, McpService, ServicePermission, User, UserRole
from gateway.policy import PolicyCache


@pytest.fixture
async def setup_perm(session_factory):
    async with session_factory() as s:
        admin = User(username="pa", password_hash="x", role=UserRole.admin)
        s.add(admin)
        await s.flush()
        app = Application(name="pa-app", owner_user_id=admin.id)
        s.add(app)
        svc = McpService(slug="pa-svc", display_name="P", endpoint_url="http://p/mcp")
        s.add(svc)
        await s.flush()
        s.add(ServicePermission(application_id=app.id, service_id=svc.id, granted_by=admin.id))
        await s.commit()
        await s.refresh(app)
        await s.refresh(svc)
        return app.id, svc.id


async def test_allowed(session_factory, setup_perm):
    app_id, svc_id = setup_perm
    cache = PolicyCache(session_factory=session_factory, ttl_seconds=30)
    assert await cache.is_allowed(application_id=app_id, service_id=svc_id) is True


async def test_denied_when_no_grant(session_factory, setup_perm):
    _, svc_id = setup_perm
    cache = PolicyCache(session_factory=session_factory, ttl_seconds=30)
    assert await cache.is_allowed(application_id=99999, service_id=svc_id) is False


async def test_denied_when_application_id_none(session_factory, setup_perm):
    _, svc_id = setup_perm
    cache = PolicyCache(session_factory=session_factory, ttl_seconds=30)
    assert await cache.is_allowed(application_id=None, service_id=svc_id) is False


async def test_cache_hit_avoids_db(session_factory, setup_perm):
    app_id, svc_id = setup_perm
    cache = PolicyCache(session_factory=session_factory, ttl_seconds=30)
    await cache.is_allowed(application_id=app_id, service_id=svc_id)

    # Drop the row directly so DB now says "not allowed". Cache should still say allowed.
    async with session_factory() as s:
        rows = (await s.execute(select(ServicePermission))).scalars().all()
        for r in rows:
            await s.delete(r)
        await s.commit()

    assert await cache.is_allowed(application_id=app_id, service_id=svc_id) is True


async def test_cache_expires(session_factory, setup_perm):
    app_id, svc_id = setup_perm
    cache = PolicyCache(session_factory=session_factory, ttl_seconds=0)  # immediate expiry
    await cache.is_allowed(application_id=app_id, service_id=svc_id)
    # remove grant
    async with session_factory() as s:
        rows = (await s.execute(select(ServicePermission))).scalars().all()
        for r in rows:
            await s.delete(r)
        await s.commit()
    assert await cache.is_allowed(application_id=app_id, service_id=svc_id) is False


async def test_invalidate_clears_service_entry(session_factory, setup_perm):
    app_id, svc_id = setup_perm
    cache = PolicyCache(session_factory=session_factory, ttl_seconds=300)
    await cache.is_allowed(application_id=app_id, service_id=svc_id)
    cache.invalidate(service_id=svc_id)
    assert svc_id not in cache._cache  # type: ignore[attr-defined]
