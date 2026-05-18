from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..cache_stats import cache_or_compute, filter_key, ttl_for
from ..deps import get_db, get_redis, require_role
from ..schemas.stats import (
    BreakdownOther,
    BreakdownOut,
    BreakdownRow,
    Bucket,
    Dim,
    LatencyBucket,
    LatencyHistogramOut,
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

# spec §3.2.4：固定 bucket 边界，前端不传。最后一桶 hi=None 表示溢出（>= 2000ms）。
_LATENCY_BOUNDS: list[tuple[int, int | None]] = [
    (0, 50),
    (50, 100),
    (100, 200),
    (200, 500),
    (500, 1000),
    (1000, 2000),
    (2000, None),
]


def resolve_range(range_: Range, now: datetime | None = None) -> tuple[datetime, datetime]:
    """返回 (from_ts, to_ts)，UTC。to_ts 对齐到当前分钟（避免半桶抖动）。"""
    base = now or datetime.now(timezone.utc)
    to_ts = base.replace(second=0, microsecond=0)
    return to_ts - _RANGE_DELTA[range_], to_ts


def _floor_to_bucket(ts: datetime, bucket: Bucket) -> datetime:
    """把 ts 向下取整到 bucket 边界。timeseries 必须把 from_ts / to_ts 都对齐到
    bucket 边界，否则 generate_series 产生的桶 ts 与 agg 的 date_trunc(...) 不重合，
    LEFT JOIN USING (bucket_ts) 全部 miss → 所有桶返回 0。"""
    if bucket == "1m":
        return ts.replace(second=0, microsecond=0)
    if bucket == "5m":
        return ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
    if bucket == "1h":
        return ts.replace(minute=0, second=0, microsecond=0)
    raise ValueError(bucket)


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


def _filter_sql_params(filt: StatsFilter | None) -> dict[str, int | None]:
    return {
        "service_id": filt.service_id if filt else None,
        "application_id": filt.application_id if filt else None,
        "api_key_id": filt.api_key_id if filt else None,
    }


# ------------------------------------------------------------------ /overview

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
    response: Response,
    range_: Range = Query("24h", alias="range"),
    service_id: int | None = Query(None),
    application_id: int | None = Query(None),
    api_key_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    redis: Redis | None = Depends(get_redis),
) -> OverviewOut:
    filt = pick_filter(service_id, application_id, api_key_id)
    cache_key = f"stats:overview:{range_}:{filter_key(filt)}"

    async def compute() -> OverviewOut:
        from_ts, to_ts = resolve_range(range_)
        row = (
            await db.execute(
                _OVERVIEW_SQL,
                {"from_ts": from_ts, "to_ts": to_ts, **_filter_sql_params(filt)},
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

    result, status_ = await cache_or_compute(
        redis, key=cache_key, ttl=ttl_for(range_), model_cls=OverviewOut, compute=compute
    )
    response.headers["x-cache"] = status_
    return result


# ---------------------------------------------------------------- /timeseries


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
    response: Response,
    metric: Metric = Query(...),
    range_: Range = Query("24h", alias="range"),
    bucket: Bucket | None = Query(None),
    service_id: int | None = Query(None),
    application_id: int | None = Query(None),
    api_key_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    redis: Redis | None = Depends(get_redis),
) -> TimeseriesOut:
    eff_bucket: Bucket = bucket or _DEFAULT_BUCKET[range_]
    filt = pick_filter(service_id, application_id, api_key_id)
    cache_key = f"stats:ts:{metric}:{range_}:{eff_bucket}:{filter_key(filt)}"

    async def compute() -> TimeseriesOut:
        from_ts, to_ts = resolve_range(range_)
        # 对齐到 bucket 边界——所有 _RANGE_DELTA 都是 bucket 的整数倍，所以先
        # 对齐 to_ts、再 from_ts = to_ts - delta 就同时对齐两端，且窗口宽度
        # 仍为 range 标称值（可能整体左移 < 1 bucket）。
        to_ts = _floor_to_bucket(to_ts, eff_bucket)
        from_ts = to_ts - _RANGE_DELTA[range_]
        # generate_series 重载选择需要参数类型提示，必须 cast 才能让 PG 在
        # prepare 阶段选中 (timestamptz, timestamptz, interval) 重载。
        # 注意不能写 `:from_ts::timestamptz` —— SQLAlchemy text() 的 bind 正
        # 则带负向前瞻 `(?!:)`，会把 `:from_ts` 切成 `:from_t`，导致 bind
        # 名错位 → asyncpg 收到原文 `:from_t` 抛 PostgresSyntaxError。
        # 解决：用 `CAST(:name AS type)` 形式，bind 正则识别，PG 也能定型。
        # WHERE 子句里的 `ts >= :from_ts` 不用 cast——参数与列 ts(timestamptz)
        # 比较时 PG 可从列类型推断参数类型。
        sql = text(f"""
WITH series AS (
  SELECT generate_series(
    CAST(:from_ts AS timestamptz),
    (CAST(:to_ts AS timestamptz) - interval '{_bucket_step(eff_bucket)}'),
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
                {"from_ts": from_ts, "to_ts": to_ts, **_filter_sql_params(filt)},
            )
        ).mappings().all()
        return TimeseriesOut(
            metric=metric,
            range=range_,
            bucket=eff_bucket,
            filter=filt,
            points=[{"ts": r["ts"], "value": r["value"]} for r in rows],
        )

    result, status_ = await cache_or_compute(
        redis, key=cache_key, ttl=ttl_for(range_), model_cls=TimeseriesOut, compute=compute
    )
    response.headers["x-cache"] = status_
    return result


# ----------------------------------------------------------------- /breakdown
#
# 每个 dim 决定：
#   - 分组列 (key_col)、JOIN 表 + label 列、是否需要 WHERE x IS NOT NULL 滤空。
#
# tool_name / application_id / api_key_id 都可能为 NULL（user-owned call、
# 历史 call_logs 等），不滤的话会出现 key=null 的"幽灵桶"。spec §3.2.3 没
# 显式要求，但实际意义就是「Top 调用方」—— null 不是调用方，所以滤掉。
# service_id / status 是 NOT NULL，不滤。

_DIM_CONFIG: dict[Dim, dict[str, str | bool]] = {
    "service": {
        "key_col": "cl.service_id",
        "join": "LEFT JOIN mcp_services e ON e.id = cl.service_id",
        "label_col": "e.slug",
        "extra_group": "e.slug",
        "null_filter": False,
    },
    "application": {
        "key_col": "cl.application_id",
        "join": "LEFT JOIN applications e ON e.id = cl.application_id",
        "label_col": "e.name",
        "extra_group": "e.name",
        "null_filter": True,
    },
    "api_key": {
        "key_col": "cl.api_key_id",
        "join": "LEFT JOIN api_keys e ON e.id = cl.api_key_id",
        "label_col": "e.name",
        "extra_group": "e.name",
        "null_filter": True,
    },
    "tool": {
        "key_col": "cl.tool_name",
        "join": "",
        "label_col": "cl.tool_name",
        "extra_group": "",
        "null_filter": True,
    },
    "status": {
        "key_col": "cl.status::text",
        "join": "",
        "label_col": "cl.status::text",
        "extra_group": "",
        "null_filter": False,
    },
}


def _build_total_sql(dim: Dim) -> str:
    """other 桶的口径要和 Top 行保持一致：top 行滤掉了 null-dim 行（见 _DIM_CONFIG），
    total 这里同样滤，否则 other = total - top 会把 null-dim 行计进"其它"，语义混乱。"""
    cfg = _DIM_CONFIG[dim]
    null_filter = f"AND {cfg['key_col']} IS NOT NULL" if cfg["null_filter"] else ""
    return f"""
SELECT count(*)                                           AS total_count,
       count(*) FILTER (WHERE status != 'success')        AS total_error_count
FROM call_logs cl
WHERE ts >= :from_ts AND ts < :to_ts
  {null_filter}
  AND (CAST(:service_id     AS integer) IS NULL OR cl.service_id     = :service_id)
  AND (CAST(:application_id AS integer) IS NULL OR cl.application_id = :application_id)
  AND (CAST(:api_key_id     AS integer) IS NULL OR cl.api_key_id     = :api_key_id)
"""


def _build_breakdown_sql(dim: Dim, order_by_errors: bool) -> str:
    cfg = _DIM_CONFIG[dim]
    key_col = cfg["key_col"]
    label_col = cfg["label_col"]
    join = cfg["join"]
    extra_group = cfg["extra_group"]
    null_filter = (
        f"AND {key_col} IS NOT NULL" if cfg["null_filter"] else ""
    )
    group_by = f"{key_col}" + (f", {extra_group}" if extra_group else "")
    order_expr = "error_count DESC, count DESC" if order_by_errors else "count DESC"
    return f"""
SELECT {key_col}    AS key,
       {label_col}  AS label,
       count(*)                                       AS count,
       count(*) FILTER (WHERE status != 'success')    AS error_count
FROM call_logs cl
{join}
WHERE ts >= :from_ts AND ts < :to_ts
  {null_filter}
  AND (CAST(:service_id     AS integer) IS NULL OR cl.service_id     = :service_id)
  AND (CAST(:application_id AS integer) IS NULL OR cl.application_id = :application_id)
  AND (CAST(:api_key_id     AS integer) IS NULL OR cl.api_key_id     = :api_key_id)
GROUP BY {group_by}
ORDER BY {order_expr}
LIMIT :limit
"""


@router.get("/breakdown", response_model=BreakdownOut, response_model_by_alias=True)
async def get_breakdown(
    response: Response,
    dim: Dim = Query(...),
    range_: Range = Query("24h", alias="range"),
    metric: Literal["calls", "errors"] = Query("calls"),
    limit: int = Query(10, ge=1, le=50),
    service_id: int | None = Query(None),
    application_id: int | None = Query(None),
    api_key_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    redis: Redis | None = Depends(get_redis),
) -> BreakdownOut:
    filt = pick_filter(service_id, application_id, api_key_id)
    cache_key = (
        f"stats:bd:{dim}:{range_}:{metric}:limit={limit}:{filter_key(filt)}"
    )

    async def compute() -> BreakdownOut:
        from_ts, to_ts = resolve_range(range_)
        params: dict[str, Any] = {
            "from_ts": from_ts,
            "to_ts": to_ts,
            "limit": limit,
            **_filter_sql_params(filt),
        }
        top_rows = (
            await db.execute(
                text(_build_breakdown_sql(dim, order_by_errors=(metric == "errors"))),
                params,
            )
        ).mappings().all()

        rows: list[BreakdownRow] = []
        top_count = 0
        top_error = 0
        for r in top_rows:
            cnt = r["count"] or 0
            err = r["error_count"] or 0
            top_count += cnt
            top_error += err
            rows.append(
                BreakdownRow(
                    key=r["key"],
                    label=r["label"],
                    count=cnt,
                    error_count=err,
                    error_rate=(err / cnt) if cnt else 0.0,
                )
            )

        # 计算 other 桶：仅当 Top 不止 limit 行的可能时才需要查总数。
        # 简单起见无条件查（一条快查），rows < limit 时 other = 0/0 → 不返回。
        total_row = (
            await db.execute(
                text(_build_total_sql(dim)),
                {"from_ts": from_ts, "to_ts": to_ts, **_filter_sql_params(filt)},
            )
        ).mappings().one()
        total_count = total_row["total_count"] or 0
        total_error = total_row["total_error_count"] or 0
        other_count = max(total_count - top_count, 0)
        other_error = max(total_error - top_error, 0)
        other = (
            BreakdownOther(count=other_count, error_count=other_error)
            if other_count > 0 or other_error > 0
            else None
        )

        return BreakdownOut(
            dim=dim,
            range=range_,
            metric=metric,  # type: ignore[arg-type]
            filter=filt,
            rows=rows,
            other=other,
        )

    result, status_ = await cache_or_compute(
        redis, key=cache_key, ttl=ttl_for(range_), model_cls=BreakdownOut, compute=compute
    )
    response.headers["x-cache"] = status_
    return result


# --------------------------------------------------------- /latency-histogram

_LATENCY_SQL = text("""
SELECT
  count(*) FILTER (WHERE duration_ms <   50)                          AS b0,
  count(*) FILTER (WHERE duration_ms >=   50 AND duration_ms <  100)  AS b1,
  count(*) FILTER (WHERE duration_ms >=  100 AND duration_ms <  200)  AS b2,
  count(*) FILTER (WHERE duration_ms >=  200 AND duration_ms <  500)  AS b3,
  count(*) FILTER (WHERE duration_ms >=  500 AND duration_ms < 1000)  AS b4,
  count(*) FILTER (WHERE duration_ms >= 1000 AND duration_ms < 2000)  AS b5,
  count(*) FILTER (WHERE duration_ms >= 2000)                         AS b6
FROM call_logs
WHERE ts >= :from_ts AND ts < :to_ts
  AND (CAST(:service_id     AS integer) IS NULL OR service_id     = :service_id)
  AND (CAST(:application_id AS integer) IS NULL OR application_id = :application_id)
  AND (CAST(:api_key_id     AS integer) IS NULL OR api_key_id     = :api_key_id)
""")


@router.get(
    "/latency-histogram",
    response_model=LatencyHistogramOut,
    response_model_by_alias=True,
)
async def get_latency_histogram(
    response: Response,
    range_: Range = Query("24h", alias="range"),
    service_id: int | None = Query(None),
    application_id: int | None = Query(None),
    api_key_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    redis: Redis | None = Depends(get_redis),
) -> LatencyHistogramOut:
    filt = pick_filter(service_id, application_id, api_key_id)
    cache_key = f"stats:lat:{range_}:{filter_key(filt)}"

    async def compute() -> LatencyHistogramOut:
        from_ts, to_ts = resolve_range(range_)
        row = (
            await db.execute(
                _LATENCY_SQL,
                {"from_ts": from_ts, "to_ts": to_ts, **_filter_sql_params(filt)},
            )
        ).mappings().one()
        buckets = [
            LatencyBucket(lo=lo, hi=hi, count=row[f"b{i}"] or 0)
            for i, (lo, hi) in enumerate(_LATENCY_BOUNDS)
        ]
        return LatencyHistogramOut(range=range_, filter=filt, buckets=buckets)

    result, status_ = await cache_or_compute(
        redis,
        key=cache_key,
        ttl=ttl_for(range_),
        model_cls=LatencyHistogramOut,
        compute=compute,
    )
    response.headers["x-cache"] = status_
    return result
