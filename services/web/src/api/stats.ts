/**
 * /api/v1/stats/* 客户端 —— 与后端 schemas/stats.py 对齐。
 *
 * 4 个端点：overview / timeseries / breakdown / latency-histogram。
 * 鉴权 admin/operator/viewer；只读，不动数据库。响应头里有 x-cache: hit|miss|bypass
 * 供调试观察（这里不抓取，浏览器开发者工具看）。
 */
import { client } from './client';

export type Range = '15m' | '1h' | '24h' | '7d' | '30d' | 'all';
export type Metric = 'calls' | 'errors' | 'error_rate' | 'p50' | 'p95' | 'p99' | 'throttled';
export type Bucket = '1m' | '5m' | '1h' | '1d';
export type Dim = 'service' | 'application' | 'api_key' | 'tool' | 'status';

/** 互斥过滤；与后端 pick_filter 优先级一致：service_id > application_id > api_key_id。 */
export interface StatsFilter {
  service_id: number | null;
  application_id: number | null;
  api_key_id: number | null;
}

export interface BaseFilterParams {
  service_id?: number;
  application_id?: number;
  api_key_id?: number;
}

// ---------- /overview ----------

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

export function getOverview(
  params: { range: Range } & BaseFilterParams,
): Promise<OverviewResp> {
  return client.get('/api/v1/stats/overview', { params }).then((r) => r.data);
}

// ---------- /timeseries ----------

export interface TimeseriesPoint {
  ts: string;
  value: number | null;
}

export interface TimeseriesResp {
  metric: Metric;
  range: Range;
  bucket: Bucket;
  filter: StatsFilter | null;
  points: TimeseriesPoint[];
}

export function getTimeseries(
  params: { metric: Metric; range: Range; bucket?: Bucket } & BaseFilterParams,
): Promise<TimeseriesResp> {
  return client.get('/api/v1/stats/timeseries', { params }).then((r) => r.data);
}

// ---------- /breakdown ----------

export interface BreakdownRow {
  key: number | string | null;
  label: string | null;
  count: number;
  error_count: number;
  error_rate: number;
}

export interface BreakdownOther {
  count: number;
  error_count: number;
}

export interface BreakdownResp {
  dim: Dim;
  range: Range;
  metric: 'calls' | 'errors';
  filter: StatsFilter | null;
  rows: BreakdownRow[];
  other: BreakdownOther | null;
}

export function getBreakdown(
  params: {
    dim: Dim;
    range: Range;
    metric?: 'calls' | 'errors';
    limit?: number;
  } & BaseFilterParams,
): Promise<BreakdownResp> {
  return client.get('/api/v1/stats/breakdown', { params }).then((r) => r.data);
}

// ---------- /latency-histogram ----------

export interface LatencyBucket {
  lo: number;
  hi: number | null;
  count: number;
}

export interface LatencyHistogramResp {
  range: Range;
  filter: StatsFilter | null;
  buckets: LatencyBucket[];
}

export function getLatencyHistogram(
  params: { range: Range } & BaseFilterParams,
): Promise<LatencyHistogramResp> {
  return client
    .get('/api/v1/stats/latency-histogram', { params })
    .then((r) => r.data);
}

// ---------- 共用展示常量 ----------

export const RANGE_OPTIONS: { value: Range; label: string }[] = [
  { value: '15m', label: '15 分钟' },
  { value: '1h', label: '1 小时' },
  { value: '24h', label: '24 小时' },
  { value: '7d', label: '7 天' },
  { value: '30d', label: '30 天' },
  { value: 'all', label: '全部' },
];

export const METRIC_LABELS: Record<Metric, string> = {
  calls: '调用次数',
  errors: '错误数',
  error_rate: '错误率',
  p50: 'P50 延迟',
  p95: 'P95 延迟',
  p99: 'P99 延迟',
  throttled: '被限流数',
};
