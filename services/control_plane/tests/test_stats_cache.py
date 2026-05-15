"""Cache layer (spec §3.4 / §6.2)：x-cache 头 + Redis 不可用 graceful degrade。"""
import pytest
from mcpsys_shared.models import User, UserRole, UserStatus

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as s:
        u = User(
            username="cache-admin",
            password_hash=hash_password("p"),
            role=UserRole.admin,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


def auth_header(user: User) -> dict:
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


# ---------- 基础：第一次 miss，第二次 hit ----------


async def test_overview_first_miss_then_hit(client, admin):
    r1 = await client.get(
        "/api/v1/stats/overview?range=24h", headers=auth_header(admin)
    )
    assert r1.status_code == 200
    assert r1.headers.get("x-cache") == "miss"

    r2 = await client.get(
        "/api/v1/stats/overview?range=24h", headers=auth_header(admin)
    )
    assert r2.status_code == 200
    assert r2.headers.get("x-cache") == "hit"
    assert r1.json() == r2.json()


async def test_timeseries_caches(client, admin):
    url = "/api/v1/stats/timeseries?metric=calls&range=1h"
    r1 = await client.get(url, headers=auth_header(admin))
    r2 = await client.get(url, headers=auth_header(admin))
    assert r1.headers["x-cache"] == "miss"
    assert r2.headers["x-cache"] == "hit"


async def test_breakdown_caches(client, admin):
    url = "/api/v1/stats/breakdown?dim=service&range=24h"
    r1 = await client.get(url, headers=auth_header(admin))
    r2 = await client.get(url, headers=auth_header(admin))
    assert r1.headers["x-cache"] == "miss"
    assert r2.headers["x-cache"] == "hit"


async def test_latency_histogram_caches(client, admin):
    url = "/api/v1/stats/latency-histogram?range=24h"
    r1 = await client.get(url, headers=auth_header(admin))
    r2 = await client.get(url, headers=auth_header(admin))
    assert r1.headers["x-cache"] == "miss"
    assert r2.headers["x-cache"] == "hit"


# ---------- TTL：15m 窗口 10s；其它 30s ----------


async def test_overview_15m_uses_10s_ttl(client, admin, redis_client):
    await client.get(
        "/api/v1/stats/overview?range=15m", headers=auth_header(admin)
    )
    ttl = await redis_client.ttl("stats:overview:15m:none")
    # Redis TTL 单位是秒；允许 1 秒的边界容差
    assert 8 <= ttl <= 10


async def test_overview_24h_uses_30s_ttl(client, admin, redis_client):
    await client.get(
        "/api/v1/stats/overview?range=24h", headers=auth_header(admin)
    )
    ttl = await redis_client.ttl("stats:overview:24h:none")
    assert 28 <= ttl <= 30


# ---------- cache key 区分参数 ----------


async def test_cache_key_disjoint_by_filter(client, admin):
    """不同 filter 不应互相命中对方缓存。"""
    r1 = await client.get(
        "/api/v1/stats/overview?range=24h", headers=auth_header(admin)
    )
    assert r1.headers["x-cache"] == "miss"
    # 加 filter 后是新 key → 仍 miss
    r2 = await client.get(
        "/api/v1/stats/overview?range=24h&service_id=42", headers=auth_header(admin)
    )
    assert r2.headers["x-cache"] == "miss"
    # 重复带 filter → hit
    r3 = await client.get(
        "/api/v1/stats/overview?range=24h&service_id=42", headers=auth_header(admin)
    )
    assert r3.headers["x-cache"] == "hit"


async def test_cache_key_disjoint_by_range(client, admin):
    r1h = await client.get(
        "/api/v1/stats/overview?range=1h", headers=auth_header(admin)
    )
    r24h = await client.get(
        "/api/v1/stats/overview?range=24h", headers=auth_header(admin)
    )
    assert r1h.headers["x-cache"] == "miss"
    assert r24h.headers["x-cache"] == "miss"


# ---------- Graceful degrade ----------


class _BrokenRedis:
    """假装是 Redis：所有读写都抛错。cache_or_compute 应该吞掉并降级为 bypass。"""

    async def get(self, *_args, **_kwargs):
        raise ConnectionError("simulated redis down")

    async def setex(self, *_args, **_kwargs):
        raise ConnectionError("simulated redis down")


async def test_bypass_when_redis_raises(client, admin, app):
    original = app.state.redis
    app.state.redis = _BrokenRedis()
    try:
        resp = await client.get(
            "/api/v1/stats/overview?range=24h", headers=auth_header(admin)
        )
        assert resp.status_code == 200
        assert resp.headers["x-cache"] == "bypass"
    finally:
        app.state.redis = original


async def test_bypass_when_redis_none(client, admin, app):
    original = app.state.redis
    app.state.redis = None
    try:
        resp = await client.get(
            "/api/v1/stats/overview?range=24h", headers=auth_header(admin)
        )
        assert resp.status_code == 200
        assert resp.headers["x-cache"] == "bypass"
    finally:
        app.state.redis = original
