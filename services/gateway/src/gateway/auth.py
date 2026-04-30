import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import bcrypt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mcpsys_shared.models import ApiKey, ApiKeyOwnerType

CACHE_PREFIX = "gw:apikey:"
NEGATIVE_TTL = 30  # cache "unknown" briefly to avoid hammering DB
TAG = "mcpk_"
PREFIX_LEN = 8


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
    return plaintext[len(TAG) : len(TAG) + PREFIX_LEN]


def _cache_key(prefix: str) -> str:
    return f"{CACHE_PREFIX}{prefix}"


def _plaintext_digest(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def _safe_checkpw(plaintext: str, hashed: str) -> bool:
    """bcrypt.checkpw raises ValueError on a malformed/corrupt hash. Treat as no-match."""
    try:
        return bcrypt.checkpw(plaintext.encode(), hashed.encode())
    except ValueError:
        return False


async def validate_api_key(
    plaintext: str,
    *,
    session_factory: async_sessionmaker[AsyncSession],
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
        # Constant-time compare against a SHA-256 of the plaintext (cache holds the digest,
        # not bcrypt) so the hot path is microseconds, not ~250ms of bcrypt per request.
        if hmac.compare_digest(_plaintext_digest(plaintext), data["digest"]):
            # Honor expiration even on cache hit so cache TTL is not the upper bound on
            # both expiration AND revocation latency. Revocation still has the cache-TTL lag.
            exp_iso = data.get("expires_at")
            if exp_iso is not None:
                exp = datetime.fromisoformat(exp_iso)
                if exp < datetime.now(UTC):
                    raise AuthError("expired key (cached)")
            return ResolvedKey(
                api_key_id=data["api_key_id"],
                application_id=data.get("application_id"),
                user_id=data.get("user_id"),
            )
        # Different plaintext within the same prefix bucket — fall through to DB.

    async with session_factory() as session:
        res = await session.execute(select(ApiKey).where(ApiKey.key_prefix == prefix))
        candidates = res.scalars().all()

    matched: ApiKey | None = None
    for k in candidates:
        if _safe_checkpw(plaintext, k.key_hash):
            matched = k
            break

    if matched is None:
        await redis.setex(ck, NEGATIVE_TTL, json.dumps({"ok": False}))
        raise AuthError("unknown key")

    if matched.revoked_at is not None:
        raise AuthError("revoked key")
    if matched.expires_at is not None and matched.expires_at < datetime.now(UTC):
        raise AuthError("expired key")

    application_id = (
        matched.owner_id if matched.owner_type == ApiKeyOwnerType.application else None
    )
    user_id = matched.owner_id if matched.owner_type == ApiKeyOwnerType.user else None

    payload = {
        "ok": True,
        "api_key_id": matched.id,
        "digest": _plaintext_digest(plaintext),
        "application_id": application_id,
        "user_id": user_id,
        "expires_at": matched.expires_at.isoformat() if matched.expires_at else None,
    }
    # If the key expires within the normal TTL window, shorten the cache lifetime so the
    # entry naturally falls off near expiry — the on-hit check above is the safety net.
    effective_ttl = ttl_seconds
    if matched.expires_at is not None:
        until_expiry = int((matched.expires_at - datetime.now(UTC)).total_seconds())
        if 0 < until_expiry < ttl_seconds:
            effective_ttl = until_expiry
    await redis.setex(ck, max(effective_ttl, 1), json.dumps(payload))

    return ResolvedKey(
        api_key_id=matched.id,
        application_id=application_id,
        user_id=user_id,
    )
