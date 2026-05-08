import asyncio


async def test_check_passes_when_qps_none(redis_client):
    from gateway.ratelimit import TokenBucket

    bucket = TokenBucket(redis_client)
    res = await bucket.check("rl:test", qps=None)
    assert res.allowed is True
    assert res.retry_after_s == 0


async def test_check_passes_first_request(redis_client):
    from gateway.ratelimit import TokenBucket

    bucket = TokenBucket(redis_client)
    res = await bucket.check("rl:t1", qps=2)
    assert res.allowed is True


async def test_burst_allows_2x_then_blocks(redis_client):
    from gateway.ratelimit import TokenBucket

    bucket = TokenBucket(redis_client)
    # qps=1 → burst=2, so 2 immediate requests pass, 3rd fails
    r1 = await bucket.check("rl:burst", qps=1)
    r2 = await bucket.check("rl:burst", qps=1)
    r3 = await bucket.check("rl:burst", qps=1)
    assert r1.allowed and r2.allowed
    assert not r3.allowed
    assert r3.retry_after_s >= 1


async def test_qps_zero_always_blocks(redis_client):
    from gateway.ratelimit import TokenBucket

    bucket = TokenBucket(redis_client)
    res = await bucket.check("rl:zero", qps=0)
    assert res.allowed is False
    assert res.retry_after_s == 0  # no meaningful retry


async def test_redis_failure_fails_open():
    from gateway.ratelimit import TokenBucket

    class BrokenRedis:
        async def eval(self, *a, **kw):
            raise ConnectionError("boom")

    bucket = TokenBucket(BrokenRedis())
    res = await bucket.check("rl:broken", qps=1)
    assert res.allowed is True  # fail-open
    assert res.retry_after_s == 0


async def test_refill_after_wait(redis_client):
    from gateway.ratelimit import TokenBucket

    bucket = TokenBucket(redis_client)
    # qps=10 → refill 1 token every 100ms; burst=20
    for _ in range(20):  # exhaust burst
        await bucket.check("rl:refill", qps=10)
    blocked = await bucket.check("rl:refill", qps=10)
    assert not blocked.allowed
    await asyncio.sleep(0.25)
    refilled = await bucket.check("rl:refill", qps=10)
    assert refilled.allowed
