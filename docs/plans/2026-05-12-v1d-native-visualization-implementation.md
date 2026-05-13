# V1-D 原生可视化（替换 Grafana → Vue + ECharts）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 control-plane 出的 4 个聚合端点 + 前端 Vue + ECharts 完全替换 Grafana 容器；DashboardPage 重写，三类详情页（service / application / api_key）加"概况"区块（顶部 KPI 行 + Sparkline + Top BarChart），两类列表页（call-logs / audit-events）加 sparkline；call-logs 列表接受 query filter 完成 drill-down 闭环。

**Architecture:** Postgres `call_logs` 即时聚合（`date_trunc` + `percentile_cont`）+ Redis 30s 短 TTL 缓存。前端 `vue-echarts` 按需引入；图表组件统一放 `services/web/src/components/charts/`；Drill-down 走 `router.push({path, query})`。**不**新增表 / 不预聚合 / 不留 Grafana fallback。

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Pydantic v2, pytest + testcontainers, Vue 3 + Element Plus, ECharts 5 + vue-echarts 7, vitest

**Spec:** `docs/specs/2026-05-12-v1d-native-visualization-design.md`

**PR 拆分**（spec §9 节奏）：
- **PR 1** — 后端 stats 4 端点 + cache + 单测 + smoke 扩展（Tasks 1–7）
- **PR 2** — 前端图表基建：vue-echarts 按需引入、chart-theme、`stats.ts` API 层、6 个公共组件（Tasks 8–10）
- **PR 3** — DashboardPage 原生化 + RangePicker；移除 Grafana 容器与 nginx 反代（Tasks 11–12）
- **PR 4** — 三个详情页加概况区块（Tasks 13–15）
- **PR 5** — call-logs / audit-events 列表 sparkline；call-logs 接受 query filter（drill-down 落地）（Tasks 16–17）
- **PR 6** — README / deployment / spec 注脚 + 删除 `grafana/provisioning/` 目录（Task 18）

PR 1 / PR 2 可并行；PR 3 是分水岭（合入后 Grafana 完全下线，必须先确认 PR 1/2 都已部署）。

合计 1.5–2 周。

---

# PR 1 — 后端 stats 端点 + cache + smoke

## Task 1 — `routers/stats.py` 骨架 + Pydantic schemas + 时间窗工具

**Files:**
- Create: `services/control_plane/src/control_plane/schemas/stats.py`
- Create: `services/control_plane/src/control_plane/routers/stats.py`
- Edit: `services/control_plane/src/control_plane/main.py`（注册新 router）

- [ ] **Step 1: schemas/stats.py — Pydantic 类型**

```python
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
    value: float | int | None  # error_rate / 分位为 float，calls / errors / throttled 为 int


class TimeseriesOut(BaseModel):
    metric: Metric
    range: Range
    bucket: Bucket
    filter: StatsFilter | None
    points: list[TimeseriesPoint]


class BreakdownRow(BaseModel):
    key: int | str | None  # service/app/key 为 int；tool/status 为 str；NULL service_id 时为 None
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
    hi: int | None  # +∞ overflow bucket
    count: int


class LatencyHistogramOut(BaseModel):
    range: Range
    filter: StatsFilter | None
    buckets: list[LatencyBucket]
```

- [ ] **Step 2: routers/stats.py — 时间窗解析 + filter 互斥工具**

```python
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db, get_redis, require_role
from ..schemas.stats import (
    Bucket, Dim, Metric, Range, StatsFilter,
    OverviewOut, TimeseriesOut, BreakdownOut, LatencyHistogramOut,
)

router = APIRouter(
    prefix="/api/v1/stats",
    tags=["stats"],
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)

_RANGE_DELTA: dict[Range, timedelta] = {
    "15m": timedelta(minutes=15),
    "1h":  timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d":  timedelta(days=7),
}

_DEFAULT_BUCKET: dict[Range, Bucket] = {
    "15m": "1m",
    "1h":  "1m",
    "24h": "5m",
    "7d":  "1h",
}


def resolve_range(range_: Range, now: datetime | None = None) -> tuple[datetime, datetime]:
    """返回 (from_ts, to_ts)，UTC。`to_ts` 对齐到当前分钟（避免半桶抖动）。"""
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
```

- [ ] **Step 3: 注册 router 到 main.py**

```python
# services/control_plane/src/control_plane/main.py
from .routers import (
    api_keys, applications, audit_events, auth, call_logs,
    permissions, services, stats, users,
)
...
app.include_router(stats.router)
```

**Verification:**

```bash
uv run --package control-plane pytest services/control_plane/tests/ -k "not stats" -x  # 无回归
curl -fsS http://localhost:8088/api/v1/stats/overview?range=24h -H "Authorization: Bearer $TOKEN"
# 期望：404（端点尚未实现）；只要不是 500 即 OK，路由层挂载正确
```

---

## Task 2 — Overview 端点 + 单测

**Files:**
- Edit: `services/control_plane/src/control_plane/routers/stats.py`
- Create: `services/control_plane/tests/test_stats_overview.py`

- [ ] **Step 1: overview handler**

```python
from sqlalchemy import text


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
    redis: Redis | None = Depends(get_redis),
) -> OverviewOut:
    filt = pick_filter(service_id, application_id, api_key_id)
    from_ts, to_ts = resolve_range(range_)

    # cache lookup (Task 6 接入；先占位)
    # ...

    row = (await db.execute(
        _OVERVIEW_SQL,
        {
            "from_ts": from_ts,
            "to_ts": to_ts,
            "service_id":     filt.service_id     if filt else None,
            "application_id": filt.application_id if filt else None,
            "api_key_id":     filt.api_key_id     if filt else None,
        },
    )).mappings().one()

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
```

> **注意**：`response_model_by_alias=True` 让 `from_` 字段以 `from` 序列化（避开 Python 关键字）。

- [ ] **Step 2: 测试 fixtures — call_logs 工厂**

参考 `services/control_plane/tests/conftest.py` 现有的 fixture 模式：

```python
# tests/test_stats_overview.py
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from mcpsys_shared.models import CallLog, CallStatus


async def _log(db, *, ts=None, status=CallStatus.success, duration_ms=10,
               service_id=None, application_id=None, api_key_id=None,
               tool_name="tools/list"):
    db.add(CallLog(
        id=uuid.uuid4(),
        ts=ts or datetime.now(timezone.utc),
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
    ))
    await db.flush()
```

- [ ] **Step 3: happy / empty / filter / priority 4 例**

```python
async def test_overview_24h_happy(client, admin_token, db):
    now = datetime.now(timezone.utc)
    for i in range(8):
        await _log(db, ts=now - timedelta(hours=1), duration_ms=10 + i * 5)
    await _log(db, ts=now - timedelta(hours=2), status=CallStatus.error, duration_ms=200)
    await _log(db, ts=now - timedelta(hours=2), status=CallStatus.throttled, duration_ms=0)
    await db.commit()

    resp = await client.get("/api/v1/stats/overview?range=24h",
                            headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["calls"] == 10
    assert data["errors"] == 2     # error + throttled (status != success)
    assert data["throttled"] == 1
    assert 0 < data["error_rate"] < 1
    assert data["p50_ms"] is not None
    assert data["last_call_at"] is not None
    assert data["filter"] is None


async def test_overview_empty(client, admin_token):
    resp = await client.get("/api/v1/stats/overview?range=24h",
                            headers={"Authorization": f"Bearer {admin_token}"})
    data = resp.json()
    assert data["calls"] == 0
    assert data["errors"] == 0
    assert data["error_rate"] == 0.0
    assert data["p50_ms"] is None
    assert data["last_call_at"] is None


async def test_overview_with_service_filter(client, admin_token, db, service_a, service_b):
    now = datetime.now(timezone.utc)
    for _ in range(100):
        await _log(db, ts=now - timedelta(minutes=10), service_id=service_a.id)
    for _ in range(50):
        await _log(db, ts=now - timedelta(minutes=10), service_id=service_b.id)
    await db.commit()

    resp = await client.get(
        f"/api/v1/stats/overview?range=24h&service_id={service_a.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    data = resp.json()
    assert data["calls"] == 100
    assert data["filter"] == {"service_id": service_a.id, "application_id": None, "api_key_id": None}


async def test_overview_filter_priority(client, admin_token, db, service_a):
    # spec §3.2.1 优先级：service_id > application_id > api_key_id
    await _log(db, service_id=service_a.id)
    await db.commit()

    resp = await client.get(
        f"/api/v1/stats/overview?range=24h&service_id={service_a.id}&application_id=999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    data = resp.json()
    assert data["filter"]["service_id"] == service_a.id
    assert data["filter"]["application_id"] is None


async def test_overview_viewer_can_read(client, viewer_token):
    resp = await client.get("/api/v1/stats/overview?range=24h",
                            headers={"Authorization": f"Bearer {viewer_token}"})
    assert resp.status_code == 200


async def test_overview_unauthenticated_rejected(client):
    resp = await client.get("/api/v1/stats/overview?range=24h")
    assert resp.status_code == 401


async def test_overview_invalid_range_422(client, admin_token):
    resp = await client.get("/api/v1/stats/overview?range=foo",
                            headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 422
```

