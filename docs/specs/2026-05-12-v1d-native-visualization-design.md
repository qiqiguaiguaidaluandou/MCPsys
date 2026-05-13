# V1-D 原生可视化设计（移除 Grafana → Vue + ECharts）

时间窗：2026-05-12 起，V1-B（审计 + 观测增强）入 main 之后。

## 1. 背景与目标

### 1.1 现状

- 当前数据可视化唯一入口是 `DashboardPage.vue:94-100` 嵌入的 Grafana iframe (`/grafana/d/mcpsys-overview/...`)。
- Grafana provisioning 维护 7 个面板，**全部** `datasource.type = postgres`、SQL 查 `call_logs`——没有任何面板用到 Grafana 真正擅长的 Prometheus 时序。换言之：Grafana 在本项目里只是一个"SQL 渲染器"。
- 其它落点完全缺图：服务详情 / 应用详情 / API Key 详情 / call-logs 列表 / audit-events 列表，都只有元数据和表格，回答不了"这个实体最近表现如何"、"异常时段在哪"。
- 用户痛点（2026-05-12）：Grafana 不好用——iframe 鉴权别扭、主题不一致、无法 drill-down 跳回 admin 内的 call-logs / 详情、改 SQL 要进 Grafana UI、多一份运维表面。

### 1.2 目标

1. **完全移除 Grafana 容器**：compose / nginx / web 三处全部清掉相关挂载与反代；不保留 profile fallback。
2. **数据可视化全部走 Vue + ECharts**：control-plane 出聚合端点，前端用 `vue-echarts` 渲染。
3. **图表与列表/详情形成 drill-down 闭环**：点击图表元素 → `router.push` 到对应 call-logs / audit 列表并带 filter。
4. **四个时间窗口固定**：`15m / 1h / 24h / 7d`，不支持自定义日期范围（YAGNI；要 ad-hoc 探查走 psql）。
5. **不预留预聚合表**：100 QPS 量级 + `call_logs` 月度分区 + 现有索引下，`date_trunc` 即时聚合 + Redis 30s 短缓存够用。未来真到瓶颈再单独立项。
6. **Prometheus `/metrics` 端点保留不动**（gateway + control-plane），便于将来对接公司级 Grafana/告警。

### 1.3 非目标（V1-D 显式不做）

- 自定义日期范围 picker
- 预聚合表 `call_metrics_1m` / 物化视图（YAGNI）
- 告警规则（V2 韧性增强主题）
- 调用日志按 application 全局可见性下沉（仍维持 admin/operator 限制；viewer 看聚合数据 OK，看 body 不行——见 §5.2）
- Grafana profile fallback：完全清掉，不保留"开关"
- 服务健康检查曲线（health_status 历史尚未持久化采样，超出 V1-D 范围）

## 2. 数据模型

**不**新增表。所有聚合直接查 `call_logs`，利用现有索引：

```
call_logs(ts), (service_id, ts), (api_key_id, ts), (status, ts)
```

以及 `mcp_services.slug` / `applications.name` / `api_keys.name` 用于在响应里把 id 翻成可读 label（join 单表 PK 索引命中）。

预算见 §7。

## 3. 后端：聚合 API

### 3.1 新模块 `services/control_plane/src/control_plane/routers/stats.py`

挂在 `/api/v1/stats` 前缀下，4 个端点。所有端点：
- 鉴权：`require_role("admin", "operator", "viewer")`——viewer 可看聚合数据（不含 body）。
- 不写审计（只读）。
- 不在 admin handler 里 import gateway，gateway 不依赖 stats。

### 3.2 端点详表

#### 3.2.1 `GET /api/v1/stats/overview`

顶部 KPI；既可全局，也可单实体（服务/应用/API Key 详情页复用同端点）。

**Query**:
- `range`: `15m | 1h | 24h | 7d`（默认 `24h`）
- 可选过滤（互斥优先级 `service_id > application_id > api_key_id`；同时给按此优先级取一个）：
  - `service_id` (int)
  - `application_id` (int)
  - `api_key_id` (int)

**Response**:
```json
{
  "range": "24h",
  "from": "2026-05-11T03:00:00Z",
  "to":   "2026-05-12T03:00:00Z",
  "filter": { "service_id": 12 },
  "calls": 14823,
  "errors": 412,
  "error_rate": 0.0278,
  "p50_ms": 23,
  "p95_ms": 187,
  "p99_ms": 622,
  "throttled": 38,
  "denied": 5,
  "last_call_at": "2026-05-12T02:58:41Z"
}
```

