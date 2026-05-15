from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Range = Literal["15m", "1h", "24h", "7d"]
Metric = Literal["calls", "errors", "error_rate", "p50", "p95", "p99", "throttled"]
Bucket = Literal["1m", "5m", "1h"]
Dim = Literal["service", "application", "api_key", "tool", "status"]


class StatsFilter(BaseModel):
    """互斥过滤；同时给多个时按 service_id > application_id > api_key_id 取一个。"""

    service_id: int | None = None
    application_id: int | None = None
    api_key_id: int | None = None


class OverviewOut(BaseModel):
    range: Range
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    filter: StatsFilter | None
    calls: int
    errors: int
    error_rate: float
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    throttled: int
    denied: int
    last_call_at: datetime | None


class TimeseriesPoint(BaseModel):
    ts: datetime
    value: float | int | None


class TimeseriesOut(BaseModel):
    metric: Metric
    range: Range
    bucket: Bucket
    filter: StatsFilter | None
    points: list[TimeseriesPoint]


class BreakdownRow(BaseModel):
    key: int | str | None
    label: str | None
    count: int
    error_count: int
    error_rate: float


class BreakdownOther(BaseModel):
    count: int
    error_count: int


class BreakdownOut(BaseModel):
    dim: Dim
    range: Range
    metric: Literal["calls", "errors"]
    filter: StatsFilter | None
    rows: list[BreakdownRow]
    other: BreakdownOther | None


class LatencyBucket(BaseModel):
    lo: int
    hi: int | None
    count: int


class LatencyHistogramOut(BaseModel):
    range: Range
    filter: StatsFilter | None
    buckets: list[LatencyBucket]