`service_a` / `service_b` / `viewer_token` fixtures 复用 `conftest.py` 已有的工厂；若没有，跟 `tests/test_call_logs.py` 同款写法新增。

**Verification:**

```bash
uv run --package control-plane pytest services/control_plane/tests/test_stats_overview.py -v
# 期望：7 passed
```

---

## Task 3 — Timeseries 端点 + 单测

**Files:**
- Edit: `services/control_plane/src/control_plane/routers/stats.py`
- Create: `services/control_plane/tests/test_stats_timeseries.py`

- [ ] **Step 1: bucket SQL 拼装**

bucket truncation 用 `date_trunc` + 分钟取模算术：

```python
def _bucket_expr(bucket: Bucket) -> str:
    """返回 SQL bucket 列表达式，命名为 bucket_ts。"""
    if bucket == "1m":
        return "date_trunc('minute', ts) AS bucket_ts"
    if bucket == "5m":
        return ("date_trunc('minute', ts) - "
                "make_interval(mins => (extract(minute FROM ts)::int % 5)) AS bucket_ts")
    if bucket == "1h":
        return "date_trunc('hour', ts) AS bucket_ts"
    raise ValueError(bucket)


def _bucket_step(bucket: Bucket) -> str:
    """series 步长。"""
    return {"1m": "1 minute", "5m": "5 minutes", "1h": "1 hour"}[bucket]


def _metric_expr(metric: Metric) -> str:
    if metric == "calls":      return "count(*)"
    if metric == "errors":     return "count(*) FILTER (WHERE status != 'success')"
    if metric == "throttled":  return "count(*) FILTER (WHERE status = 'throttled')"
    if metric == "error_rate":
        return ("CASE WHEN count(*) = 0 THEN 0.0 "
                "ELSE count(*) FILTER (WHERE status != 'success')::float / count(*) END")
    if metric == "p50": return "percentile_cont(0.50) WITHIN GROUP (ORDER BY duration_ms)"
    if metric == "p95": return "percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)"
    if metric == "p99": return "percentile_cont(0.99) WITHIN GROUP (ORDER BY duration_ms)"
    raise ValueError(metric)
```

- [ ] **Step 2: handler**

```python
@router.get("/timeseries", response_model=TimeseriesOut, response_model_by_alias=True)
async def get_timeseries(
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

    rows = (await db.execute(sql, {
        "from_ts": from_ts, "to_ts": to_ts,
        "service_id":     filt.service_id     if filt else None,
        "application_id": filt.application_id if filt else None,
        "api_key_id":     filt.api_key_id     if filt else None,
    })).mappings().all()

    return TimeseriesOut(
        metric=metric, range=range_, bucket=eff_bucket, filter=filt,
        points=[{"ts": r["ts"], "value": r["value"]} for r in rows],
    )
```

- [ ] **Step 3: 测试**

```python
async def test_timeseries_calls_bucket_5m(client, admin_token, db):
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    # 跨 3 个 5m bucket，每个 bucket 写不同数量
    await _log(db, ts=now - timedelta(minutes=2))
    await _log(db, ts=now - timedelta(minutes=2))
    await _log(db, ts=now - timedelta(minutes=7))
    await db.commit()

    resp = await client.get(
        "/api/v1/stats/timeseries?metric=calls&range=1h&bucket=5m",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    data = resp.json()
    assert data["bucket"] == "5m"
    # 1h / 5m = 12 个 bucket，且空 bucket 用 0 填充
    assert len(data["points"]) == 12
    assert sum(p["value"] for p in data["points"]) == 3


async def test_timeseries_default_bucket_by_range(client, admin_token):
    for r, expected_bucket in [("15m", "1m"), ("1h", "1m"), ("24h", "5m"), ("7d", "1h")]:
        resp = await client.get(
            f"/api/v1/stats/timeseries?metric=calls&range={r}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.json()["bucket"] == expected_bucket


async def test_timeseries_p95_with_service_filter(client, admin_token, db, service_a, service_b):
    now = datetime.now(timezone.utc) - timedelta(minutes=5)
    for i in range(100):
        await _log(db, ts=now, service_id=service_a.id, duration_ms=10)
    for i in range(100):
        await _log(db, ts=now, service_id=service_b.id, duration_ms=1000)
    await db.commit()

    resp = await client.get(
        f"/api/v1/stats/timeseries?metric=p95&range=1h&service_id={service_a.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    nonzero = [p for p in resp.json()["points"] if p["value"]]
    # service_a 全部 10ms，p95 应该接近 10，远小于 service_b 的 1000
    assert all(p["value"] < 100 for p in nonzero)


async def test_timeseries_error_rate_no_data_zero(client, admin_token):
    resp = await client.get(
        "/api/v1/stats/timeseries?metric=error_rate&range=1h",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert all(p["value"] == 0 for p in resp.json()["points"])
```

**Verification:**

```bash
uv run --package control-plane pytest services/control_plane/tests/test_stats_timeseries.py -v
# 期望：4 passed
```

---

## Task 4 — Breakdown 端点 + 单测

**Files:**
- Edit: `services/control_plane/src/control_plane/routers/stats.py`
- Create: `services/control_plane/tests/test_stats_breakdown.py`

- [ ] **Step 1: dim → SQL column / join 表**

```python
# (column_expr_for_group_by, label_expr, join_clause)
_DIM_MAPPING = {
    "service":     ("cl.service_id",     "s.slug",
                    "LEFT JOIN mcp_services s ON s.id = cl.service_id"),
    "application": ("cl.application_id", "a.name",
                    "LEFT JOIN applications a ON a.id = cl.application_id"),
    "api_key":     ("cl.api_key_id",     "k.name",
                    "LEFT JOIN api_keys k ON k.id = cl.api_key_id"),
    "tool":        ("cl.tool_name",      "cl.tool_name", ""),
    "status":      ("cl.status",         "cl.status", ""),
}
```

- [ ] **Step 2: handler**

```python
@router.get("/breakdown", response_model=BreakdownOut, response_model_by_alias=True)
async def get_breakdown(
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
    from_ts, to_ts = resolve_range(range_)
    col, label_expr, join_clause = _DIM_MAPPING[dim]
    order_expr = "count" if metric == "calls" else "error_count"

    sql = text(f"""
WITH agg AS (
  SELECT {col} AS key,
         {label_expr} AS label,
         count(*) AS count,
         count(*) FILTER (WHERE cl.status != 'success') AS error_count
  FROM call_logs cl {join_clause}
  WHERE cl.ts >= :from_ts AND cl.ts < :to_ts
    AND (CAST(:service_id     AS integer) IS NULL OR cl.service_id     = :service_id)
    AND (CAST(:application_id AS integer) IS NULL OR cl.application_id = :application_id)
    AND (CAST(:api_key_id     AS integer) IS NULL OR cl.api_key_id     = :api_key_id)
  GROUP BY {col}, {label_expr}
)
SELECT * FROM agg ORDER BY {order_expr} DESC LIMIT :limit
""")
    rows = (await db.execute(sql, {
        "from_ts": from_ts, "to_ts": to_ts, "limit": limit,
        "service_id":     filt.service_id     if filt else None,
        "application_id": filt.application_id if filt else None,
        "api_key_id":     filt.api_key_id     if filt else None,
    })).mappings().all()

    # other bucket = 总 - sum(top)
    total = await db.execute(text(f"""
        SELECT count(*) AS c, count(*) FILTER (WHERE status != 'success') AS e
        FROM call_logs WHERE ts >= :from_ts AND ts < :to_ts
          AND (CAST(:service_id     AS integer) IS NULL OR service_id     = :service_id)
          AND (CAST(:application_id AS integer) IS NULL OR application_id = :application_id)
          AND (CAST(:api_key_id     AS integer) IS NULL OR api_key_id     = :api_key_id)
    """), {
        "from_ts": from_ts, "to_ts": to_ts,
        "service_id":     filt.service_id     if filt else None,
        "application_id": filt.application_id if filt else None,
        "api_key_id":     filt.api_key_id     if filt else None,
    })
    t = total.mappings().one()
    top_count = sum(r["count"] for r in rows)
    top_err   = sum(r["error_count"] for r in rows)
    other = None
    if t["c"] > top_count:
        other = {"count": t["c"] - top_count, "error_count": t["e"] - top_err}

    return BreakdownOut(
        dim=dim, range=range_, metric=metric, filter=filt,
        rows=[
            {
                "key": r["key"],
                "label": r["label"],
                "count": r["count"],
                "error_count": r["error_count"],
                "error_rate": (r["error_count"] / r["count"]) if r["count"] else 0.0,
            } for r in rows
        ],
        other=other,
    )
```

- [ ] **Step 3: 测试**

