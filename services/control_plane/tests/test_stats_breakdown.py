import uuid
from datetime import UTC, datetime, timedelta

import pytest
from mcpsys_shared.models import (
    Application,
    CallLog,
    CallStatus,
    McpService,
    ServiceStatus,
    TransportType,
    User,
    UserRole,
    UserStatus,
)
from sqlalchemy import select

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as s:
        u = User(
            username="bd-admin",
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


async def _add_log(
    s,
    *,
    ts: datetime | None = None,
    status: CallStatus = CallStatus.success,
    duration_ms: int = 10,
    service_id: int = 1,
    application_id: int | None = None,
    api_key_id: int | None = None,
    tool_name: str | None = "tools/list",
) -> None:
    s.add(
        CallLog(
            id=uuid.uuid4(),
            ts=ts or datetime.now(UTC) - timedelta(minutes=5),
            service_id=service_id,
            application_id=application_id,
            api_key_id=api_key_id,
            tool_name=tool_name,
            request_id=str(uuid.uuid4()),
            status=status,
            http_status=200 if status == CallStatus.success else 500,
            duration_ms=duration_ms,
            request_bytes=10,
            response_bytes=10,
        )
    )


async def test_breakdown_top_services_with_other(client, admin, session_factory):
    """spec §6.1：12 个 service × N calls，limit=10 → 10 行 + other 含余下 2 个。"""
    async with session_factory() as s:
        for i in range(12):
            svc = McpService(
                slug=f"bd-svc-{i:02d}",
                display_name=f"S{i}",
                endpoint_url=f"http://s{i}/mcp",
                transport=TransportType.streamable_http,
                status=ServiceStatus.active,
            )
            s.add(svc)
        await s.commit()
        all_svcs = sorted(
            (await s.execute(select(McpService))).scalars().all(),
            key=lambda r: r.slug,
        )
        # 给每个服务塞不同数量的 call，保证 Top 10 排序稳定
        for rank, svc in enumerate(all_svcs):
            for _ in range(20 - rank):  # 20, 19, 18, ..., 9
                await _add_log(s, service_id=svc.id)
        await s.commit()

    resp = await client.get(
        "/api/v1/stats/breakdown?dim=service&range=24h&limit=10",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["dim"] == "service"
    assert len(body["rows"]) == 10
    # Top 行按 count DESC：20, 19, ..., 11
    assert [r["count"] for r in body["rows"]] == list(range(20, 10, -1))
    # 余下两个的总 count = 10 + 9 = 19
    assert body["other"] == {"count": 19, "error_count": 0}


async def test_breakdown_no_other_when_rows_under_limit(client, admin, session_factory):
    async with session_factory() as s:
        svc = McpService(
            slug="bd-only", display_name="O", endpoint_url="http://o/mcp"
        )
        s.add(svc)
        await s.commit()
        await s.refresh(svc)
        for _ in range(5):
            await _add_log(s, service_id=svc.id)
        await s.commit()

    resp = await client.get(
        "/api/v1/stats/breakdown?dim=service&range=24h&limit=10",
        headers=auth_header(admin),
    )
    data = resp.json()
    assert len(data["rows"]) == 1
    assert data["other"] is None


async def test_breakdown_metric_errors_orders_by_error_count(
    client, admin, session_factory
):
    async with session_factory() as s:
        for i in range(3):
            svc = McpService(
                slug=f"bd-err-{i}",
                display_name=f"E{i}",
                endpoint_url=f"http://e{i}/mcp",
            )
            s.add(svc)
        await s.commit()
        svcs = sorted(
            (await s.execute(select(McpService))).scalars().all(),
            key=lambda r: r.slug,
        )
        # 调用数都一样（10），但错误数不同：svc0=1, svc1=5, svc2=3
        error_counts = {svcs[0].id: 1, svcs[1].id: 5, svcs[2].id: 3}
        for svc_row in svcs:
            err = error_counts[svc_row.id]
            for _ in range(err):
                await _add_log(s, service_id=svc_row.id, status=CallStatus.error)
            for _ in range(10 - err):
                await _add_log(s, service_id=svc_row.id, status=CallStatus.success)
        await s.commit()

    resp = await client.get(
        "/api/v1/stats/breakdown?dim=service&range=24h&metric=errors",
        headers=auth_header(admin),
    )
    body = resp.json()
    # 顺序应按 error_count DESC：5, 3, 1
    assert [r["error_count"] for r in body["rows"]] == [5, 3, 1]


async def test_breakdown_by_application(client, admin, session_factory):
    async with session_factory() as s:
        a1 = Application(name="bd-app-1", owner_user_id=admin.id)
        a2 = Application(name="bd-app-2", owner_user_id=admin.id)
        s.add_all([a1, a2])
        await s.commit()
        await s.refresh(a1)
        await s.refresh(a2)
        for _ in range(7):
            await _add_log(s, application_id=a1.id)
        for _ in range(3):
            await _add_log(s, application_id=a2.id)
        # 一条没有 application_id 的，应该被滤掉（null_filter）
        await _add_log(s, application_id=None)
        await s.commit()

    resp = await client.get(
        "/api/v1/stats/breakdown?dim=application&range=24h",
        headers=auth_header(admin),
    )
    data = resp.json()
    keys = [r["key"] for r in data["rows"]]
    assert a1.id in keys and a2.id in keys
    # null application_id 不应出现
    assert all(r["key"] is not None for r in data["rows"])


async def test_breakdown_by_status(client, admin, session_factory):
    async with session_factory() as s:
        for _ in range(8):
            await _add_log(s, status=CallStatus.success)
        for _ in range(3):
            await _add_log(s, status=CallStatus.error)
        for _ in range(1):
            await _add_log(s, status=CallStatus.throttled)
        await s.commit()

    resp = await client.get(
        "/api/v1/stats/breakdown?dim=status&range=24h",
        headers=auth_header(admin),
    )
    data = resp.json()
    by_status = {r["label"]: r["count"] for r in data["rows"]}
    assert by_status == {"success": 8, "error": 3, "throttled": 1}
    # status 总共 5 个枚举，limit 默认 10 ≥ 5 → 不应有 other
    assert data["other"] is None


async def test_breakdown_by_tool(client, admin, session_factory):
    async with session_factory() as s:
        for _ in range(4):
            await _add_log(s, tool_name="search")
        for _ in range(2):
            await _add_log(s, tool_name="lookup")
        await _add_log(s, tool_name=None)  # 应被滤
        await s.commit()

    resp = await client.get(
        "/api/v1/stats/breakdown?dim=tool&range=24h",
        headers=auth_header(admin),
    )
    by_tool = {r["label"]: r["count"] for r in resp.json()["rows"]}
    assert by_tool == {"search": 4, "lookup": 2}


async def test_breakdown_with_service_filter(client, admin, session_factory):
    async with session_factory() as s:
        svc_a = McpService(slug="bd-f-a", display_name="A", endpoint_url="http://a/mcp")
        svc_b = McpService(slug="bd-f-b", display_name="B", endpoint_url="http://b/mcp")
        s.add_all([svc_a, svc_b])
        await s.commit()
        await s.refresh(svc_a)
        await s.refresh(svc_b)
        for _ in range(5):
            await _add_log(s, service_id=svc_a.id, tool_name="a-tool")
        for _ in range(3):
            await _add_log(s, service_id=svc_b.id, tool_name="b-tool")
        await s.commit()

    resp = await client.get(
        f"/api/v1/stats/breakdown?dim=tool&range=24h&service_id={svc_a.id}",
        headers=auth_header(admin),
    )
    data = resp.json()
    tools = {r["label"]: r["count"] for r in data["rows"]}
    assert tools == {"a-tool": 5}
    assert data["filter"] == {
        "service_id": svc_a.id,
        "application_id": None,
        "api_key_id": None,
    }


async def test_breakdown_invalid_dim_422(client, admin):
    resp = await client.get(
        "/api/v1/stats/breakdown?dim=bogus&range=24h",
        headers=auth_header(admin),
    )
    assert resp.status_code == 422


async def test_breakdown_invalid_metric_422(client, admin):
    resp = await client.get(
        "/api/v1/stats/breakdown?dim=service&metric=p95&range=24h",
        headers=auth_header(admin),
    )
    assert resp.status_code == 422


async def test_breakdown_30d_range(client, admin, session_factory):
    """range=30d 走通 breakdown 端点（_RANGE_DELTA 新键），跨日数据按 count 正确排序。"""
    now = datetime.now(UTC)
    async with session_factory() as s:
        for i in range(3):
            svc = McpService(
                slug=f"bd30-svc-{i}",
                display_name=f"S{i}",
                endpoint_url=f"http://s{i}/mcp",
                transport=TransportType.streamable_http,
                status=ServiceStatus.active,
            )
            s.add(svc)
        await s.commit()
        svcs = sorted(
            (await s.execute(select(McpService).where(McpService.slug.like("bd30-%"))))
            .scalars()
            .all(),
            key=lambda r: r.slug,
        )
        # 跨 25 天 + 5 天，确保 30d 窗口都能包到
        for _ in range(10):
            await _add_log(s, ts=now - timedelta(days=25), service_id=svcs[0].id)
        for _ in range(5):
            await _add_log(s, ts=now - timedelta(days=5), service_id=svcs[1].id)
        for _ in range(2):
            await _add_log(s, ts=now - timedelta(days=1), service_id=svcs[2].id)
        await s.commit()

    resp = await client.get(
        "/api/v1/stats/breakdown?dim=service&range=30d&limit=10",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    data = resp.json()
    counts = {r["label"]: r["count"] for r in data["rows"] if r["label"].startswith("bd30-")}
    assert counts == {"bd30-svc-0": 10, "bd30-svc-1": 5, "bd30-svc-2": 2}