无 filter 时 `filter` 字段为 `null`。`last_call_at` 是 `MAX(ts)`，方便 API Key 详情页直接显示"最近调用时间"（无调用记录则为 `null`）。

**SQL**（一条复合查询，避免 N 次往返）:
```sql
SELECT
  count(*)                                         AS calls,
  count(*) FILTER (WHERE status != 'success')      AS errors,
  count(*) FILTER (WHERE status = 'throttled')     AS throttled,
  count(*) FILTER (WHERE status = 'denied')        AS denied,
  percentile_cont(0.50) WITHIN GROUP (ORDER BY duration_ms) AS p50,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95,
  percentile_cont(0.99) WITHIN GROUP (ORDER BY duration_ms) AS p99,
  max(ts)                                          AS last_call_at
FROM call_logs
WHERE ts >= :from AND ts < :to
  AND (:service_id::int     IS NULL OR service_id     = :service_id)
  AND (:application_id::int IS NULL OR application_id = :application_id)
  AND (:api_key_id::int     IS NULL OR api_key_id     = :api_key_id);
```

Python 层按 §3.2.2 同款优先级把多个 filter 互斥成一个（其余传 NULL 占位），避免 SQL 里跨 filter 组合。`error_rate = errors / calls`（calls=0 时返回 0.0）。

Cache key 形态：`stats:overview:{range}:filter={svc=12|app=3|key=5|none}`，TTL 同 §3.4。

#### 3.2.2 `GET /api/v1/stats/timeseries`

时序图（主仪表盘曲线 / 详情页迷你图 / 列表 sparkline 共用）。

**Query**:
- `metric`: `calls | errors | error_rate | p50 | p95 | p99 | throttled`（必填，单值）
- `range`: 同上
- `bucket`: `1m | 5m | 1h`（可选；服务端按 range 选默认：15m→`30s`?不，下沉到 1m；1h→`1m`；24h→`5m`；7d→`1h`）
- 可选过滤（互斥优先级 service_id > application_id > api_key_id；同时给则按这个优先级取一个）：
  - `service_id` (int)
  - `application_id` (int)
  - `api_key_id` (int)

**Response**:
```json
{
  "metric": "calls",
  "range": "24h",
  "bucket": "5m",
  "filter": { "service_id": 12 },
  "points": [
    { "ts": "2026-05-11T03:00:00Z", "value": 38 },
    { "ts": "2026-05-11T03:05:00Z", "value": 41 },
    ...
  ]
}
```

**SQL 骨架**（以 calls + bucket=5m 为例）:
```sql
WITH series AS (
  SELECT generate_series(:from, :to - interval '5 min', interval '5 min') AS bucket_ts
),
agg AS (
  SELECT date_trunc('minute', ts) - (extract(minute FROM ts)::int % 5) * interval '1 min' AS bucket_ts,
         count(*) AS value
  FROM call_logs
  WHERE ts >= :from AND ts < :to
    AND (:service_id::int IS NULL OR service_id = :service_id)
  GROUP BY bucket_ts
)
SELECT s.bucket_ts AS ts, COALESCE(a.value, 0) AS value
FROM series s LEFT JOIN agg a USING (bucket_ts)
ORDER BY ts;
```

p50/p95/p99：`GROUP BY bucket_ts` + `percentile_cont`。error_rate：用 `nullif(calls,0)` 防除零。

**实现要点**:
- bucket truncation 用 `date_trunc('minute' | 'hour', ts)` + 算术取整（1m / 5m / 1h 三档），不引入 `time_bucket` 之类扩展。
- 用 `generate_series` 补零 → 前端拿到等距点数组，画图无需 padding。
- `(metric, range, bucket, filter)` 组合是 cache key 的一部分。

#### 3.2.3 `GET /api/v1/stats/breakdown`

Top 榜 / 分组聚合（仪表盘下方 + 详情页"调用方"分布）。

**Query**:
- `dim`: `service | application | api_key | tool | status`（必填）
- `range`: 同上
- `metric`: `calls | errors`（默认 `calls`）
- `limit`: 默认 10，max 50
- 可选过滤（同 timeseries）：`service_id` / `application_id` / `api_key_id`