```python
async def test_breakdown_top_services_with_other(client, admin_token, db):
    services = [await _make_service(db, slug=f"svc-{i}") for i in range(12)]
    for i, s in enumerate(services):
        for _ in range(10 + i):  # 越靠后越多
            await _log(db, service_id=s.id)
    await db.commit()

    resp = await client.get(
        "/api/v1/stats/breakdown?dim=service&range=24h&limit=10",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    data = resp.json()
    assert len(data["rows"]) == 10
    assert data["other"] is not None
    # 12 个服务，top 10 = i in [2..11]，剩下 i=0 (10 calls) + i=1 (11 calls) = 21 进 other
    assert data["other"]["count"] == 10 + 11


async def test_breakdown_dim_tool(client, admin_token, db):
    for tool in ["tools/list", "tools/call:get_weather", "tools/call:get_weather", "tools/call:get_news"]:
        await _log(db, tool_name=tool)
    await db.commit()

    resp = await client.get(
        "/api/v1/stats/breakdown?dim=tool&range=24h",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    rows = resp.json()["rows"]
    top = next(r for r in rows if r["key"] == "tools/call:get_weather")
    assert top["count"] == 2


async def test_breakdown_dim_status(client, admin_token, db):
    await _log(db, status=CallStatus.success)
    await _log(db, status=CallStatus.error)
    await _log(db, status=CallStatus.throttled)
    await db.commit()

    resp = await client.get(
        "/api/v1/stats/breakdown?dim=status&range=24h",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    keys = {r["key"] for r in resp.json()["rows"]}
    assert keys == {"success", "error", "throttled"}


async def test_breakdown_limit_clamped(client, admin_token):
    resp = await client.get(
        "/api/v1/stats/breakdown?dim=service&range=24h&limit=51",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422  # le=50
```

**Verification:**

```bash
uv run --package control-plane pytest services/control_plane/tests/test_stats_breakdown.py -v
```

---

## Task 5 — Latency Histogram 端点 + 单测

**Files:**
- Edit: `services/control_plane/src/control_plane/routers/stats.py`
- Create: `services/control_plane/tests/test_stats_latency.py`

- [ ] **Step 1: 固定 bucket 边界 + handler**

```python
_HIST_BOUNDS = [0, 50, 100, 200, 500, 1000, 2000]  # 最后一档 hi=None 为 overflow


@router.get("/latency-histogram", response_model=LatencyHistogramOut,
            response_model_by_alias=True)
async def get_latency_histogram(
    range_: Range = Query("24h", alias="range"),
    service_id: int | None = Query(None),
    application_id: int | None = Query(None),
    api_key_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    redis: Redis | None = Depends(get_redis),
) -> LatencyHistogramOut:
    filt = pick_filter(service_id, application_id, api_key_id)
    from_ts, to_ts = resolve_range(range_)

    # 用一组 FILTER 一次性算齐
    expr = ", ".join(
        f"count(*) FILTER (WHERE duration_ms >= {lo} AND duration_ms < {hi}) AS b_{lo}"
        for lo, hi in zip(_HIST_BOUNDS, _HIST_BOUNDS[1:] + [None])
        if hi is not None
    ) + f", count(*) FILTER (WHERE duration_ms >= {_HIST_BOUNDS[-1]}) AS b_overflow"

    sql = text(f"""
SELECT {expr}
FROM call_logs
WHERE ts >= :from_ts AND ts < :to_ts
  AND (CAST(:service_id     AS integer) IS NULL OR service_id     = :service_id)
  AND (CAST(:application_id AS integer) IS NULL OR application_id = :application_id)
  AND (CAST(:api_key_id     AS integer) IS NULL OR api_key_id     = :api_key_id)
""")
    row = (await db.execute(sql, {
        "from_ts": from_ts, "to_ts": to_ts,
        "service_id":     filt.service_id     if filt else None,
        "application_id": filt.application_id if filt else None,
        "api_key_id":     filt.api_key_id     if filt else None,
    })).mappings().one()

    buckets = []
    for lo, hi in zip(_HIST_BOUNDS, _HIST_BOUNDS[1:]):
        buckets.append({"lo": lo, "hi": hi, "count": row[f"b_{lo}"] or 0})
    buckets.append({"lo": _HIST_BOUNDS[-1], "hi": None, "count": row["b_overflow"] or 0})

    return LatencyHistogramOut(range=range_, filter=filt, buckets=buckets)
```

- [ ] **Step 2: 测试**

```python
async def test_latency_histogram_overflow_bucket(client, admin_token, db):
    for ms in [10, 30, 60, 150, 800, 5000, 5000]:
        await _log(db, duration_ms=ms)
    await db.commit()

    resp = await client.get(
        "/api/v1/stats/latency-histogram?range=24h",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    data = resp.json()
    by_lo = {b["lo"]: b["count"] for b in data["buckets"]}
    assert by_lo[0]   == 2   # 10, 30
    assert by_lo[50]  == 1   # 60
    assert by_lo[100] == 1   # 150
    assert by_lo[500] == 1   # 800
    assert by_lo[2000] == 2  # 5000 ×2 (overflow)
    overflow = next(b for b in data["buckets"] if b["hi"] is None)
    assert overflow["lo"] == 2000


async def test_latency_histogram_empty(client, admin_token):
    resp = await client.get(
        "/api/v1/stats/latency-histogram?range=24h",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert all(b["count"] == 0 for b in resp.json()["buckets"])
```

**Verification:**

```bash
uv run --package control-plane pytest services/control_plane/tests/test_stats_latency.py -v
```

---

## Task 6 — Redis Cache 接入 + 测试

**Files:**
- Create: `services/control_plane/src/control_plane/cache_stats.py`
- Edit: `services/control_plane/src/control_plane/routers/stats.py`（4 个 handler 接入 cache）
- Create: `services/control_plane/tests/test_stats_cache.py`

- [ ] **Step 1: cache_stats 模块**

```python
# services/control_plane/src/control_plane/cache_stats.py
import logging

import orjson
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_TTL_BY_RANGE = {"15m": 10, "1h": 30, "24h": 30, "7d": 30}


def ttl_for(range_: str) -> int:
    return _TTL_BY_RANGE.get(range_, 30)


def filter_key(filt) -> str:
    if filt is None:
        return "none"
    if filt.service_id is not None:     return f"svc={filt.service_id}"
    if filt.application_id is not None: return f"app={filt.application_id}"
    if filt.api_key_id is not None:     return f"key={filt.api_key_id}"
    return "none"


async def get_or_compute(
    redis: Redis | None,
    *,
    key: str,
    ttl: int,
    compute,  # async () -> pydantic BaseModel
):
    """返回 (model, is_hit). Redis 不可用 → 直接 compute, is_hit=False."""
    if redis is None:
        return await compute(), False
    try:
        cached = await redis.get(key)
        if cached:
            return orjson.loads(cached), True
        result = await compute()
        await redis.setex(key, ttl, orjson.dumps(result.model_dump(by_alias=True, mode="json")))
        return result, False
    except Exception as e:  # graceful degrade
        logger.warning("stats cache error key=%s err=%s", key, e)
        return await compute(), False
```

- [ ] **Step 2: 4 个 handler 包一层 cache**

每个 handler 末尾把"算 + 返回"逻辑封进闭包：

```python
@router.get("/overview", ...)
async def get_overview(..., response: Response):
    filt = pick_filter(...)
    from_ts, to_ts = resolve_range(range_)
    cache_key = f"stats:overview:{range_}:filter={filter_key(filt)}"

    async def _compute() -> OverviewOut:
        row = (await db.execute(_OVERVIEW_SQL, {...})).mappings().one()
        ...
        return OverviewOut(...)

    result, hit = await get_or_compute(redis, key=cache_key, ttl=ttl_for(range_), compute=_compute)
    response.headers["x-cache"] = "hit" if hit else "miss"

    # cache 命中时 result 是 dict，需要再 validate 回 model
    if isinstance(result, dict):
        return OverviewOut.model_validate(result)
    return result
```

> **取舍**：cache 存的是 JSON 序列化后的 dict，命中时直接 `OverviewOut.model_validate` 回模型，避免重复算。

每个端点 cache key 形态：
- `stats:overview:{range}:filter={...}`
- `stats:ts:{metric}:{range}:{bucket}:filter={...}`
- `stats:bd:{dim}:{range}:{metric}:limit={n}:filter={...}`
- `stats:hist:{range}:filter={...}`

- [ ] **Step 3: 测试**

