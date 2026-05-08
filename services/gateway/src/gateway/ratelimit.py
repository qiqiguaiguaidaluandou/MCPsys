import logging
import math
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


_LUA = """
local data = redis.call('HMGET', KEYS[1], 'tokens', 'updated_ms')
local tokens = tonumber(data[1]) or tonumber(ARGV[3])
local updated = tonumber(data[2]) or tonumber(ARGV[1])
local elapsed = math.max(0, tonumber(ARGV[1]) - updated)
tokens = math.min(
    tonumber(ARGV[3]),
    tokens + elapsed * tonumber(ARGV[2]) / 1000
)
local allowed = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated_ms', ARGV[1])
redis.call('PEXPIRE', KEYS[1], 60000)
return {allowed, tostring(tokens)}
"""


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: float
    retry_after_s: int


class TokenBucket:
    """Redis Lua-backed token bucket. burst = 2 × qps."""

    def __init__(self, redis) -> None:
        self._redis = redis

    async def check(self, key: str, *, qps: int | None) -> RateLimitResult:
        if qps is None:
            return RateLimitResult(allowed=True, remaining=float("inf"), retry_after_s=0)
        if qps == 0:
            # qps=0 directly blocks all. retry_after_s stays 0 — meaningless return (never tokens).
            return RateLimitResult(allowed=False, remaining=0.0, retry_after_s=0)

        burst = qps * 2
        now_ms = int(time.time() * 1000)
        try:
            res = await self._redis.eval(_LUA, 1, key, str(now_ms), str(qps), str(burst))
        except Exception as e:
            # redis unavailable / Lua exception → fail-open, don't block main path; spec §8 requires
            logger.warning("ratelimit eval failed, fail-open: %s", e)
            return RateLimitResult(allowed=True, remaining=float("inf"), retry_after_s=0)

        allowed_int, remaining_str = res
        remaining = float(remaining_str)
        allowed = bool(int(allowed_int))
        retry_after_s = 0 if allowed else max(1, math.ceil((1 - remaining) / qps))
        return RateLimitResult(allowed=allowed, remaining=remaining, retry_after_s=retry_after_s)
