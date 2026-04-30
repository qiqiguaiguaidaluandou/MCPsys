import asyncio

import pytest
from sqlalchemy import func, select

from mcpsys_shared.models import CallLog, CallStatus

from gateway.telemetry import CallLogEntry, TelemetryWriter


def make_entry(service_id: int, status: CallStatus = CallStatus.success) -> CallLogEntry:
    return CallLogEntry(
        api_key_id=1,
        application_id=2,
        user_id=None,
        service_id=service_id,
        service_version=None,
        tool_name="echo",
        request_id="42",
        status=status,
        http_status=200,
        error_code=None,
        error_message=None,
        duration_ms=12,
        request_bytes=10,
        response_bytes=20,
        request_body='{"a":1}',
        response_body='{"b":2}',
        client_ip="127.0.0.1",
    )


async def _count(session_factory) -> int:
    async with session_factory() as s:
        res = await s.execute(select(func.count()).select_from(CallLog))
        return res.scalar_one()


async def test_writes_after_batch_size(session_factory):
    w = TelemetryWriter(session_factory=session_factory, batch_size=3, flush_interval=10)
    await w.start()
    try:
        for _ in range(3):
            await w.enqueue(make_entry(service_id=1))
        # give the loop a tick
        await asyncio.sleep(0.2)
        assert await _count(session_factory) == 3
    finally:
        await w.stop()


async def test_writes_after_interval(session_factory):
    w = TelemetryWriter(session_factory=session_factory, batch_size=100, flush_interval=0.2)
    await w.start()
    try:
        await w.enqueue(make_entry(service_id=2))
        await asyncio.sleep(0.5)
        # at least the one we enqueued should be flushed by now
        assert await _count(session_factory) >= 1
    finally:
        await w.stop()


async def test_stop_flushes_pending(session_factory):
    w = TelemetryWriter(session_factory=session_factory, batch_size=100, flush_interval=10)
    await w.start()
    await w.enqueue(make_entry(service_id=3))
    await w.stop()
    # after stop(), enqueued items must be persisted
    async with session_factory() as s:
        res = await s.execute(
            select(func.count()).select_from(CallLog).where(CallLog.service_id == 3)
        )
        assert res.scalar_one() == 1