```python
async def test_overview_caches_30s(client, admin_token, redis):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r1 = await client.get("/api/v1/stats/overview?range=24h", headers=headers)
    assert r1.headers["x-cache"] == "miss"
    r2 = await client.get("/api/v1/stats/overview?range=24h", headers=headers)
    assert r2.headers["x-cache"] == "hit"
    assert r1.json() == r2.json()


async def test_overview_15m_shorter_ttl(client, admin_token, redis):
    await client.get("/api/v1/stats/overview?range=15m",
                     headers={"Authorization": f"Bearer {admin_token}"})
    ttl = await redis.ttl("stats:overview:15m:filter=none")
    assert 0 < ttl <= 10


async def test_cache_bypass_when_redis_down(client, admin_token, monkeypatch):
    # mock redis.get → 抛 ConnectionError
    from control_plane import cache_stats
    async def boom(*a, **kw): raise ConnectionError("redis down")
    monkeypatch.setattr("redis.asyncio.Redis.get", boom)

    resp = await client.get("/api/v1/stats/overview?range=24h",
                            headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.headers["x-cache"] == "miss"


async def test_cache_isolated_by_filter(client, admin_token, redis, service_a):
    headers = {"Authorization": f"Bearer {admin_token}"}
    await client.get("/api/v1/stats/overview?range=24h", headers=headers)
    await client.get(f"/api/v1/stats/overview?range=24h&service_id={service_a.id}", headers=headers)
    keys = await redis.keys("stats:overview:*")
    assert len(keys) == 2
```

**Verification:**

```bash
uv run --package control-plane pytest services/control_plane/tests/test_stats_cache.py -v
```

---

## Task 7 — Smoke 扩展

**Files:**
- Edit: `scripts/smoke.sh`

- [ ] **Step 1: 在 audit 校验段之前加 stats 校验**

```bash
echo "[smoke] verifying stats endpoints ..."

# overview (global)
OV=$(curl -fsS "$BASE/api/v1/stats/overview?range=24h" -H "Authorization: Bearer $TOKEN")
echo "$OV" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'calls' in d and 'p95_ms' in d, d" || {
  echo "[smoke] FAIL: overview response shape"; exit 1; }

# timeseries with default bucket
N=$(curl -fsS "$BASE/api/v1/stats/timeseries?metric=calls&range=1h" -H "Authorization: Bearer $TOKEN" \
   | python3 -c "import sys,json; print(len(json.load(sys.stdin)['points']))")
test "$N" -eq 60 || { echo "[smoke] FAIL: expected 60 points for 1h/1m"; exit 1; }

# breakdown
curl -fsS "$BASE/api/v1/stats/breakdown?dim=service&range=24h" -H "Authorization: Bearer $TOKEN" | jq -e '.rows' >/dev/null

# overview with service filter (after smoke-svc has some traffic)
curl -fsS "$BASE/api/v1/stats/overview?range=24h&service_id=1" -H "Authorization: Bearer $TOKEN" >/dev/null
```

**Verification:**

```bash
./scripts/smoke.sh
# 期望：全部 PASS；末尾 "[smoke] OK"
```

---

# PR 2 — 前端图表基建

## Task 8 — 安装 ECharts + 按需引入 + chart-theme

**Files:**
- Edit: `services/web/package.json`
- Create: `services/web/src/components/charts/echarts-setup.ts`
- Create: `services/web/src/components/charts/chart-theme.ts`

- [ ] **Step 1: 安装依赖**

```bash
cd services/web
pnpm add echarts@^5 vue-echarts@^7
```

- [ ] **Step 2: echarts-setup.ts**

```ts
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { LineChart, BarChart } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, LegendComponent,
  DataZoomComponent, MarkLineComponent, AxisPointerComponent,
} from 'echarts/components';

use([
  CanvasRenderer, LineChart, BarChart,
  GridComponent, TooltipComponent, LegendComponent,
  DataZoomComponent, MarkLineComponent, AxisPointerComponent,
]);
```

- [ ] **Step 3: chart-theme.ts**

```ts
// 与项目 CSS variable 对齐；hex 值与 src/styles/tokens.scss 同步
export const colors = {
  primary:  '#3b82f6',
  success:  '#10b981',
  warning:  '#f59e0b',
  danger:   '#ef4444',
  gray400:  '#9ca3af',
  gray200:  '#e5e7eb',
};

export function getMetricColor(metric: string): string {
  if (metric === 'errors' || metric === 'error_rate') return colors.danger;
  if (metric === 'throttled') return colors.warning;
  if (metric.startsWith('p')) return colors.success;
  return colors.primary;
}

export const defaultLineOption = {
  textStyle: { fontFamily: 'inherit', fontSize: 12, color: '#4b5563' },
  grid: { left: 48, right: 16, top: 24, bottom: 32 },
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#fff',
    borderColor: colors.gray200,
    textStyle: { color: '#111827' },
  },
};
```

- [ ] **Step 4: main.ts 注册全局组件（可选）**

不全局注册，让每个图表组件自己 import VChart from 'vue-echarts'，避免污染。

**Verification:**

```bash
cd services/web && pnpm typecheck
# 期望：clean
```

---

## Task 9 — `api/stats.ts` 数据层

**Files:**
- Create: `services/web/src/api/stats.ts`

- [ ] **Step 1: 类型 + 函数签名**

```ts
import { client } from './client';

export type Range = '15m' | '1h' | '24h' | '7d';
export type Metric = 'calls' | 'errors' | 'error_rate' | 'p50' | 'p95' | 'p99' | 'throttled';
export type Bucket = '1m' | '5m' | '1h';
export type Dim = 'service' | 'application' | 'api_key' | 'tool' | 'status';

export interface StatsFilter {
  service_id?: number | null;
  application_id?: number | null;
  api_key_id?: number | null;
}

export interface OverviewResp {
  range: Range;
  from: string;
  to: string;
  filter: StatsFilter | null;
  calls: number;
  errors: number;
  error_rate: number;
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  throttled: number;
  denied: number;
  last_call_at: string | null;
}

export interface TimeseriesPoint { ts: string; value: number | null; }
export interface TimeseriesResp {
  metric: Metric; range: Range; bucket: Bucket;
  filter: StatsFilter | null;
  points: TimeseriesPoint[];
}

export interface BreakdownRow {
  key: number | string | null;
  label: string | null;
  count: number;
  error_count: number;
  error_rate: number;
}
export interface BreakdownResp {
  dim: Dim; range: Range; metric: 'calls' | 'errors';
  filter: StatsFilter | null;
  rows: BreakdownRow[];
  other: { count: number; error_count: number } | null;
}

export interface LatencyBucket { lo: number; hi: number | null; count: number; }
export interface LatencyHistogramResp {
  range: Range; filter: StatsFilter | null;
  buckets: LatencyBucket[];
}

export function getOverview(params: {
  range: Range;
  service_id?: number;
  application_id?: number;
  api_key_id?: number;
}): Promise<OverviewResp> {
  return client.get('/api/v1/stats/overview', { params }).then((r) => r.data);
}

export function getTimeseries(params: {
  metric: Metric; range: Range; bucket?: Bucket;
  service_id?: number; application_id?: number; api_key_id?: number;
}): Promise<TimeseriesResp> {
  return client.get('/api/v1/stats/timeseries', { params }).then((r) => r.data);
}

export function getBreakdown(params: {
  dim: Dim; range: Range; metric?: 'calls' | 'errors'; limit?: number;
  service_id?: number; application_id?: number; api_key_id?: number;
}): Promise<BreakdownResp> {
  return client.get('/api/v1/stats/breakdown', { params }).then((r) => r.data);
}

export function getLatencyHistogram(params: {
  range: Range;
  service_id?: number; application_id?: number; api_key_id?: number;
}): Promise<LatencyHistogramResp> {
  return client.get('/api/v1/stats/latency-histogram', { params }).then((r) => r.data);
}
```

**Verification:**

```bash
cd services/web && pnpm typecheck
```

---

## Task 10 — 6 个公共图表组件

**Files:**
- Create: `services/web/src/components/charts/KpiCard.vue`
- Create: `services/web/src/components/charts/TimeseriesChart.vue`
- Create: `services/web/src/components/charts/BarChart.vue`
- Create: `services/web/src/components/charts/Sparkline.vue`
- Create: `services/web/src/components/charts/LatencyHistogram.vue`
- Create: `services/web/src/components/charts/RangePicker.vue`

- [ ] **Step 1: KpiCard.vue（抽出 DashboardPage 内联代码）**

```vue
<script setup lang="ts">
interface Props {
  label: string;
  value: string | number;
  sub?: string;
  tone?: 'primary' | 'success' | 'warning' | 'danger' | 'info';
  loading?: boolean;
  icon?: string;
}
const { tone = 'info' } = defineProps<Props>();
</script>

<template>
  <div class="kpi-card">
    <div :class="['kpi-card__icon', `kpi-card__icon--${tone}`]">
      <slot name="icon" />
    </div>
    <div class="kpi-card__main">
      <div class="kpi-card__label">{{ label }}</div>
      <div class="kpi-card__value">{{ loading ? '—' : value }}</div>
      <div v-if="sub" class="kpi-card__sub">{{ sub }}</div>
    </div>
  </div>
</template>

<style scoped>
/* 复用 DashboardPage.vue 现有样式抽出 */
</style>
```

- [ ] **Step 2: TimeseriesChart.vue**