**Response**:
```json
{
  "dim": "service",
  "range": "24h",
  "metric": "calls",
  "rows": [
    { "key": 12, "label": "weather-mcp", "count": 4821, "error_count": 17, "error_rate": 0.0035 },
    { "key": 7,  "label": "crm-mcp",     "count": 3299, "error_count": 102, "error_rate": 0.0309 },
    ...
  ],
  "other": { "count": 142, "error_count": 8 }
}
```

**SQL 骨架**（dim=service）:
```sql
SELECT cl.service_id AS key,
       s.slug        AS label,
       count(*)                                       AS count,
       count(*) FILTER (WHERE status != 'success')    AS error_count
FROM call_logs cl
LEFT JOIN mcp_services s ON s.id = cl.service_id
WHERE ts >= :from AND ts < :to
GROUP BY cl.service_id, s.slug
ORDER BY count DESC
LIMIT :limit;
```

`other` bucket：再单独查 `count(*) - sum(top.count)`，避免前端拼接。

`dim=tool` → `GROUP BY tool_name`，label 直接是 tool_name；`dim=status` → label 是 status 枚举值。

#### 3.2.4 `GET /api/v1/stats/latency-histogram`

延迟分布（服务详情页可选；仪表盘不放主图，避免过密）。

**Query**:
- `range`: 同上
- 可选过滤：`service_id` / `application_id` / `api_key_id`

**Response**:
```json
{
  "range": "24h",
  "bucket_ms": 50,
  "buckets": [
    { "lo": 0,    "hi": 50,   "count": 8421 },
    { "lo": 50,   "hi": 100,  "count": 3120 },
    ...
    { "lo": 2000, "hi": null, "count": 41 }  // overflow
  ]
}
```

固定 bucket 边界：`[0, 50, 100, 200, 500, 1000, 2000, +∞]`，前端不传 bucket 边界（YAGNI）。

**SQL**：`CASE width_bucket` 或一组 `count(*) FILTER (WHERE duration_ms < N)`。

### 3.3 Schema 与依赖

`schemas/stats.py` 集中放 `OverviewOut / TimeseriesOut / TimeseriesPoint / BreakdownOut / BreakdownRow / LatencyHistogramOut / LatencyBucket`。

Range / bucket / dim / metric 用 `Literal` + Pydantic 校验。非法值 → 422 走全局 interceptor 通道。

### 3.4 缓存

新模块 `control_plane/cache_stats.py`：
- key 格式：`stats:{endpoint}:{range}:{...args}`，例 `stats:overview:24h`、`stats:ts:calls:24h:5m:svc=12`。
- 序列化：`orjson.dumps` 进 Redis；TTL 30s。
- 命中 → `Response(... headers={"x-cache": "hit"})`；未命中 → 算 + 写 + 返回 `x-cache: miss`。
- range=`15m` 时 TTL 缩短为 10s（窗口本来就小，30s 失效会比窗口长 2 倍，体验差）。
- Redis 不可用 → 跳过缓存直接打库（与 service resolver 同款 graceful degrade）。
- 失效策略：**不**主动失效。call_logs 是追加流，缓存 TTL 到即可。

### 3.5 不在范围

- 不引入 TimescaleDB / pg_partman 之外的扩展。
- 不写 stats SQL 到 audit_events（聚合是读操作）。
- 不暴露原始 `request_body / response_body`（已有 call-logs 详情端点覆盖，权限 admin/operator）。

## 4. 前端

### 4.1 依赖

`pnpm add echarts vue-echarts` —— **按需引入**：

```ts
// services/web/src/components/charts/echarts-setup.ts
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { LineChart, BarChart } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, LegendComponent,
  DataZoomComponent, MarkLineComponent,
} from 'echarts/components';

use([CanvasRenderer, LineChart, BarChart,
     GridComponent, TooltipComponent, LegendComponent,
     DataZoomComponent, MarkLineComponent]);
```

bundle 预估：+ ~220 KB gzip，可接受。**不**全量引入 `echarts`。

### 4.2 API 层

