import asyncio
import contextlib
import logging

from redis.asyncio import Redis

from .policy import PolicyCache
from .resolver import ServiceResolver

logger = logging.getLogger(__name__)

POLICY_CHANNEL = "policy:invalidate"
SERVICE_CHANNEL = "service:invalidate"


class InvalidationListener:
    """Subscribes to control-plane invalidation broadcasts and clears caches.

    Channel contract:
      - "policy:invalidate"  payload = "<service_id>" or "" → PolicyCache.invalidate
      - "service:invalidate" payload = "<slug>" or ""        → ServiceResolver.invalidate

    Best-effort: malformed payloads are logged and skipped so the loop keeps running."""

    def __init__(
        self,
        *,
        redis: Redis,
        policy: PolicyCache,
        resolver: ServiceResolver,
        poll_timeout: float = 1.0,
    ) -> None:
        self._redis = redis
        self._policy = policy
        self._resolver = resolver
        self._poll_timeout = poll_timeout
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="invalidation-listener")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._task
        self._task = None

    async def _run(self) -> None:
        async with self._redis.pubsub() as ps:
            await ps.subscribe(POLICY_CHANNEL, SERVICE_CHANNEL)
            while True:
                msg = await ps.get_message(
                    ignore_subscribe_messages=True, timeout=self._poll_timeout
                )
                if msg is None:
                    continue
                self._dispatch(msg.get("channel"), msg.get("data"))

    def _dispatch(self, channel: str | None, data: str | None) -> None:
        if channel == POLICY_CHANNEL:
            try:
                service_id = int(data) if data else None
            except (TypeError, ValueError):
                logger.warning("invalidator: bad policy payload %r", data)
                return
            self._policy.invalidate(service_id=service_id)
        elif channel == SERVICE_CHANNEL:
            slug = data if data else None
            self._resolver.invalidate(slug=slug)