```vue
<script setup lang="ts">
import { computed } from 'vue';
import VChart from 'vue-echarts';
import '@/components/charts/echarts-setup';
import { defaultLineOption, getMetricColor } from '@/components/charts/chart-theme';
import type { TimeseriesPoint, Metric } from '@/api/stats';

interface Props {
  points: TimeseriesPoint[];
  metric: Metric;
  loading?: boolean;
  height?: number;
}
const props = withDefaults(defineProps<Props>(), { height: 280 });

const option = computed(() => ({
  ...defaultLineOption,
  xAxis: { type: 'time' as const },
  yAxis: { type: 'value' as const, minInterval: 1 },
  series: [{
    name: props.metric,
    type: 'line' as const,
    symbol: 'none' as const,
    smooth: false,
    areaStyle: { opacity: 0.1 },
    data: props.points.map((p) => [p.ts, p.value ?? 0]),
    color: getMetricColor(props.metric),
  }],
}));

const hasData = computed(() => props.points.some((p) => (p.value ?? 0) > 0));
</script>

<template>
  <div class="ts-chart" :style="{ height: height + 'px' }">
    <VChart v-if="!loading && hasData" :option="option" autoresize />
    <div v-else-if="loading" class="ts-chart__state">加载中…</div>
    <div v-else class="ts-chart__state">暂无数据</div>
  </div>
</template>

<style scoped>
.ts-chart { width: 100%; }
.ts-chart__state {
  height: 100%; display: flex; align-items: center; justify-content: center;
  color: var(--color-gray-400); font-size: var(--text-sm);
}
</style>
```

- [ ] **Step 3: BarChart.vue（水平 Top 榜，支持点击）**

```vue
<script setup lang="ts">
import { computed } from 'vue';
import VChart from 'vue-echarts';
import '@/components/charts/echarts-setup';
import { colors } from '@/components/charts/chart-theme';
import type { BreakdownRow } from '@/api/stats';

interface Props {
  rows: BreakdownRow[];
  loading?: boolean;
  height?: number;
}
const props = withDefaults(defineProps<Props>(), { height: 240 });
const emit = defineEmits<{ rowClick: [row: BreakdownRow] }>();

const reversed = computed(() => [...props.rows].reverse());

const option = computed(() => ({
  grid: { left: 120, right: 16, top: 8, bottom: 24 },
  xAxis: { type: 'value' },
  yAxis: {
    type: 'category',
    data: reversed.value.map((r) => r.label ?? '—'),
    axisLabel: { width: 110, overflow: 'truncate' },
  },
  tooltip: { trigger: 'axis' },
  series: [{
    type: 'bar',
    data: reversed.value.map((r) => r.count),
    itemStyle: { borderRadius: [0, 3, 3, 0], color: colors.primary },
  }],
}));

function onChartClick(params: any) {
  const i = reversed.value.length - 1 - params.dataIndex;
  if (i >= 0) emit('rowClick', props.rows[i]);
}
</script>

<template>
  <div class="bar-chart" :style="{ height: height + 'px' }">
    <VChart v-if="!loading && rows.length" :option="option" autoresize @click="onChartClick" />
    <div v-else-if="loading" class="bar-chart__state">加载中…</div>
    <div v-else class="bar-chart__state">暂无数据</div>
  </div>
</template>

<style scoped>
.bar-chart { width: 100%; }
.bar-chart__state {
  height: 100%; display: flex; align-items: center; justify-content: center;
  color: var(--color-gray-400); font-size: var(--text-sm);
}
</style>
```

- [ ] **Step 4: Sparkline.vue**

```vue
<script setup lang="ts">
import { computed } from 'vue';
import VChart from 'vue-echarts';
import '@/components/charts/echarts-setup';
import { colors, getMetricColor } from '@/components/charts/chart-theme';
import type { TimeseriesPoint, Metric } from '@/api/stats';

interface Props {
  points: TimeseriesPoint[];
  metric?: Metric;
  height?: number;
}
const props = withDefaults(defineProps<Props>(), { height: 32 });

const option = computed(() => ({
  grid: { left: 0, right: 0, top: 2, bottom: 2 },
  xAxis: { type: 'time' as const, show: false },
  yAxis: { type: 'value' as const, show: false },
  tooltip: { show: false },
  series: [{
    type: 'line' as const, symbol: 'none' as const, smooth: true,
    areaStyle: { opacity: 0.15 },
    data: props.points.map((p) => [p.ts, p.value ?? 0]),
    color: props.metric ? getMetricColor(props.metric) : colors.primary,
  }],
}));
</script>

<template>
  <div class="sparkline" :style="{ height: height + 'px' }">
    <VChart :option="option" autoresize />
  </div>
</template>

<style scoped>.sparkline { width: 100%; }</style>
```

- [ ] **Step 5: LatencyHistogram.vue**

```vue
<script setup lang="ts">
import { computed } from 'vue';
import VChart from 'vue-echarts';
import '@/components/charts/echarts-setup';
import { colors } from '@/components/charts/chart-theme';
import type { LatencyBucket } from '@/api/stats';

interface Props {
  buckets: LatencyBucket[];
  p95Ms?: number | null;
  p99Ms?: number | null;
  loading?: boolean;
}
const props = defineProps<Props>();

const option = computed(() => ({
  grid: { left: 48, right: 16, top: 24, bottom: 32 },
  xAxis: {
    type: 'category',
    data: props.buckets.map((b) => b.hi == null ? `≥${b.lo}ms` : `${b.lo}-${b.hi}ms`),
  },
  yAxis: { type: 'value' },
  tooltip: { trigger: 'axis' },
  series: [{
    type: 'bar',
    data: props.buckets.map((b) => b.count),
    itemStyle: { color: colors.primary },
    markLine: {
      data: [
        props.p95Ms ? { name: 'P95', xAxis: 'P95', label: { formatter: 'P95' } } : null,
        props.p99Ms ? { name: 'P99', xAxis: 'P99', label: { formatter: 'P99' } } : null,
      ].filter(Boolean),
    },
  }],
}));
</script>

<template>
  <div class="lh" style="height: 240px;">
    <VChart v-if="!loading && buckets.length" :option="option" autoresize />
    <div v-else class="lh__state">{{ loading ? '加载中…' : '暂无数据' }}</div>
  </div>
</template>

<style scoped>
.lh { width: 100%; }
.lh__state {
  height: 100%; display: flex; align-items: center; justify-content: center;
  color: var(--color-gray-400);
}
</style>
```

- [ ] **Step 6: RangePicker.vue**

```vue
<script setup lang="ts">
import type { Range } from '@/api/stats';

const range = defineModel<Range>('range', { required: true });
const options: { label: string; value: Range }[] = [
  { label: '15 分钟', value: '15m' },
  { label: '1 小时',  value: '1h'  },
  { label: '24 小时', value: '24h' },
  { label: '7 天',    value: '7d'  },
];
</script>

<template>
  <el-radio-group v-model="range" size="default">
    <el-radio-button v-for="o in options" :key="o.value" :value="o.value">{{ o.label }}</el-radio-button>
  </el-radio-group>
</template>
```

- [ ] **Step 7: vitest 单测**（小测，验证 prop → DOM 结构 / empty state 文案）

```ts
// services/web/tests/unit/charts.test.ts
import { mount } from '@vue/test-utils';
import { describe, it, expect } from 'vitest';
import KpiCard from '@/components/charts/KpiCard.vue';
import TimeseriesChart from '@/components/charts/TimeseriesChart.vue';

describe('KpiCard', () => {
  it('loading 时 value 显示 —', () => {
    const w = mount(KpiCard, { props: { label: 'calls', value: 0, loading: true } });
    expect(w.text()).toContain('—');
  });
});

describe('TimeseriesChart', () => {
  it('空 points 时显示"暂无数据"', () => {
    const w = mount(TimeseriesChart, { props: { points: [], metric: 'calls' } });
    expect(w.text()).toContain('暂无数据');
  });
});
```

**Verification:**

```bash
cd services/web && pnpm typecheck && pnpm test
```

---

# PR 3 — DashboardPage 原生化 + 移除 Grafana

## Task 11 — DashboardPage.vue 重写

**Files:**
- Edit: `services/web/src/views/dashboard/DashboardPage.vue`（整体重写）

- [ ] **Step 1: 替换整文件**

布局（spec §4.4 已定）：
```
PageHeader + RangePicker（右上）
─ KPI 行（4 卡：calls / error_rate / p95 / throttled）
─ 主时序图（TimeseriesChart，metric 切换 calls/error_rate/p95）
─ 两栏：Top services BarChart / Top callers BarChart
─ 两栏：Top tools BarChart / Status breakdown BarChart
```

关键逻辑：
- `const range = ref<Range>('24h')`
- watch range 变更 → 并行重拉 4 类数据
- `breakdown rowClick` 路由跳转：
  - dim=service → `/services/{slug}`（label 是 slug）
  - dim=application → `/applications/{id}`（key 是 id）
  - dim=tool → `/call-logs?tool=<key>&range=24h`
  - dim=status → `/call-logs?status=<key>&range=24h`

