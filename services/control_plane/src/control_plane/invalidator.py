import logging

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

POLICY_CHANNEL = "policy:invalidate"
SERVICE_CHANNEL = "service:invalidate"


async def publish_policy_invalidate(redis: Redis | None, service_id: int) -> None:
    """Broadcast a single-service permission cache invalidation. Best-effort:
    a redis hiccup must not fail the API call."""
    if redis is None:
        return
    try:
        await redis.publish(POLICY_CHANNEL, str(service_id))
    except Exception as e:
        logger.warning("publish policy:invalidate(%s) failed: %s", service_id, e)


async def publish_service_invalidate(redis: Redis | None, slug: str) -> None:
    """Broadcast a single-service resolver cache invalidation."""
    if redis is None:
        return
    try:
        await redis.publish(SERVICE_CHANNEL, slug)
    except Exception as e:
        logger.warning("publish service:invalidate(%s) failed: %s", slug, e)
