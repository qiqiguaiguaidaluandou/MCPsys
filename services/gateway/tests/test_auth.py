import pytest
from redis.asyncio import Redis

from mcpsys_shared.models import ApiKey, ApiKeyOwnerType, Application, User, UserRole

from gateway.auth import AuthError, ResolvedKey, validate_api_key


def hash_plain(plain: str) -> str:
    import bcrypt
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


@pytest.fixture
async def redis(redis_url):
    r = Redis.from_url(redis_url, decode_responses=True)
    await r.flushdb()
    yield r
    await r.aclose()


@pytest.fixture
async def seed_key(session_factory):
    async with session_factory() as s:
        u = User(username="owner", role=UserRole.viewer)
        s.add(u)
        await s.flush()
        a = Application(name="seed-app", owner_user_id=u.id)
        s.add(a)
        await s.flush()
        plain = "mcpk_testkey_abc"
        k = ApiKey(
            name="t",
            key_prefix=plain[5:13],
            key_hash=hash_plain(plain),
            owner_type=ApiKeyOwnerType.application,
            owner_id=a.id,
        )
        s.add(k)
        await s.commit()
        await s.refresh(k)
        return plain, k.id, a.id


async def test_validate_known_key(session_factory, redis, seed_key):
    plain, key_id, app_id = seed_key
    resolved = await validate_api_key(plain, session_factory=session_factory, redis=redis)
    assert isinstance(resolved, ResolvedKey)
    assert resolved.api_key_id == key_id
    assert resolved.application_id == app_id


async def test_validate_unknown_key_raises(session_factory, redis):
    with pytest.raises(AuthError):
        await validate_api_key(
            "mcpk_doesnotexist_x", session_factory=session_factory, redis=redis
        )


async def test_revoked_key_raises(session_factory, redis, seed_key):
    plain, key_id, _ = seed_key
    from datetime import UTC, datetime

    from sqlalchemy import select
    from mcpsys_shared.models import ApiKey

    async with session_factory() as s:
        res = await s.execute(select(ApiKey).where(ApiKey.id == key_id))
        k = res.scalar_one()
        k.revoked_at = datetime.now(UTC)
        await s.commit()

    # bypass cache for this test
    await redis.flushdb()
    with pytest.raises(AuthError):
        await validate_api_key(plain, session_factory=session_factory, redis=redis)


async def test_cache_returns_same_result(session_factory, redis, seed_key):
    plain, key_id, _ = seed_key
    r1 = await validate_api_key(plain, session_factory=session_factory, redis=redis)
    r2 = await validate_api_key(plain, session_factory=session_factory, redis=redis)
    assert r1.api_key_id == r2.api_key_id == key_id