```vue
<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import PageHeader from '@/components/common/PageHeader.vue';
import RangePicker from '@/components/charts/RangePicker.vue';
import KpiCard from '@/components/charts/KpiCard.vue';
import TimeseriesChart from '@/components/charts/TimeseriesChart.vue';
import BarChart from '@/components/charts/BarChart.vue';
import Icon from '@/components/icons/Icon.vue';
import {
  getOverview, getTimeseries, getBreakdown,
  type Range, type Metric, type OverviewResp, type TimeseriesResp,
  type BreakdownResp, type BreakdownRow,
} from '@/api/stats';

const router = useRouter();
const range = ref<Range>('24h');
const tsMetric = ref<Metric>('calls');

const overview = ref<OverviewResp | null>(null);
const ts = ref<TimeseriesResp | null>(null);
const topServices = ref<BreakdownResp | null>(null);
const topApps = ref<BreakdownResp | null>(null);
const topTools = ref<BreakdownResp | null>(null);
const statusBreakdown = ref<BreakdownResp | null>(null);
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    const [o, t, ts1, ta, to, sb] = await Promise.all([
      getOverview({ range: range.value }),
      getTimeseries({ metric: tsMetric.value, range: range.value }),
      getBreakdown({ dim: 'service', range: range.value }),
      getBreakdown({ dim: 'application', range: range.value }),
      getBreakdown({ dim: 'tool', range: range.value }),
      getBreakdown({ dim: 'status', range: range.value }),
    ]);
    overview.value = o;
    ts.value = t;
    topServices.value = ts1;
    topApps.value = ta;
    topTools.value = to;
    statusBreakdown.value = sb;
  } finally { loading.value = false; }
}

watch([range, tsMetric], load);
onMounted(load);

function onServiceClick(row: BreakdownRow) {
  if (row.label) router.push(`/services/${row.label}`);
}
function onAppClick(row: BreakdownRow) {
  if (row.key !== null) router.push(`/applications/${row.key}`);
}
function onToolClick(row: BreakdownRow) {
  router.push({ path: '/call-logs', query: { tool: String(row.key), range: range.value } });
}
function onStatusClick(row: BreakdownRow) {
  router.push({ path: '/call-logs', query: { status: String(row.key), range: range.value } });
}
</script>

<template>
  <PageHeader title="仪表盘" description="MCP 系统调用总览">
    <template #actions>
      <RangePicker v-model:range="range" />
    </template>
  </PageHeader>

  <div class="kpi-grid">
    <KpiCard label="调用次数" :value="overview?.calls?.toLocaleString() ?? 0" :loading="loading" tone="primary">
      <template #icon><Icon name="activity" :size="20" /></template>
    </KpiCard>
    <KpiCard label="错误率" :value="overview ? (overview.error_rate * 100).toFixed(2) + ' %' : '0 %'" :loading="loading" tone="warning">
      <template #icon><Icon name="trending-up" :size="20" /></template>
    </KpiCard>
    <KpiCard label="P95 延迟" :value="overview?.p95_ms ? Math.round(overview.p95_ms) + ' ms' : '—'" :loading="loading" tone="success">
      <template #icon><Icon name="zap" :size="20" /></template>
    </KpiCard>
    <KpiCard label="被限流" :value="overview?.throttled ?? 0" :loading="loading" tone="danger">
      <template #icon><Icon name="alert-circle" :size="20" /></template>
    </KpiCard>
  </div>

  <div class="chart-section">
    <div class="chart-section__header">
      <h3>调用趋势</h3>
      <el-radio-group v-model="tsMetric" size="small">
        <el-radio-button value="calls">次数</el-radio-button>
        <el-radio-button value="error_rate">错误率</el-radio-button>
        <el-radio-button value="p95">P95 延迟</el-radio-button>
      </el-radio-group>
    </div>
    <TimeseriesChart :points="ts?.points ?? []" :metric="tsMetric" :loading="loading" />
  </div>

  <div class="chart-row">
    <div class="chart-section">
      <h3>Top 服务（按调用量）</h3>
      <BarChart :rows="topServices?.rows ?? []" :loading="loading" @row-click="onServiceClick" />
    </div>
    <div class="chart-section">
      <h3>Top 调用方（应用）</h3>
      <BarChart :rows="topApps?.rows ?? []" :loading="loading" @row-click="onAppClick" />
    </div>
  </div>

  <div class="chart-row">
    <div class="chart-section">
      <h3>Top 工具</h3>
      <BarChart :rows="topTools?.rows ?? []" :loading="loading" @row-click="onToolClick" />
    </div>
    <div class="chart-section">
      <h3>状态分布</h3>
      <BarChart :rows="statusBreakdown?.rows ?? []" :loading="loading" @row-click="onStatusClick" />
    </div>
  </div>
</template>

<style scoped>
.kpi-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-4); margin-bottom: var(--space-6);
}
.chart-section {
  background: var(--color-surface); border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-base); padding: var(--space-5); margin-bottom: var(--space-4);
}
.chart-section__header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-3);
}
.chart-section h3 { margin: 0 0 var(--space-3); font-size: var(--text-base); }
.chart-row {
  display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4); margin-bottom: var(--space-4);
}
.chart-row .chart-section { margin-bottom: 0; }
</style>
```

- [ ] **Step 2: 删 iframe 相关样式**

确认 `dashboard-iframe-wrap` / `dashboard-iframe` 样式块已彻底移除。

**Verification:**

```bash
cd services/web && pnpm typecheck && pnpm build
```

浏览器手工：登录 → 仪表盘 → 切 range / 切 metric / 点 BarChart 跳转。

---

## Task 12 — 移除 Grafana 容器、nginx 反代、相关 env

**Files:**
- Edit: `compose.yaml`
- Edit: `nginx/nginx.conf`
- Edit: `.env.example`（若有 `GF_*` 变量）

- [ ] **Step 1: compose.yaml 删除 grafana service 与 volume**

```yaml
# 删除：
  grafana:
    image: grafana/grafana:10.4.5
    ...
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
    ...

# 删除 volume 声明：
  grafana-data:
```

也删 `depends_on: [grafana]` 之类引用。

- [ ] **Step 2: nginx.conf 删除 /grafana/ location**

```
# 删除整个 location /grafana/ { ... } 块（nginx.conf:61-63）
```

- [ ] **Step 3: .env.example 清理 GF_* 变量**

如有 `GF_SECURITY_ADMIN_PASSWORD` / `GF_INSTALL_PLUGINS` 等，全删。

- [ ] **Step 4: README 同步**

`README.md` 端点表删 `| http://localhost:8088/grafana/ | Monitoring dashboard |` 这行。

**Verification:**

```bash
docker compose config 2>&1 | grep -i grafana   # 应无输出
```

部署机操作（用户自己跑）：
```bash
docker compose down
docker volume rm mcpsys_grafana-data   # 可选
docker compose up -d --remove-orphans
```

---

# PR 4 — 三个详情页加概况区块

## Task 13 — ServiceDetailPage 概况区块

**Files:**
- Edit: `services/web/src/views/services/ServiceDetailPage.vue`

- [ ] **Step 1: 在元数据之后、权限/列表之前插入概况区块**

```vue
<div class="overview-section">
  <h3>近 24 小时概况</h3>
  <div class="kpi-grid kpi-grid--3">
    <KpiCard label="24h 调用次数" :value="overview?.calls?.toLocaleString() ?? 0" :loading="loadingOverview" tone="primary" />
    <KpiCard label="24h 错误率"   :value="overview ? (overview.error_rate * 100).toFixed(2) + ' %' : '0 %'" :loading="loadingOverview" tone="warning" />
    <KpiCard label="24h P95 延迟" :value="overview?.p95_ms ? Math.round(overview.p95_ms) + ' ms' : '—'" :loading="loadingOverview" tone="success" />
  </div>
  <div class="chart-row">
    <div class="chart-section">
      <h4>24h 调用趋势</h4>
      <Sparkline :points="ts?.points ?? []" metric="calls" :height="80" />
    </div>
    <div class="chart-section">
      <h4>Top 5 调用方</h4>
      <BarChart :rows="topApps?.rows ?? []" :height="200" @row-click="onAppClick" />
    </div>
  </div>
</div>
```

- [ ] **Step 2: script 拉数据**

```ts
import { getOverview, getTimeseries, getBreakdown, ... } from '@/api/stats';

const overview = ref<OverviewResp | null>(null);
const ts = ref<TimeseriesResp | null>(null);
const topApps = ref<BreakdownResp | null>(null);
const loadingOverview = ref(false);

watch(() => service.value?.id, async (sid) => {
  if (!sid) return;
  loadingOverview.value = true;
  try {
    [overview.value, ts.value, topApps.value] = await Promise.all([
      getOverview({ range: '24h', service_id: sid }),
      getTimeseries({ metric: 'calls', range: '24h', service_id: sid }),
      getBreakdown({ dim: 'application', range: '24h', service_id: sid, limit: 5 }),
    ]);
  } finally { loadingOverview.value = false; }
}, { immediate: true });

function onAppClick(row: BreakdownRow) {
  if (row.key !== null) router.push(`/applications/${row.key}`);
}
```

