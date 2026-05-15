from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db, require_role
from ..schemas.stats import (
    Bucket,
    Metric,
    OverviewOut,
    Range,
    StatsFilter,
    TimeseriesOut,
)

router = APIRouter(
    prefix="/api/v1/stats",
    tags=["stats"],
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)


_RANGE_DELTA: dict[Range, timedelta] = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}

_DEFAULT_BUCKET: dict[Range, Bucket] = {
    "15m": "1m",
    "1h": "1m",
    "24h": "5m",
    "7d": "1h",
}


def resolve_range(range_: Range, now: datetime | None = None) -> tuple[datetime, datetime]:
    """返回 (from_ts, to_ts)，UTC。to_ts 对齐到当前分钟（避免半桶抖动）。"""
    base = now or datetime.now(timezone.utc)
    to_ts = base.replace(second=0, microsecond=0)
    return to_ts - _RANGE_DELTA[range_], to_ts


def pick_filter(
    service_id: int | None,
    application_id: int | None,
    api_key_id: int | None,
) -> StatsFilter | None:
    """按 service_id > application_id > api_key_id 优先级选一个；全 None 返回 None。"""
    if service_id is not None:
        return StatsFilter(service_id=service_id)
    if application_id is not None:
        return StatsFilter(application_id=application_id)
    if api_key_id is not None:
        return StatsFilter(api_key_id=api_key_id)
    return None


_OVERVIEW_SQL = text("""
SELECT
  count(*)                                                  AS calls,
  count(*) FILTER (WHERE status != 'success')               AS errors,
  count(*) FILTER (WHERE status = 'throttled')              AS throttled,
  count(*) FILTER (WHERE status = 'denied')                 AS denied,
  percentile_cont(0.50) WITHIN GROUP (ORDER BY duration_ms) AS p50,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95,
  percentile_cont(0.99) WITHIN GROUP (ORDER BY duration_ms) AS p99,
  max(ts)                                                   AS last_call_at
FROM call_logs
WHERE ts >= :from_ts AND ts < :to_ts
  AND (CAST(:service_id     AS integer) IS NULL OR service_id     = :service_id)
  AND (CAST(:application_id AS integer) IS NULL OR application_id = :application_id)
  AND (CAST(:api_key_id     AS integer) IS NULL OR api_key_id     = :api_key_id)
""")


@router.get("/overview", response_model=OverviewOut, response_model_by_alias=True)
async def get_overview(
    range_: Range = Query("24h", alias="range"),
    service_id: int | None = Query(None),
    application_id: int | None = Query(None),
    api_key_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> OverviewOut:
    filt = pick_filter(service_id, application_id, api_key_id)
    from_ts, to_ts = resolve_range(range_)

    row = (
        await db.execute(
            _OVERVIEW_SQL,
            {
                "from_ts": from_ts,
                "to_ts": to_ts,
                "service_id": filt.service_id if filt else None,
                "application_id": filt.application_id if filt else None,
                "api_key_id": filt.api_key_id if filt else None,
            },
        )
    ).mappings().one()

    calls = row["calls"] or 0
    errors = row["errors"] or 0
    return OverviewOut(
        range=range_,
        from_=from_ts,
        to=to_ts,
        filter=filt,
        calls=calls,
        errors=errors,
        error_rate=(errors / calls) if calls else 0.0,
        p50_ms=row["p50"],
        p95_ms=row["p95"],
        p99_ms=row["p99"],
        throttled=row["throttled"] or 0,
        denied=row["denied"] or 0,
        last_call_at=row["last_call_at"],
    )


def _bucket_expr(bucket: Bucket) -> str:
    """SQL bucket 列表达式，命名为 bucket_ts。"""
    if bucket == "1m":
        return "date_trunc('minute', ts) AS bucket_ts"
    if bucket == "5m":
        return (
            "date_trunc('minute', ts) - "
            "make_interval(mins => (extract(minute FROM ts)::int % 5)) AS bucket_ts"
        )
    if bucket == "1h":
        return "date_trunc('hour', ts) AS bucket_ts"
    raise ValueError(bucket)


def _bucket_step(bucket: Bucket) -> str:
    return {"1m": "1 minute", "5m": "5 minutes", "1h": "1 hour"}[bucket]


def _metric_expr(metric: Metric) -> str:
    if metric == "calls":
        return "count(*)"
    if metric == "errors":
        return "count(*) FILTER (WHERE status != 'success')"
    if metric == "throttled":
        return "count(*) FILTER (WHERE status = 'throttled')"
    if metric == "error_rate":
        return (
            "CASE WHEN count(*) = 0 THEN 0.0 "
            "ELSE count(*) FILTER (WHERE status != 'success')::float / count(*) END"
        )
    if metric == "p50":
        return "percentile_cont(0.50) WITHIN GROUP (ORDER BY duration_ms)"
    if metric == "p95":
        return "percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)"
    if metric == "p99":
        return "percentile_cont(0.99) WITHIN GROUP (ORDER BY duration_ms)"
    raise ValueError(metric)


@router.get("/timeseries", response_model=TimeseriesOut, response_model_by_alias=True)
async def get_timeseries(
    metric: Metric = Query(...),
    range_: Range = Query("24h", alias="range"),
    bucket: Bucket | None = Query(None),
    service_id: int | None = Query(None),
    application_id: int | None = Query(None),
    api_key_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> TimeseriesOut:
    eff_bucket: Bucket = bucket or _DEFAULT_BUCKET[range_]
    filt = pick_filter(service_id, application_id, api_key_id)
    from_ts, to_ts = resolve_range(range_)

    sql = text(f"""
WITH series AS (
  SELECT generate_series(
    :from_ts::timestamptz,
    (:to_ts::timestamptz - interval '{_bucket_step(eff_bucket)}'),
    interval '{_bucket_step(eff_bucket)}'
  ) AS bucket_ts
),
agg AS (
  SELECT {_bucket_expr(eff_bucket)},
         {_metric_expr(metric)} AS value
  FROM call_logs
  WHERE ts >= :from_ts AND ts < :to_ts
    AND (CAST(:service_id     AS integer) IS NULL OR service_id     = :service_id)
    AND (CAST(:application_id AS integer) IS NULL OR application_id = :application_id)
    AND (CAST(:api_key_id     AS integer) IS NULL OR api_key_id     = :api_key_id)
  GROUP BY bucket_ts
)
SELECT s.bucket_ts AS ts, COALESCE(a.value, 0) AS value
FROM series s LEFT JOIN agg a USING (bucket_ts)
ORDER BY ts
""")

    rows = (
        await db.execute(
            sql,
            {
                "from_ts": from_ts,
                "to_ts": to_ts,
                "service_id": filt.service_id if filt else None,
                "application_id": filt.application_id if filt else None,
                "api_key_id": filt.api_key_id if filt else None,
            },
        )
    ).mappings().all()

    return TimeseriesOut(
        metric=metric,
        range=range_,
        bucket=eff_bucket,
        filter=filt,
        points=[{"ts": r["ts"], "value": r["value"]} for r in rows],
    )
