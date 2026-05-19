"""Background health checker (spec §4.3 流程 C).

启动 asyncio 周期任务，每 N 秒对所有 status=active 的服务并发探活：
- POST endpoint_url 发 JSON-RPC initialize
- 写回 mcp_services.health_status + last_health_check_at
- 状态变化时 audit_log(SERVICE_HEALTH_CHANGE)

不引 APScheduler —— 任务太简单，asyncio loop 已经够；spec AD-4 明确只在
control-plane 跑，不在 gateway（多实例无状态，重复探活浪费）。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mcpsys_shared.models import HealthStatus, McpService, ServiceStatus

from .audit import Action, audit_log
from .settings import settings

logger = logging.getLogger(__name__)


_INIT_BODY: dict = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}


async def probe_service(client: httpx.AsyncClient, endpoint_url: str) -> HealthStatus:
    """探一个 endpoint，返回 healthy / unhealthy。永不抛异常。

    分类口径：
    - 2xx / 4xx → healthy（服务有响应；4xx = "在线但拒绝了我们的探活"，仍说明上游存活）
    - 5xx / 超时 / 连接错误 / DNS / TLS 失败 → unhealthy
    """
    try:
        resp = await client.post(
            endpoint_url,
            json=_INIT_BODY,
            timeout=settings.health_check_timeout_seconds,
        )
    except (httpx.TimeoutException, httpx.RequestError):
        return HealthStatus.unhealthy
    if 200 <= resp.status_code < 500:
        return HealthStatus.healthy
    return HealthStatus.unhealthy


async def run_health_check_round(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """一轮：列出 active 服务 → 并发 probe → 写回状态/audit。

    用两段 session：第一段读、释放；第二段写回。避免在并发探活的 await 边界
    持有 session 引发 asyncpg 重入问题。
    """
    async with session_factory() as session:
        result = await session.execute(
            select(McpService).where(McpService.status == ServiceStatus.active)
        )
        services = list(result.scalars().all())
    if not services:
        return

    sem = asyncio.Semaphore(settings.health_check_concurrency)
    async with httpx.AsyncClient() as client:

        async def probe_one(svc: McpService) -> tuple[int, HealthStatus, HealthStatus, str]:
            async with sem:
                new_status = await probe_service(client, svc.endpoint_url)
            return svc.id, svc.health_status, new_status, svc.slug

        results = await asyncio.gather(*(probe_one(s) for s in services))

    now = datetime.now(UTC)
    async with session_factory() as session:
        for svc_id, old_status, new_status, slug in results:
            svc_db = await session.get(McpService, svc_id)
            if svc_db is None:
                # 这一轮中途被归档/删除：跳过
                continue
            svc_db.last_health_check_at = now
            if old_status != new_status:
                svc_db.health_status = new_status
                await audit_log(
                    session,
                    action=Action.SERVICE_HEALTH_CHANGE,
                    target_type="mcp_service",
                    target_id=str(svc_id),
                    before={"health_status": old_status.value, "slug": slug},
                    after={"health_status": new_status.value, "slug": slug},
                    actor=None,
                    request=None,
                )
        await session.commit()


async def health_check_loop(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """常驻 loop：每 N 秒一轮；单轮异常被吃掉，loop 不死。"""
    interval = settings.health_check_interval_seconds
    logger.info("health checker started (interval=%ds)", interval)
    while True:
        try:
            await run_health_check_round(session_factory)
        except Exception:  # noqa: BLE001 — 防御性：DB 短暂断连等
            logger.exception("health check round failed")
        await asyncio.sleep(interval)
