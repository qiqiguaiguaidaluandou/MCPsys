"""Background body-retention worker (spec §7 数据保留).

spec 口径：调用 metadata 永久保留；调用 body（request_body / response_body）
N 天（默认 30）后置 NULL。本 worker 周期性地把超期行的两个 body 列清空，
**不删行**——metadata 永久。

复刻 health_checker 的常驻 loop 形态：单轮异常被吃掉、loop 不死；
retention_enabled=False 用于测试隔离。AD-4 同理只在 control-plane 跑
（gateway 多实例无状态，重复清理浪费且互相空跑）。

为什么分批：一次 UPDATE 几百万行会拿很长的行锁、撑大 WAL、阻塞 autovacuum。
每批限量、逐批提交，把单次写事务控制在可控范围；循环直到一轮内无更多超期行。
依赖 ix_call_logs_body_unpurged 这个部分索引（只含未清空的行）——保证扫描代价
正比于"待清理行数"而非全表行数，否则 call_logs 越大、每轮越慢。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .settings import settings

logger = logging.getLogger(__name__)


# 子查询 ORDER BY ts + 部分索引谓词 ⇒ 走 ix_call_logs_body_unpurged，最旧的先清。
_PURGE_SQL = text("""
UPDATE call_logs
SET request_body = NULL, response_body = NULL
WHERE id IN (
    SELECT id FROM call_logs
    WHERE ts < :cutoff
      AND (request_body IS NOT NULL OR response_body IS NOT NULL)
    ORDER BY ts
    LIMIT :batch
)
""")


async def run_retention_round(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    retention_days: int,
    batch_size: int,
) -> int:
    """把 ts 早于 (now - retention_days) 且 body 尚未清空的行的两个 body 列置 NULL。

    分批提交，返回本轮清空的总行数。affected < batch ⇒ 已无更多超期行，收尾。
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    total = 0
    while True:
        async with session_factory() as session:
            result = await session.execute(
                _PURGE_SQL, {"cutoff": cutoff, "batch": batch_size}
            )
            await session.commit()
        affected = result.rowcount or 0
        total += affected
        if affected < batch_size:
            break
    if total:
        logger.info(
            "retention: nulled bodies on %d call_logs rows (cutoff=%s)",
            total,
            cutoff.isoformat(),
        )
    return total


async def retention_loop(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """常驻 loop：每 N 秒一轮；单轮异常被吃掉，loop 不死。"""
    interval = settings.retention_interval_seconds
    logger.info(
        "retention worker started (interval=%ds, retention=%dd)",
        interval,
        settings.call_log_body_retention_days,
    )
    while True:
        try:
            await run_retention_round(
                session_factory,
                retention_days=settings.call_log_body_retention_days,
                batch_size=settings.retention_batch_size,
            )
        except Exception:  # noqa: BLE001 — 防御性：DB 短暂断连等
            logger.exception("retention round failed")
        await asyncio.sleep(interval)
