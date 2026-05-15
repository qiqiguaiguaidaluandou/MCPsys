"""Read-side cache for `/api/v1/stats/*` endpoints (spec §3.4).

`call_logs` is append-only — TTL is the only invalidation. Redis hiccup must
*not* fail a stats request: a Redis error / Redis-down ⇒ silently bypass cache
and serve a live computation. This mirrors the resolver / policy degrade
pattern already used in gateway.
"""
import logging
from collections.abc import Awaitable, Callable
from typing import Literal, TypeVar

from pydantic import BaseModel
from redis.asyncio import Redis

from .schemas.stats import Range, StatsFilter

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

CacheStatus = Literal["hit", "miss", "bypass"]


def ttl_for(range_: Range) -> int:
    """spec §3.4：range=15m 时 TTL 缩短到 10s（窗口本身小，30s 失效会比窗口长
    2 倍，体验差）；其它窗口固定 30s。"""
    return 10 if range_ == "15m" else 30


def filter_key(filt: StatsFilter | None) -> str:
    """规范化 (service_id|application_id|api_key_id) → cache key 片段。
    顺序与 pick_filter 优先级一致；保证同一 filter 始终映射到同一字符串。"""
    if filt is None:
        return "none"
    if filt.service_id is not None:
        return f"svc={filt.service_id}"
    if filt.application_id is not None:
        return f"app={filt.application_id}"
    if filt.api_key_id is not None:
        return f"key={filt.api_key_id}"
    return "none"


async def cache_or_compute(
    redis: Redis | None,
    *,
    key: str,
    ttl: int,
    model_cls: type[T],
    compute: Callable[[], Awaitable[T]],
) -> tuple[T, CacheStatus]:
    """Read-through cache.

    Returns `(value, status)` where status ∈ {hit, miss, bypass}:
      - **hit**：Redis 命中且能反序列化 → 直接返回
      - **miss**：Redis 未命中 → 调 compute()，结果写回（写失败也无所谓）
      - **bypass**：redis 为 None 或 Redis 操作抛错 → 直接走 compute()，不写缓存

    任何 Redis 异常都被吞掉并降级；最差也只是退化到无缓存，不让请求失败。
    """
    if redis is None:
        return await compute(), "bypass"

    try:
        cached = await redis.get(key)
    except Exception as e:
        logger.debug("stats cache GET failed (%s): %s", key, e)
        return await compute(), "bypass"

    if cached is not None:
        try:
            return model_cls.model_validate_json(cached), "hit"
        except Exception as e:
            # 序列化格式漂移（升级后的旧缓存）—— 不抛，重算一次自动覆盖。
            logger.warning("stats cache deserialize failed (%s): %s", key, e)

    result = await compute()
    try:
        await redis.setex(key, ttl, result.model_dump_json())
    except Exception as e:
        logger.debug("stats cache SET failed (%s): %s", key, e)
    return result, "miss"