`services/web/src/api/stats.ts`：
```ts
export type Range = '15m' | '1h' | '24h' | '7d';
export type Metric = 'calls' | 'errors' | 'error_rate' | 'p50' | 'p95' | 'p99' | 'throttled';
export type Dim = 'service' | 'application' | 'api_key' | 'tool' | 'status';

export interface OverviewResp { ... }
export interface TimeseriesResp { points: { ts: string; value: number }[]; ... }
export interface BreakdownResp { rows: ...; other?: ... }
export interface LatencyHistogramResp { ... }

export function getOverview(params: {
  range: Range;
  service_id?: number;
  application_id?: number;
  api_key_id?: number;
}): Promise<OverviewResp>;
export function getTimeseries(params: {
  metric: Metric;
  range: Range;
  bucket?: '1m' | '5m' | '1h';
  service_id?: number;
  application_id?: number;
  api_key_id?: number;
}): Promise<TimeseriesResp>;
export function getBreakdown(params: ...): Promise<BreakdownResp>;
export function getLatencyHistogram(params: ...): Promise<LatencyHistogramResp>;
```

### 4.3 公共图表组件

目录 `services/web/src/components/charts/`：

| 组件 | Props | 说明 |
|---|---|---|
| `KpiCard.vue` | `label`, `value`, `sub?`, `tone?`, `loading?` | 已有内联代码抽出 |
| `TimeseriesChart.vue` | `points`, `metric`, `range`, `loading?`, `height?` | ECharts line；x 轴时间，y 轴自动；hover 显示精确值 + 时间；`@brush-select` 抛出 `[from, to]` 用于 drill-down |
| `BarChart.vue` | `rows`, `metric`, `orientation?` (默认 horizontal), `loading?`, `onClick?` (`(row) => void`) | Top 榜；点击条 → onClick(row) |
| `Sparkline.vue` | `points`, `height?` (默认 32), `tone?` | 极简，无坐标轴 / 无 tooltip / 无 legend；列表 filter 上方用 |
| `LatencyHistogram.vue` | `buckets`, `loading?` | 直方图 + 标 P95 / P99 mark line |
| `RangePicker.vue` | `v-model:range` | 四按钮分段（15m / 1h / 24h / 7d）；不是日期 picker |

**共享样式**：图表配色取项目 CSS variable（`--color-primary-500` / `--color-success` / `--color-warning` / `--color-danger`），ECharts theme 配置文件 `chart-theme.ts` 统一定义。

**Loading 态**：组件内部不发请求；父组件传 `loading` props。空数据 / 全零 → 显示"暂无数据"占位（与 DataTable 风格一致）。

### 4.4 DashboardPage 改造

完全重写 `services/web/src/views/dashboard/DashboardPage.vue`：

```
+ RangePicker（15m / 1h / 24h / 7d）右上角
│
├─ KPI 行（4 卡）：calls / error_rate / p95 / throttled
│
├─ 主时序图（TimeseriesChart, metric=calls，全屏宽）
│    切换器：[calls | error_rate | p95]（三个 tab）
│
├─ 两栏
│   ├─ Top services by calls (BarChart)
│   └─ Top callers (BarChart)        ← 按 application 维度
│
├─ 两栏
│   ├─ Top tools (BarChart)
│   └─ Status breakdown (BarChart, dim=status, 横向)
```

**Drill-down**：
- `BarChart` onClick(row) → 路由：
  - `dim=service` → `/services/{slug}`（先去服务详情页，里面有图表 + 调用记录入口；不直接跳到 call-logs，避免越级）
  - `dim=application` → `/applications/{id}`
  - `dim=tool` → `/call-logs?tool=<name>&range=24h`
  - `dim=status` → `/call-logs?status=<status>&range=24h`
- `TimeseriesChart` 暂不做 brush-select drill-down（V1-D 范围保守；标好 onClick(ts) 钩子留给后续即可）。

iframe 区域整段删掉。

### 4.5 详情页改造

三类详情页统一加"概况"区块（在元数据下、列表上方），固定 24h 窗口。每页结构：**顶部 KPI 卡行 → 下方 Sparkline / BarChart 补充时序与构成视角**。KPI 调 `GET /api/v1/stats/overview?<entity_id>=...&range=24h`，单次请求拿齐。