**Verification:**

`pnpm typecheck`；浏览器手工：进入任一服务详情页 → 顶部能看到 24h 调用次数 KPI 数字 + 趋势 sparkline + Top 5 调用方榜。

---

## Task 14 — ApplicationDetailPage 概况区块

**Files:**
- Edit: `services/web/src/views/applications/ApplicationDetailPage.vue`

- [ ] **Step 1: 同 Task 13 模式**

KPI 行：24h 调用次数 / 24h 错误率 / 24h 被限流次数（`overview.throttled`）

补充图：
- Sparkline：24h calls
- BarChart：Top 5 被调服务（`getBreakdown({ dim: 'service', application_id })`）

`onServiceClick` 跳 `/services/{label}`（label 是 service slug）。

**Verification:** 浏览器手工同 Task 13。

---

## Task 15 — 新建 ApiKeyDetailPage（含概况区块）

**核查结论（2026-05-12）**：
- `services/web/src/views/api-keys/` 下**只有** `ApiKeyListPage.vue`，`router/index.ts` 仅有 `/api-keys`。
- 后端 `routers/api_keys.py` 只有 `GET ""`（列表）+ DELETE/PATCH，**没有 `GET /{key_id}` 单条详情端点**。
- 故本 Task 工作量 ≈ Task 13/14 ×2，但仍留在 PR 4 内（避免 PR 数膨胀）。前后端都要补，顺序：后端端点 → 前端 API → 路由 → 页面 → 列表按钮。

**Files:**
- Edit:   `services/control_plane/src/control_plane/routers/api_keys.py`（加 `GET /{key_id}`）
- Edit:   `services/control_plane/tests/test_api_keys.py`（1-2 例覆盖详情端点）
- Edit:   `services/web/src/api/api-keys.ts`（加 `getApiKey(id)`）
- Edit:   `services/web/src/router/index.ts`（加路由）
- Create: `services/web/src/views/api-keys/ApiKeyDetailPage.vue`
- Edit:   `services/web/src/views/api-keys/ApiKeyListPage.vue`（加"详情"按钮）

- [ ] **Step 1: 后端加 `GET /api/v1/api-keys/{key_id}`**

参考 `routers/services.py:126` 的 `get_service` 模式：

```python
@router.get(
    "/{key_id}",
    response_model=ApiKeyOut,
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)
async def get_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiKeyOut:
    res = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    key = res.scalar_one_or_none()
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "api key not found")
    return ApiKeyOut.model_validate(key)
```

`ApiKeyOut` 已存在（用于 list），不需要新 schema。**响应里绝不**含 plaintext / key_hash（`ApiKeyOut` 默认就没包含，确认一次即可）。

- [ ] **Step 2: 后端测试**

`tests/test_api_keys.py` 加：
```python
async def test_get_api_key_happy(client, admin_token, db, application_a):
    # 先 POST 签发一个 key 拿到 id
    ...
    resp = await client.get(f"/api/v1/api-keys/{key_id}", headers=...)
    assert resp.status_code == 200
    body = resp.json()
    assert "plaintext" not in body
    assert "key_hash" not in body

async def test_get_api_key_not_found(client, admin_token):
    resp = await client.get("/api/v1/api-keys/999999", headers=...)
    assert resp.status_code == 404

async def test_get_api_key_viewer_can_read(client, viewer_token, key_id):
    resp = await client.get(f"/api/v1/api-keys/{key_id}", headers=...)
    assert resp.status_code == 200
```

- [ ] **Step 3: 前端 api/api-keys.ts 加 `getApiKey(id)`**

```ts
export function getApiKey(id: number): Promise<ApiKey> {
  return client.get(`/api/v1/api-keys/${id}`).then((r) => r.data);
}
```

- [ ] **Step 4: 加路由**

`router/index.ts` 在 `/api-keys` 路由之后：
```ts
{
  path: '/api-keys/:id',
  name: 'ApiKeyDetail',
  component: () => import('@/views/api-keys/ApiKeyDetailPage.vue'),
  meta: { requiresAuth: true, roles: ['admin', 'operator', 'viewer'] },
},
```

- [ ] **Step 5: 新建 ApiKeyDetailPage.vue**

参照 `ServiceDetailPage.vue` 骨架：
- `<PageHeader>` 显示 key 名 / 所属 application / 创建时间 / 状态（active/revoked）
- 元数据卡：key prefix（`mks_****` 仅显示前缀，**绝不**回显 plaintext）/ rate_limit_qps / created_by / last_used_at
- 概况区块（本 Task 重点）：
  - KPI 行 ×3：24h 调用次数 / 24h 被限流次数 / 最近调用时间（`formatRelative(overview.last_call_at)`，无调用记录显示"—"）
  - Sparkline ×2 横排：24h calls / 24h throttled
  - 不加 BarChart（API Key 维度下"调用方分布"无意义；若要"被调服务分布"，作为后续小条目）

```ts
import { getOverview, getTimeseries } from '@/api/stats';

const route = useRoute();
const id = Number(route.params.id);
const key = ref<ApiKey | null>(null);
const overview = ref<OverviewResp | null>(null);
const callsTs = ref<TimeseriesResp | null>(null);
const throttledTs = ref<TimeseriesResp | null>(null);
const loading = ref(false);

onMounted(async () => {
  loading.value = true;
  try {
    [key.value, overview.value, callsTs.value, throttledTs.value] = await Promise.all([
      getApiKey(id),
      getOverview({ range: '24h', api_key_id: id }),
      getTimeseries({ metric: 'calls', range: '24h', api_key_id: id }),
      getTimeseries({ metric: 'throttled', range: '24h', api_key_id: id }),
    ]);
  } finally { loading.value = false; }
});
```

- [ ] **Step 6: ApiKeyListPage 加"详情"按钮**

操作列加：
```vue
<el-button link type="primary" @click="router.push(`/api-keys/${row.id}`)">详情</el-button>
```

**Verification:**
- `pnpm typecheck` clean
- 浏览器：API Key 列表 → 点详情 → 进入新页面 → 顶部 24h 调用次数 KPI 数字 + 最近调用时间显示"X 分钟前"或"—" + 两条 sparkline 渲染。
- 直接访问 `/api-keys/999999`（不存在 id）→ 后端 404 → 页面友好态（空数据 placeholder 或 toast）。

---

# PR 5 — 列表页 sparkline + drill-down

## Task 16 — CallLogListPage / AuditEventListPage sparkline

**Files:**
- Edit: `services/web/src/views/call-logs/CallLogListPage.vue`
- Edit: `services/web/src/views/audit/AuditEventListPage.vue`

- [ ] **Step 1: CallLogListPage filter bar 下方加 sparkline**

```vue
<div class="list-sparkline">
  <div class="list-sparkline__title">24h 调用</div>
  <Sparkline :points="callsTs?.points ?? []" metric="calls" :height="64" />
  <div class="list-sparkline__title">24h 错误</div>
  <Sparkline :points="errorsTs?.points ?? []" metric="errors" :height="64" />
</div>
```

```ts
const callsTs = ref<TimeseriesResp | null>(null);
const errorsTs = ref<TimeseriesResp | null>(null);
onMounted(async () => {
  [callsTs.value, errorsTs.value] = await Promise.all([
    getTimeseries({ metric: 'calls', range: '24h' }),
    getTimeseries({ metric: 'errors', range: '24h' }),
  ]);
});
```

- [ ] **Step 2: AuditEventListPage 同款**

只放一个 7d sparkline（events count）：

```ts
const eventsTs = ref<TimeseriesResp | null>(null);
onMounted(async () => {
  eventsTs.value = await getTimeseries({ metric: 'calls', range: '7d' });
});
```

> 注意：audit 走的不是 `call_logs`，spec 没要求 stats 端点支持 audit 时序。**简化处理**：本 Task 用 `calls` 时序作占位——它代表系统活跃度，与 audit 写入频次正相关，作"是否有异常时段"的可视提示够用。后续若需精确的 audit 时序，新增 `audit_events_per_minute` 端点不困难，**列入"未覆盖"，本 Task 不实现**。

**Verification:** 浏览器手工：进 call-logs 页能看到两条 sparkline；进 audit 页能看到一条。

---

## Task 17 — call-logs 列表接受 query filter（drill-down 落地）

**核查结论（2026-05-12）**：`GET /api/v1/call-logs` 已支持 `service_id / application_id / api_key_id / status / from / to`，**缺 `tool` filter**。本 Task 必须先在后端补 `tool` query，前端 drill-down 才能落地。

**Files:**
- Edit: `services/control_plane/src/control_plane/routers/call_logs.py`（加 `tool` filter）
- Edit: `services/control_plane/tests/test_call_logs.py`（1 例覆盖 tool filter）
- Edit: `services/web/src/api/call-logs.ts`（list 参数加 `tool?`）
- Edit: `services/web/src/views/call-logs/CallLogListPage.vue`

