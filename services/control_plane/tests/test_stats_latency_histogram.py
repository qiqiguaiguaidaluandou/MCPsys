import uuid
from datetime import UTC, datetime, timedelta

import pytest
from mcpsys_shared.models import (
    CallLog,
    CallStatus,
    User,
    UserRole,
    UserStatus,
)

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as s:
        u = User(
            username="lh-admin",
            password_hash=hash_password("p"),
            role=UserRole.admin,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


def auth_header(user: User) -> dict:
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


async def _add_log(s, *, duration_ms: int) -> None:
    s.add(
        CallLog(
            id=uuid.uuid4(),
            ts=datetime.now(UTC) - timedelta(minutes=5),
            service_id=1,
            tool_name="tools/list",
            request_id=str(uuid.uuid4()),
            status=CallStatus.success,
            http_status=200,
            duration_ms=duration_ms,
            request_bytes=10,
            response_bytes=10,
        )
    )


async def test_latency_histogram_empty(client, admin):
    resp = await client.get(
        "/api/v1/stats/latency-histogram?range=24h",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["buckets"]) == 7
    assert all(b["count"] == 0 for b in data["buckets"])
    # 第一个桶 lo=0；最后一个 hi=null（overflow）
    assert data["buckets"][0]["lo"] == 0
    assert data["buckets"][0]["hi"] == 50
    assert data["buckets"][-1]["lo"] == 2000
    assert data["buckets"][-1]["hi"] is None


async def test_latency_histogram_overflow_bucket(client, admin, session_factory):
    """spec §6.1：duration_ms=5000 → 落入 hi=null 的 overflow bucket。"""
    async with session_factory() as s:
        await _add_log(s, duration_ms=5000)
        await s.commit()

    resp = await client.get(
        "/api/v1/stats/latency-histogram?range=24h",
        headers=auth_header(admin),
    )
    buckets = resp.json()["buckets"]
    overflow = buckets[-1]
    assert overflow["lo"] == 2000
    assert overflow["hi"] is None
    assert overflow["count"] == 1
    # 其它桶都应是 0
    assert sum(b["count"] for b in buckets[:-1]) == 0


async def test_latency_histogram_bucket_boundaries(client, admin, session_factory):
    """每个桶中间值 → 该桶 count=1，其他 0。验证边界正确。"""
    midpoints = [25, 75, 150, 350, 750, 1500, 3000]
    async with session_factory() as s:
        for d in midpoints:
            await _add_log(s, duration_ms=d)
        await s.commit()

    resp = await client.get(
        "/api/v1/stats/latency-histogram?range=24h",
        headers=auth_header(admin),
    )
    counts = [b["count"] for b in resp.json()["buckets"]]
    assert counts == [1, 1, 1, 1, 1, 1, 1]


async def test_latency_histogram_boundary_inclusive_lo(
    client, admin, session_factory
):
    """lo 值刚好等于桶下界 → 落入该桶（半开区间 [lo, hi)）。"""
    async with session_factory() as s:
        await _add_log(s, duration_ms=50)   # → bucket[1] (50..100)
        await _add_log(s, duration_ms=2000)  # → bucket[6] (2000..∞)
        await s.commit()

    resp = await client.get(
        "/api/v1/stats/latency-histogram?range=24h",
        headers=auth_header(admin),
    )
    counts = [b["count"] for b in resp.json()["buckets"]]
    # index 0 不应得到 50; index 1 +1; ... ; index 6 +1
    assert counts[0] == 0
    assert counts[1] == 1
    assert counts[6] == 1


async def test_latency_histogram_filter_response_echo(client, admin):
    resp = await client.get(
        "/api/v1/stats/latency-histogram?range=1h&service_id=42",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["filter"] == {
        "service_id": 42,
        "application_id": None,
        "api_key_id": None,
    }
