import asyncio
from unittest.mock import MagicMock

import pytest
from gateway.invalidator import InvalidationListener
from redis.asyncio import Redis


async def _wait_until(predicate, timeout: float = 2.0, interval: float = 0.02) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


@pytest.fixture
async def listener_setup(redis_url):
    sub = Redis.from_url(redis_url, decode_responses=True)
    pub = Redis.from_url(redis_url, decode_responses=True)
    policy = MagicMock()
    resolver = MagicMock()
    listener = InvalidationListener(redis=sub, policy=policy, resolver=resolver)
    await listener.start()
    # Give the subscriber a moment to actually subscribe before publishing.
    await asyncio.sleep(0.05)
    yield listener, policy, resolver, pub
    await listener.stop()
    await sub.aclose()
    await pub.aclose()


async def test_policy_invalidate_specific_service(listener_setup):
    listener, policy, resolver, pub = listener_setup
    await pub.publish("policy:invalidate", "42")

    ok = await _wait_until(lambda: policy.invalidate.called)
    assert ok, "policy.invalidate was not called within timeout"
    policy.invalidate.assert_called_with(service_id=42)
    resolver.invalidate.assert_not_called()


async def test_policy_invalidate_all(listener_setup):
    listener, policy, resolver, pub = listener_setup
    await pub.publish("policy:invalidate", "")

    ok = await _wait_until(lambda: policy.invalidate.called)
    assert ok
    policy.invalidate.assert_called_with(service_id=None)


async def test_service_invalidate_specific_slug(listener_setup):
    listener, policy, resolver, pub = listener_setup
    await pub.publish("service:invalidate", "smoke-svc")

    ok = await _wait_until(lambda: resolver.invalidate.called)
    assert ok
    resolver.invalidate.assert_called_with(slug="smoke-svc")
    policy.invalidate.assert_not_called()


async def test_service_invalidate_all(listener_setup):
    listener, policy, resolver, pub = listener_setup
    await pub.publish("service:invalidate", "")

    ok = await _wait_until(lambda: resolver.invalidate.called)
    assert ok
    resolver.invalidate.assert_called_with(slug=None)


async def test_malformed_policy_payload_does_not_crash(listener_setup):
    listener, policy, resolver, pub = listener_setup
    await pub.publish("policy:invalidate", "not-an-int")
    # Send a valid one after; if listener died on the bad one, this won't reach.
    await pub.publish("policy:invalidate", "7")

    ok = await _wait_until(
        lambda: policy.invalidate.call_args is not None
        and policy.invalidate.call_args.kwargs.get("service_id") == 7
    )
    assert ok, "listener appears to have died on bad payload"


async def test_stop_is_clean(redis_url):
    sub = Redis.from_url(redis_url, decode_responses=True)
    listener = InvalidationListener(redis=sub, policy=MagicMock(), resolver=MagicMock())
    await listener.start()
    await asyncio.sleep(0.05)
    await listener.stop()
    # second stop should be a no-op, not raise
    await listener.stop()
    await sub.aclose()
