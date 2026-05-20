"""Tests for control_plane.retention (spec §7 数据保留：body N 天后置 NULL)."""
from datetime import UTC, datetime, timedelta

from mcpsys_shared.models import CallLog, CallStatus
from sqlalchemy import select

from control_plane.retention import run_retention_round


async def _add_call_log(
    session_factory,
    *,
    age_days: float,
    body: str | None = "payload",
) -> str:
    """插一行 call_log，ts = now - age_days，body 两列都填 `body`（或 None）。返回 id。"""
    async with session_factory() as s:
        row = CallLog(
            ts=datetime.now(UTC) - timedelta(days=age_days),
            service_id=1,
            status=CallStatus.success,
            duration_ms=1,
            request_body=body,
            response_body=body,
        )
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return str(row.id)


async def _bodies(session_factory, call_id: str) -> tuple[str | None, str | None]:
    async with session_factory() as s:
        row = await s.get(CallLog, call_id)
        assert row is not None
        return row.request_body, row.response_body


async def test_purges_bodies_past_cutoff(session_factory) -> None:
    """超期行的两个 body 列被清空，metadata 仍在、行不删。"""
    old_id = await _add_call_log(session_factory, age_days=40)

    purged = await run_retention_round(session_factory, retention_days=30, batch_size=100)

    assert purged == 1
    assert await _bodies(session_factory, old_id) == (None, None)
    # 行仍在（metadata 永久）
    async with session_factory() as s:
        row = await s.get(CallLog, old_id)
        assert row is not None
        assert row.service_id == 1
        assert row.status == CallStatus.success


async def test_keeps_bodies_within_cutoff(session_factory) -> None:
    """未超期行的 body 原样保留。"""
    fresh_id = await _add_call_log(session_factory, age_days=5)

    purged = await run_retention_round(session_factory, retention_days=30, batch_size=100)

    assert purged == 0
    assert await _bodies(session_factory, fresh_id) == ("payload", "payload")


async def test_idempotent_already_nulled_not_recounted(session_factory) -> None:
    """已清空的超期行不会被再次计入（body IS NOT NULL 谓词过滤）。"""
    await _add_call_log(session_factory, age_days=40)

    first = await run_retention_round(session_factory, retention_days=30, batch_size=100)
    second = await run_retention_round(session_factory, retention_days=30, batch_size=100)

    assert first == 1
    assert second == 0


async def test_batches_until_drained(session_factory) -> None:
    """待清理行数 > batch_size 时，单轮循环分批清完全部。"""
    for _ in range(5):
        await _add_call_log(session_factory, age_days=40)

    purged = await run_retention_round(session_factory, retention_days=30, batch_size=2)

    assert purged == 5
    remaining = (
        await _count_with_body(session_factory)
    )
    assert remaining == 0


async def _count_with_body(session_factory) -> int:
    async with session_factory() as s:
        rows = (
            await s.execute(
                select(CallLog).where(CallLog.request_body.isnot(None))
            )
        ).scalars().all()
        return len(rows)


async def test_empty_db_no_op(session_factory) -> None:
    """无数据时直接返回 0，不抛错。"""
    assert await run_retention_round(session_factory, retention_days=30, batch_size=100) == 0
