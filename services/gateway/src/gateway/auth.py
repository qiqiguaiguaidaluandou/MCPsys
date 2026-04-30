import json
from dataclasses import dataclass
from datetime import UTC, datetime

import bcrypt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from mcpsys_shared.models import ApiKey, ApiKeyOwnerType

CACHE_PREFIX = "gw:apikey:"
NEGATIVE_TTL = 30  # cache "unknown" briefly to avoid hammering DB
TAG = "mcpk_"


class AuthError(Exception):
    pass


@dataclass
class ResolvedKey:
    api_key_id: int
    application_id: int | None
    user_id: int | None


def _extract_prefix(plaintext: str) -> str:
    if not plaintext.startswith(TAG):
        raise AuthError("malformed key")
    return plaintext[len(TAG) : len(TAG) + 8]


def _cache_key(prefix: str) -> str:
    return f"{CACHE_PREFIX}{prefix}"


async def validate_api_key(
    plaintext: str,
    *,
    session_factory: async_sessionmaker,
    redis: Redis,
    ttl_seconds: int = 60,
) -> ResolvedKey:
    prefix = _extract_prefix(plaintext)
    ck = _cache_key(prefix)

    cached = await redis.get(ck)
    if cached is not None:
        data = json.loads(cached)
        if data.get("ok") is False:
            raise AuthError("unknown key (cached)")
        # re-verify against the cached hash to ensure correct key matched (collision unlikely
        # but plaintext may differ within same prefix bucket)
        if bcrypt.checkpw(plaintext.encode(), data["hash"].encode()):
            return ResolvedKey(
                api_key_id=data["api_key_id"],
                application_id=data.get("application_id"),
                user_id=data.get("user_id"),
            )

    async with session_factory() as session:
        res = await session.execute(select(ApiKey).where(ApiKey.key_prefix == prefix))
        candidates = res.scalars().all()

    matched: ApiKey | None = None
    for k in candidates:
        if bcrypt.checkpw(plaintext.encode(), k.key_hash.encode()):
            matched = k
            break

    if matched is None:
        await redis.setex(ck, NEGATIVE_TTL, json.dumps({"ok": False}))
        raise AuthError("unknown key")

    if matched.revoked_at is not None:
        raise AuthError("revoked key")
    if matched.expires_at is not None and matched.expires_at < datetime.now(UTC):
        raise AuthError("expired key")

    payload = {
        "ok": True,
        "api_key_id": matched.id,
        "hash": matched.key_hash,
        "application_id": (
            matched.owner_id if matched.owner_type == ApiKeyOwnerType.application else None
        ),
        "user_id": matched.owner_id if matched.owner_type == ApiKeyOwnerType.user else None,
    }
    await redis.setex(ck, ttl_seconds, json.dumps(payload))

    return ResolvedKey(
        api_key_id=matched.id,
        application_id=payload["application_id"],
        user_id=payload["user_id"],
    )
