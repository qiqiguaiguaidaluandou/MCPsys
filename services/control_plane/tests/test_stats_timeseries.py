import uuid
from datetime import UTC, datetime, timedelta

import pytest
from mcpsys_shared.models import (
    CallLog,
    CallStatus,
    McpService,
    ServiceStatus,
    TransportType,
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
            username="ts-admin",
            password_hash=hash_password("p"),
            role=UserRole.admin,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


@pytest.fixture
async def service_a(session_factory):
    async with session_factory() as s:
        svc = McpService(
            slug="ts-a",
            display_name="A",
            endpoint_url="http://a/mcp",
            transport=TransportType.streamable_http,
            status=ServiceStatus.active,
        )
        s.add(svc)
        await s.commit()
        await s.refresh(svc)
        return svc


@pytest.fixture
async def service_b(session_factory):
    async with session_factory() as s:
        svc = McpService(
            slug="ts-b",
            display_name="B",
            endpoint_url="http://b/mcp",
            transport=TransportType.streamable_http,
            status=ServiceStatus.active,
        )
        s.add(svc)
        await s.commit()
        await s.refresh(svc)
        return svc


def auth_header(user: User) -> dict:
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


async def _add_log(
    s,
    *,
    ts: datetime,
    status: CallStatus = CallStatus.success,
    duration_ms: int = 10,
    service_id: int = 1,
) -> None:
    s.add(
        CallLog(
            id=uuid.uuid4(),
            ts=ts,
            service_id=service_id,
            tool_name="tools/list",
            request_id=str(uuid.uuid4()),
            status=status,
            http_status=200,
            duration_ms=duration_ms,
            request_bytes=10,
            response_bytes=10,
        )
    )


async def test_timeseries_calls_bucket_5m(client, admin, session_factory):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    async with session_factory() as s:
        await _add_log(s, ts=now - timedelta(minutes=2))
        await _add_log(s, ts=now - timedelta(minutes=2))
        await _add_log(s, ts=now - timedelta(minutes=7))
        await s.commit()

    resp = await client.get(
        "/api/v1/stats/timeseries?metric=calls&range=1h&bucket=5m",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["bucket"] == "5m"
    # 1h / 5m = 12 buckets，空 bucket 用 0 填充
    assert len(data["points"]) == 12
    assert sum(p["value"] for p in data["points"]) == 3


async def test_timeseries_default_bucket_by_range(client, admin):
    for r, expected_bucket in [
        ("15m", "1m"),
        ("1h", "1m"),
        ("24h", "5m"),
        ("7d", "1h"),
        ("30d", "1d"),
        ("all", "1d"),
    ]:
        resp = await client.get(
            f"/api/v1/stats/timeseries?metric=calls&range={r}",
            headers=auth_header(admin),
        )
        assert resp.status_code == 200
        assert resp.json()["bucket"] == expected_bucket


async def test_timeseries_p95_with_service_filter(
    client, admin, session_factory, service_a, service_b
):
    now = datetime.now(UTC) - timedelta(minutes=5)
    async with session_factory() as s:
        for _ in range(100):
            await _add_log(s, ts=now, service_id=service_a.id, duration_ms=10)
        for _ in range(100):
            await _add_log(s, ts=now, service_id=service_b.id, duration_ms=1000)
        await s.commit()

    resp = await client.get(
        f"/api/v1/stats/timeseries?metric=p95&range=1h&service_id={service_a.id}",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    nonzero = [p for p in resp.json()["points"] if p["value"]]
    # service_a 全 10ms，p95 应远小于 service_b 的 1000
    assert nonzero, "expected at least one non-zero bucket"
    assert all(p["value"] < 100 for p in nonzero)


async def test_timeseries_error_rate_no_data_zero(client, admin):
    resp = await client.get(
        "/api/v1/stats/timeseries?metric=error_rate&range=1h",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    assert all(p["value"] == 0 for p in resp.json()["points"])


async def test_timeseries_30d_default_bucket_1d(client, admin, session_factory):
    """range=30d 默认 bucket=1d，30 个桶；唯一落点位于 now-5d 桶。"""
    now = datetime.now(UTC)
    async with session_factory() as s:
        await _add_log(s, ts=now - timedelta(days=5))
        await s.commit()

    resp = await client.get(
        "/api/v1/stats/timeseries?metric=calls&range=30d",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["bucket"] == "1d"
    assert len(data["points"]) == 30
    nonzero = [p for p in data["points"] if p["value"]]
    assert len(nonzero) == 1
    assert nonzero[0]["value"] == 1


async def test_timeseries_all_1d_bucket_old_log(client, admin, session_factory):
    """range=all 用 1d bucket 也能包到 100 天前的旧 call_log。"""
    now = datetime.now(UTC)
    async with session_factory() as s:
        await _add_log(s, ts=now - timedelta(days=100))
        await s.commit()

    resp = await client.get(
        "/api/v1/stats/timeseries?metric=calls&range=all",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["bucket"] == "1d"
    nonzero = [p for p in data["points"] if p["value"]]
    assert len(nonzero) == 1
    assert nonzero[0]["value"] == 1
