import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mcpsys_shared.models import McpService, ServiceStatus


class ServiceNotFound(Exception):
    pass


@dataclass
class ResolvedService:
    service_id: int
    slug: str
    endpoint_url: str
    transport: str


class ServiceResolver:
    """Slug → service info, with simple per-process TTL cache.

    External invalidation should call `invalidate(slug)` (driven by control plane
    via redis pub/sub in a future task)."""

    def __init__(
        self, *, session_factory: async_sessionmaker[AsyncSession], ttl_seconds: int = 60
    ) -> None:
        self._sf = session_factory
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, ResolvedService]] = {}

    def invalidate(self, slug: str | None = None) -> None:
        if slug is None:
            self._cache.clear()
        else:
            self._cache.pop(slug, None)

    async def resolve(self, slug: str) -> ResolvedService:
        now = time.monotonic()
        hit = self._cache.get(slug)
        if hit and hit[0] > now:
            return hit[1]

        async with self._sf() as session:
            res = await session.execute(select(McpService).where(McpService.slug == slug))
            svc = res.scalar_one_or_none()

        if svc is None or svc.status != ServiceStatus.active:
            raise ServiceNotFound(slug)

        info = ResolvedService(
            service_id=svc.id,
            slug=svc.slug,
            endpoint_url=svc.endpoint_url,
            transport=svc.transport.value,
        )
        self._cache[slug] = (now + self._ttl, info)
        return info
