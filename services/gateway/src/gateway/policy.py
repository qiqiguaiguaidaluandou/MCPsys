import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mcpsys_shared.models import ServicePermission


@dataclass
class _Entry:
    allow_set: frozenset[int]
    expires_at: float


class PolicyCache:
    """Per-process service_id → frozenset[application_id] cache.

    On miss / expiry, reloads the *entire* allow set for one service in a single
    SELECT. Default-deny: app_id not in the set ⇒ False. application_id == None
    (user-owned key, not yet bound to an application) ⇒ always False — by V1-A
    design only application subjects are grantable."""

    def __init__(
        self, *, session_factory: async_sessionmaker[AsyncSession], ttl_seconds: int = 30
    ) -> None:
        self._sf = session_factory
        self._ttl = ttl_seconds
        self._cache: dict[int, _Entry] = {}

    def invalidate(self, *, service_id: int | None = None) -> None:
        if service_id is None:
            self._cache.clear()
        else:
            self._cache.pop(service_id, None)

    async def is_allowed(self, *, application_id: int | None, service_id: int) -> bool:
        if application_id is None:
            return False

        now = time.monotonic()
        entry = self._cache.get(service_id)
        if entry is None or entry.expires_at <= now:
            entry = await self._load(service_id, now)

        return application_id in entry.allow_set

    async def _load(self, service_id: int, now: float) -> _Entry:
        async with self._sf() as session:
            res = await session.execute(
                select(ServicePermission.application_id).where(
                    ServicePermission.service_id == service_id
                )
            )
            allow = frozenset(res.scalars().all())
        entry = _Entry(allow_set=allow, expires_at=now + self._ttl)
        self._cache[service_id] = entry
        return entry
