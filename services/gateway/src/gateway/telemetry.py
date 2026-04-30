import asyncio
import logging
from dataclasses import asdict, dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mcpsys_shared.models import CallLog, CallStatus

logger = logging.getLogger(__name__)


@dataclass
class CallLogEntry:
    api_key_id: int | None
    application_id: int | None
    user_id: int | None
    service_id: int
    service_version: str | None
    tool_name: str | None
    request_id: str | None
    status: CallStatus
    http_status: int | None
    error_code: str | None
    error_message: str | None
    duration_ms: int
    request_bytes: int | None
    response_bytes: int | None
    request_body: str | None
    response_body: str | None
    client_ip: str | None


class TelemetryWriter:
    """In-memory queue + background flusher.

    Trade-off: small risk of log loss on hard crash; kept for main-path latency.
    Writes are batched by size or interval, whichever comes first.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        batch_size: int = 100,
        flush_interval: float = 1.0,
    ) -> None:
        self._sf = session_factory
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._queue: asyncio.Queue[CallLogEntry] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="telemetry-flusher")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def enqueue(self, entry: CallLogEntry) -> None:
        await self._queue.put(entry)

    async def _run(self) -> None:
        while not self._stopping.is_set():
            batch = await self._collect_batch()
            if batch:
                await self._flush(batch)
        # drain remaining
        remaining: list[CallLogEntry] = []
        while not self._queue.empty():
            remaining.append(self._queue.get_nowait())
        if remaining:
            await self._flush(remaining)

    async def _collect_batch(self) -> list[CallLogEntry]:
        deadline = asyncio.get_running_loop().time() + self._flush_interval
        batch: list[CallLogEntry] = []
        while len(batch) < self._batch_size:
            timeout = max(0.0, deadline - asyncio.get_running_loop().time())
            if timeout == 0.0 and batch:
                break
            try:
                if self._stopping.is_set():
                    # short timeout to drain quickly
                    timeout = min(timeout, 0.05)
                item = await asyncio.wait_for(self._queue.get(), timeout=timeout or 0.05)
                batch.append(item)
            except asyncio.TimeoutError:
                break
        return batch

    async def _flush(self, batch: list[CallLogEntry]) -> None:
        rows = [CallLog(**asdict(e)) for e in batch]
        try:
            async with self._sf() as session:
                session.add_all(rows)
                await session.commit()
        except Exception as ex:  # log loss is acceptable per design (NFR §7)
            logger.error("telemetry flush failed: %s (dropped %d entries)", ex, len(rows))