| 详情页 | KPI 行（3 个标量） | 下方补充图 |
|---|---|---|
| `ServiceDetailPage.vue` | 24h 调用次数 / 24h 错误率 / 24h p95 延迟 | 24h calls Sparkline / Top 5 调用方应用 BarChart |
| `ApplicationDetailPage.vue` | 24h 调用次数 / 24h 错误率 / 24h 被限流次数（throttled） | 24h calls Sparkline / Top 5 被调服务 BarChart |
| `ApiKeyDetailPage.vue` | 24h 调用次数 / 24h 被限流次数 / 最近调用时间（last_call_at） | 24h calls Sparkline / 24h throttled Sparkline |

KPI 卡复用 §4.3 的 `KpiCard.vue` 组件，与 DashboardPage 顶部 KPI 行视觉一致。Sparkline 用 timeseries API + 实体 filter（如 `?service_id=12`），Top BarChart 用 breakdown API + 同样 filter。

`last_call_at` 在 API Key 详情页用 `formatRelative()` 渲染（如"3 分钟前"），与 DashboardPage "上次登录" 文案一致；无调用记录显示"—"。

### 4.6 列表页 sparkline

`CallLogListPage.vue` 和 `AuditEventListPage.vue` 在 filter bar 下方加一条 64px 高的 sparkline：
- call-logs：24h calls + 红线叠加 errors（双系列）
- audit-events：7d events count（窗口长一些，因为审计稀疏）

点击 sparkline 不做 brush（同上保守理由）。

### 4.7 删除 Grafana 相关前端代码

- `DashboardPage.vue` 删除 iframe / `.dashboard-iframe-wrap` / `.dashboard-iframe` 样式。
- `SideBar.vue` 若有 Grafana 链接 → 删。
- `nginx.conf` 反代条目 → 删。

### 4.8 i18n

新增文案集中放 `i18n/locales/zh-CN.ts` 的 `stats.*` 命名空间。本次不上 en；与项目现状一致。

## 5. 权限与隐私

### 5.1 角色

- `admin / operator / viewer`：所有 stats 端点皆可访问。
- 聚合不带 PII：`call_logs.request_body / response_body` 不出现在 stats 响应里。
- `client_ip` 不出现在聚合里（避免 viewer 看到 IP 分布）。

### 5.2 跨租户

V1-D 仍**不**做 per-application scoping（viewer 看的是全局聚合）。这与 V1-B 决策一致（`docs/specs/2026-05-11-v1b-audit-events-design.md` §5）。未来真要做按 tenant 隔离，stats 接口里加 `application_id` 强制 filter 即可。

## 6. 测试策略

### 6.1 后端（`services/control_plane/tests/test_stats.py`）

每个端点 4-6 例：
- `test_overview_24h_happy`：写入若干 call_logs（混 success/error/throttled）+ 调端点 → KPI 数值匹配；`last_call_at` 等于最后一条样本的 `ts`。
- `test_overview_empty`：空表 → calls=0 / error_rate=0.0 / 分位为 null / `last_call_at`=null。
- `test_overview_with_service_filter`：service_id=A 写 100 条 / service_id=B 写 50 条 → `?service_id=A` 返回 calls=100，其余字段只反映 A。
- `test_overview_filter_priority`：同时传 `service_id` + `application_id` → 按 §3.2.1 优先级只应用 `service_id`，`filter` 字段在响应里只回显被采用的那个。
- `test_timeseries_calls_bucket_5m`：写入跨 5 个 bucket 的样本 → 返回 12 个 5m 点（1h）且零桶补 0。
- `test_timeseries_p95_with_service_filter`：service_id=A 100 条 / service_id=B 100 条 → filter=A 时 p95 只反映 A 的样本。
- `test_breakdown_top_services_with_other`：写入 12 个服务 → limit=10 时返回 10 行 + `other` 含剩 2 个的累计。
- `test_latency_histogram_overflow_bucket`：写入 duration_ms=5000 的样本 → 落入 `hi=null` overflow bucket。
- `test_stats_viewer_can_read`：viewer 调 overview → 200。
- `test_stats_unauthenticated_rejected`：无 token → 401。
- `test_stats_invalid_range_422`：range=`foo` → 422。

### 6.2 缓存（`tests/test_stats_cache.py`）

- `test_overview_caches_30s`：第一次 miss，第二次 hit（x-cache 头）。
- `test_overview_cache_bypass_when_redis_down`：mock redis raise → 端点仍返回 200。