- [ ] **Step 1: 后端 list_call_logs 加 tool filter**

`routers/call_logs.py:55-65` 在 `status_filter` 之后插：

```python
tool: str | None = Query(default=None),
```

并在 where 拼接里加：
```python
if tool is not None:
    where.append(CallLog.tool_name == tool)
```

精确匹配（不做 LIKE）——drill-down 场景里 tool 名一定来自 breakdown.rows[i].key，是确定值。

- [ ] **Step 2: 后端测试**

`tests/test_call_logs.py` 加一例：
```python
async def test_list_call_logs_filter_by_tool(client, admin_token, db):
    # 写 2 条 tools/call:get_weather + 1 条 tools/list
    ...
    resp = await client.get(
        "/api/v1/call-logs?tool=tools/call:get_weather",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.json()["total"] == 2
    assert all(it["tool_name"] == "tools/call:get_weather" for it in resp.json()["items"])
```

- [ ] **Step 3: 前端 api/call-logs.ts list 参数加 tool**

```ts
export function listCallLogs(params: {
  service_id?: number;
  application_id?: number;
  api_key_id?: number;
  status?: CallStatus;
  tool?: string;          // 新增
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}): Promise<CallLogList> {
  return client.get('/api/v1/call-logs', { params }).then((r) => r.data);
}
```

- [ ] **Step 4: 读 query 参数初始化 filter**

```ts
import { useRoute } from 'vue-router';
const route = useRoute();

const filterStatus = ref<string>(route.query.status as string ?? '');
const filterTool = ref<string>(route.query.tool as string ?? '');
const filterService = ref<string>(route.query.service as string ?? '');
// range 暂不支持自定义；列表页已有默认窗口
```

> **service query 形态选择**：仪表盘 drill-down 时 `BreakdownRow.label` 是 slug（spec §3.2.3），但 list_call_logs 后端按 `service_id` 过滤。两种处理方式：
> - **A（简单）**：DashboardPage 的 `onServiceClick` 已经跳 `/services/{slug}` 服务详情，不直接跳 call-logs。本 Task 的 `service` query 只服务于"详情页里的'查看本服务所有调用记录'按钮"——传 `service_id` 数值即可。
> - **B**：URL 里用 slug，列表页里再查 `getService(slug)` 拿 id。多一次往返，无收益。
>
> 选 A：filterService 直接是数字字符串，调 list_call_logs 时 `service_id: Number(filterService.value)`。

- [ ] **Step 5: filter 选项变化时同步到 URL（router.replace）**

```ts
watch([filterStatus, filterTool, filterService], () => {
  router.replace({
    path: route.path,
    query: {
      ...(filterStatus.value ? { status: filterStatus.value } : {}),
      ...(filterTool.value   ? { tool:   filterTool.value   } : {}),
      ...(filterService.value? { service:filterService.value}: {}),
    },
  });
});
```

**Verification:**

1. 后端 `pytest services/control_plane/tests/test_call_logs.py -v` → 全绿。
2. 仪表盘 → Status breakdown → 点 `error` 条 → 跳到 `/call-logs?status=error` → URL 保留 query 且列表只显示 error。
3. 仪表盘 → Top tools → 点某 tool → 跳到 `/call-logs?tool=...` → 列表只显示该 tool。
4. 刷新页面 query 仍生效（不是仅靠 ref 内存状态）。

---

# PR 6 — 文档收尾 + cleanup

## Task 18 — README / deployment / spec 注脚 + 删除 grafana/provisioning

**Files:**
- Edit: `README.md`
- Edit: `docs/deployment.md`（若有 Grafana 章节）
- Edit: `docs/specs/2026-04-30-mcp-management-system-design.md`（加注脚）
- Delete: `grafana/provisioning/` 整个目录
- Edit: `docs/changes/2026-05-12-UI半成品修复.md` 或新建 `2026-05-12-V1-D-原生可视化.md`（变更记录）

- [ ] **Step 1: README 端点表删 Grafana 行**

- [ ] **Step 2: 给老 spec 加一条注脚**

在 `2026-04-30-mcp-management-system-design.md` "嵌 Grafana 一张图即可" 那一句后面加：

```
> 注（2026-05-12）：V1-D 已用原生 Vue + ECharts 替换 Grafana，对应 spec 见
> `docs/specs/2026-05-12-v1d-native-visualization-design.md`。
```

不改原文。

- [ ] **Step 3: 删除 grafana 目录**

```bash
git rm -r grafana/
```

确认 compose.yaml 已无引用（Task 12 已完成）。

- [ ] **Step 4: 写变更记录**

新建 `docs/changes/2026-05-12-V1-D-原生可视化.md`，按已有变更记录格式（参考 2026-05-11-V1-B-观测增强.md），记录：
- 入 main 的 PR 列表（PR 1-6 commit SHA）
- 数据库无 migration（强调）
- 部署机操作清单：`docker compose down → docker volume rm mcpsys_grafana-data → docker compose up -d --remove-orphans`
- smoke.sh 已扩展，跑通即可

**Verification:**

```bash
git status   # 期望：grafana 目录已删除（在 staged-for-delete 状态）
find . -name "*.md" | xargs grep -l "grafana" | grep -v changes | grep -v specs
# 期望：仅 specs/changes 残留参考；其它（README/deployment/code 注释）无残留
```

---

# Task 19 — 全套验证 + 自审

- [ ] **Step 1: 后端**

```bash
uv run --package control-plane pytest services/control_plane/tests/ -v
# 期望：全绿；新增 stats 测试 ~22 例
```

- [ ] **Step 2: 前端**

```bash
cd services/web
pnpm typecheck
pnpm lint
pnpm test
pnpm build   # 关注 ECharts 体积；预期主 bundle +200KB gzip 上下
```

- [ ] **Step 3: 部署机 smoke**

```bash
./scripts/smoke.sh
# 期望：包括 stats 4 端点 + audit 全段 + 调用代理段全 OK
```

- [ ] **Step 4: 手工冒烟（浏览器）**

按以下顺序点一遍：
1. admin 登录 → 仪表盘 → KPI 行有数字 → 切 range（15m/1h/24h/7d）观察数字变化 → 切 metric tab → Top services 点条跳服务详情 → Top tools 点条跳 call-logs 带 ?tool=
2. 进任一服务详情 → 顶部 24h 调用次数 KPI 是个真实数字 → Sparkline 显示曲线 → Top 5 调用方榜
3. 进任一应用详情 → 同上验证
4. 进任一 API Key 详情 → 顶部"最近调用时间"显示"X 分钟前"
5. 进 call-logs 列表 → filter bar 下两条 sparkline
6. 进 audit-events 列表 → filter bar 下 7d sparkline
7. 浏览器 hard refresh `localhost:8088/grafana/` → 404（nginx 已删反代）

- [ ] **Step 5: 自审清单（spec § 对照）**

```
[ ] spec §3.2.1 overview filter 三选一优先级在测试中钉死
[ ] spec §3.2.1 last_call_at 在 ApiKeyDetailPage 用 formatRelative 渲染
[ ] spec §3.4 cache 30s TTL（15m range → 10s）
[ ] spec §4.1 ECharts 按需引入而非全量；bundle size 不超 250KB gzip
[ ] spec §4.4 DashboardPage 主时序图 metric 切换器存在
[ ] spec §4.5 三类详情页 KPI 行字段与 spec 表格一致
[ ] spec §5.1 stats 端点 viewer 可访问 + 响应不含 body/ip
[ ] spec §8.1 grafana service / volume / nginx 反代 / README 端点行 / .env GF_* 全清干净
[ ] spec §11 未覆盖项无一被偷偷做了（无自定义日期 picker、无预聚合表、无告警）
```

任何一条不达标 → 回对应 Task 修正后重跑 Step 1-4。

---

# 自审（plan 本身）

- [ ] 已对照 spec §1-11 全部章节，无缺漏 / 无超出（自定义 range / 预聚合 / 多租户 / 告警 / health 曲线 / CSV / Grafana fallback 均未越界）
- [ ] 后端 SQL 全部 UTC-aware：`from_ts` / `to_ts` 用 `timezone.utc`；`date_trunc` 默认 UTC（Postgres session timezone 在 control-plane 容器统一设 UTC）
- [ ] 测试覆盖了 spec §6.1 列出的所有项（happy/empty/filter/priority/bucket/percentile/breakdown other/histogram overflow/viewer/401/422/cache hit&miss&bypass）
- [ ] 性能预算：percentile 兜底（§7.4）若实测慢于 1.5s → 加 cache TTL 提升 或 sampling；**不**预聚合（红线）
- [ ] 数据库无 migration → 部署仅需 `down + volume rm + up`；用户在部署机手动执行（不在开发机跑 docker，见 [[feedback-no-docker-build]]）
- [ ] git commit 用中文（见 [[git-commit-language]]）
- [ ] 拆分为 6 个 PR，PR 1/2 可并行；PR 3 是 Grafana 下线分水岭，必须在 PR 1/2 部署完成后才能合
