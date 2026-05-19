"""Tests for control_plane.health_checker (spec §4.3 流程 C)."""
from datetime import UTC, datetime

import httpx
import pytest
from mcpsys_shared.models import (
    AuditEvent,
    HealthStatus,
    McpService,
    ServiceStatus,
    TransportType,
)
from sqlalchemy import select

from control_plane import health_checker
from control_plane.health_checker import (
    probe_service,
    run_health_check_round,
)


def _ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})


def _server_error_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, text="upstream down")


def _client_error_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(404, text="no such method")


def _timeout_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.TimeoutException("probe timed out", request=request)


def _connect_error_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


async def test_probe_healthy_2xx() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_ok_handler)) as c:
        assert await probe_service(c, "http://x/mcp") == HealthStatus.healthy


async def test_probe_healthy_4xx() -> None:
    """4xx = '服务有响应但拒绝了探活'，仍说明上游存活。"""
    async with httpx.AsyncClient(transport=httpx.MockTransport(_client_error_handler)) as c:
        assert await probe_service(c, "http://x/mcp") == HealthStatus.healthy


async def test_probe_unhealthy_5xx() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_server_error_handler)) as c:
        assert await probe_service(c, "http://x/mcp") == HealthStatus.unhealthy


async def test_probe_unhealthy_timeout() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_timeout_handler)) as c:
        assert await probe_service(c, "http://x/mcp") == HealthStatus.unhealthy


async def test_probe_unhealthy_connect_error() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_connect_error_handler)) as c:
        assert await probe_service(c, "http://x/mcp") == HealthStatus.unhealthy


async def _add_service(
    session_factory,
    slug: str,
    *,
    status: ServiceStatus = ServiceStatus.active,
    health: HealthStatus = HealthStatus.unknown,
) -> int:
    async with session_factory() as s:
        svc = McpService(
            slug=slug,
            display_name=slug,
            endpoint_url=f"http://{slug}/mcp",
            transport=TransportType.streamable_http,
            status=status,
            health_status=health,
        )
        s.add(svc)
        await s.commit()
        await s.refresh(svc)
        return svc.id


async def test_round_updates_last_check_and_audits_change(
    session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """active 服务从 unknown → healthy：last_health_check_at 被填、health_status 翻新、
    audit_events 多一行 service.health_change。"""
    sid = await _add_service(session_factory, "hc-a", health=HealthStatus.unknown)

    async def fake_probe(client, url):
        return HealthStatus.healthy

    monkeypatch.setattr(health_checker, "probe_service", fake_probe)
    await run_health_check_round(session_factory)

    async with session_factory() as s:
        svc = await s.get(McpService, sid)
        assert svc is not None
        assert svc.health_status == HealthStatus.healthy
        assert svc.last_health_check_at is not None
        events = (
            await s.execute(
                select(AuditEvent)
                .where(AuditEvent.action == "service.health_change")
                .where(AuditEvent.target_id == str(sid))
            )
        ).scalars().all()
        assert len(events) == 1
        assert events[0].before == {"health_status": "unknown", "slug": "hc-a"}
        assert events[0].after == {"health_status": "healthy", "slug": "hc-a"}


async def test_round_skips_disabled_services(
    session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    active_id = await _add_service(session_factory, "hc-active")
    disabled_id = await _add_service(
        session_factory, "hc-disabled", status=ServiceStatus.disabled
    )

    async def fake_probe(client, url):
        return HealthStatus.healthy

    monkeypatch.setattr(health_checker, "probe_service", fake_probe)
    await run_health_check_round(session_factory)

    async with session_factory() as s:
        active = await s.get(McpService, active_id)
        disabled = await s.get(McpService, disabled_id)
        assert active.last_health_check_at is not None
        assert active.health_status == HealthStatus.healthy
        # disabled 服务不参与，状态保持初始
        assert disabled.last_health_check_at is None
        assert disabled.health_status == HealthStatus.unknown


async def test_round_no_change_no_extra_audit(
    session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """已为 healthy 的服务再来一轮 healthy：last_check 更新但不多 audit 行。"""
    sid = await _add_service(session_factory, "hc-stable", health=HealthStatus.healthy)

    async def fake_probe(client, url):
        return HealthStatus.healthy

    monkeypatch.setattr(health_checker, "probe_service", fake_probe)
    before_ts = datetime.now(UTC)
    await run_health_check_round(session_factory)

    async with session_factory() as s:
        svc = await s.get(McpService, sid)
        assert svc.last_health_check_at is not None
        assert svc.last_health_check_at >= before_ts
        count = (
            await s.execute(
                select(AuditEvent).where(AuditEvent.target_id == str(sid))
            )
        ).scalars().all()
        assert len(count) == 0


async def test_round_empty_db_no_op(session_factory) -> None:
    """无 active 服务时 run_health_check_round 直接返回，不抛错。"""
    await run_health_check_round(session_factory)