### 6.3 前端

- `services/web/tests/unit/charts.test.ts`：组件 prop → 渲染 mock canvas（jsdom 下 ECharts 用 SVGRenderer fallback 验证 DOM 结构）。
- 单测覆盖目标：drill-down router.push 参数正确性；空数据 placeholder 渲染。

### 6.4 冒烟

`scripts/smoke.sh` 末尾追加：
```bash
curl -fsS "$BASE/api/v1/stats/overview?range=24h" -H "Authorization: Bearer $TOKEN" >/dev/null
curl -fsS "$BASE/api/v1/stats/timeseries?metric=calls&range=1h" -H "Authorization: Bearer $TOKEN" | jq '.points | length' | grep -q '^[0-9]\+$'
```

## 7. 性能预算

### 7.1 数据量假设

- 100 QPS 峰值 → 24h 上限 ~864 万行 call_logs；7d 上限 ~6000 万行。
- 实际内部系统大概率远低于此（个位数 QPS）。

### 7.2 查询成本

- `WHERE ts >= :from AND ts < :to` 命中 `(ts)` btree；扫描范围 100 万行级 → Postgres 单条聚合 < 200 ms。
- `GROUP BY service_id` + `JOIN mcp_services` → 服务数预估 < 100，hash agg 单次 < 50 ms。
- `percentile_cont` 在 100 万行上 ~500 ms（无 TDigest），24h 全表场景较重——**靠 Redis 30s TTL 抹平**：第一次慢，后续 30s 内零成本。
- 7d range 直接走 1h bucket → 168 点，aggregation 命中较窄子集时间不长；不走 percentile（前端 metric 切到分位时强制 1h bucket，原始数据规模可控）。

### 7.3 阈值

- 命中 cache：< 10 ms（Redis round-trip）。
- 未命中、range=24h、metric=calls：< 300 ms。
- 未命中、range=7d、metric=p95：< 1500 ms（前端可显 loading）。
- 这些是预算，不写硬断言。

### 7.4 兜底

如果 24h percentile 实测慢于 1.5s（监控自身 control_plane `/metrics` 的 endpoint duration），按以下顺序处理：
1. 把 percentile 查询拆出独立 cache key 单独 TTL=60s（数值变化慢，分位上拉 TTL OK）。
2. 仍慢则降级：percentile 改 sampling（`TABLESAMPLE BERNOULLI(10)`），数值误差可接受。
3. 仍慢才考虑预聚合表——但**不在 V1-D 范围**。

## 8. 部署 / 迁移

### 8.1 移除 Grafana

- `compose.yaml`：删除 `grafana` service、`grafana-data` volume、`grafana` 依赖。
- `nginx/nginx.conf`：删除 `location /grafana/` 块（`nginx.conf:61-63`）。
- `grafana/provisioning/` 目录：保留在 git 仓库**作为参考**（V1-D plan 阶段写 SQL 时可直接抄过来），但不再被任何服务挂载。后续单独一次 cleanup PR 删除整个目录。
- `.env.example`：删除 `GF_*` 相关变量（如有）。

### 8.2 升级路径

无 DB 迁移。只需：
1. 拉新代码
2. `docker compose build control-plane web`
3. `docker compose up -d --remove-orphans`（`--remove-orphans` 清掉 grafana 容器）
4. `docker volume rm mcpsys_grafana-data`（可选，释放空间）

### 8.3 文档同步

- `README.md` 删除 `/grafana/` 端点行。
- `docs/deployment.md`（若有 Grafana 章节）删除。
- `docs/specs/2026-04-30-mcp-management-system-design.md` 的"嵌 Grafana 一张图"一句，标记为 V1-D 之后已替换（不改原文，加一行注脚即可）。

## 9. 拆分与 PR 节奏

| PR | 内容 | 估时 |
|---|---|---|
| 1 | 后端 stats 端点（4 个）+ cache + 单测 + smoke 扩展 | 3-4 天 |
| 2 | 前端图表基础组件（charts/*）+ stats.ts API 层 + ECharts 按需引入 | 2 天 |
| 3 | DashboardPage 原生化 + RangePicker；compose / nginx 移除 Grafana | 2-3 天 |
| 4 | 三个详情页加概况区块 | 2 天 |
| 5 | call-logs + audit-events 列表 sparkline；call-logs 接受 query filter | 1-2 天 |
| 6 | 文档同步 + cleanup（删除 grafana/provisioning 目录） | 0.5 天 |

PR 1-2 可并行（后端/前端独立）。PR 3 是分水岭——合入后 Grafana 完全下线；前后顺序：PR 1 / 2 入 main → PR 3 入 → PR 4 / 5 / 6 并行。

合计 1.5-2 周。

## 10. 风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| ECharts bundle 体积 +220KB 影响首屏 | 中 | 低 | 按需引入，路由级 `defineAsyncComponent` 懒加载 chart 组件 |
| Postgres percentile 在 7d 数据下慢 | 中 | 中 | §7.4 缓存 + 采样兜底；监控 control_plane endpoint duration |
| 删除 grafana 后被发现还有人在用 | 低 | 中 | 项目是内部 MVP，单人架构；删前在 docs/changes 写一条 heads-up |
| Redis 不可用时聚合直接打库变慢 | 低 | 低 | resolver 已有 graceful degrade 模式可复用；stats 端点同 pattern |
| date_trunc 时区问题 | 中 | 中 | 全部 SQL 显式 `at time zone 'UTC'`；前端按浏览器时区显示 |

## 11. 未覆盖（明确不做，避免日后被开 ticket）

- **自定义时间窗口**：四档够用；要 ad-hoc 走 psql 或将来对接公司 Grafana（保留 /metrics 端点）。
- **预聚合表 / 物化视图**：YAGNI；§7.4 描述了真到瓶颈时的升级路径。
- **告警/通知**：超出可视化范畴；V2 韧性主题处理。
- **多租户 scope**：viewer 仍看全局；按 tenant 隔离留到 v2 SSO/RBAC 主题。
- **服务健康检查曲线**：依赖 health_status 历史采样表，目前不存在；超出 V1-D 范围。
- **导出 / 下载 CSV**：界面操作中没人需要；要数据走 psql。
- **保留 Grafana 作为 profile fallback**：用户拍板完全移除；不做 fallback。

## 附录 A · ECharts option 模板（实现期参照）

### A.1 TimeseriesChart

```ts
{
  grid: { left: 48, right: 16, top: 24, bottom: 32 },
  xAxis: { type: 'time' },
  yAxis: { type: 'value', minInterval: 1 },
  tooltip: { trigger: 'axis', formatter: ... },
  series: [{
    type: 'line', smooth: false, symbol: 'none',
    areaStyle: { opacity: 0.1 },
    data: points.map(p => [p.ts, p.value]),
    color: getMetricColor(metric),
  }],
}
```

### A.2 Sparkline（极简）

```ts
{
  grid: { left: 0, right: 0, top: 2, bottom: 2 },
  xAxis: { type: 'time', show: false },
  yAxis: { type: 'value', show: false },
  tooltip: { show: false },
  series: [{
    type: 'line', symbol: 'none', smooth: true,
    areaStyle: { opacity: 0.15 },
    data: points.map(p => [p.ts, p.value]),
  }],
}
```

### A.3 BarChart (horizontal Top)

```ts
{
  grid: { left: 120, right: 16, top: 8, bottom: 24 },
  xAxis: { type: 'value' },
  yAxis: { type: 'category', data: rows.map(r => r.label).reverse(),
           axisLabel: { width: 110, overflow: 'truncate' } },
  series: [{
    type: 'bar',
    data: rows.map(r => r.count).reverse(),
    itemStyle: { borderRadius: [0, 3, 3, 0] },
  }],
}
```

## 附录 B · 端点 → 页面映射速查

| 页面 | 调用端点 | 频率 |
|---|---|---|
| DashboardPage | overview（全局）/ timeseries / breakdown ×4 | 每次切 range / 进页 |
| ServiceDetailPage | overview（filter=service）+ timeseries ×1 + breakdown ×1（filter=service） | 进页一次 |
| ApplicationDetailPage | overview（filter=app）+ timeseries ×1 + breakdown ×1（filter=app） | 进页一次 |
| ApiKeyDetailPage | overview（filter=key）+ timeseries ×2（filter=key） | 进页一次 |
| CallLogListPage | timeseries ×1（24h, calls + errors 双系列） | 进页一次 |
| AuditEventListPage | timeseries ×1（7d count） | 进页一次 |
