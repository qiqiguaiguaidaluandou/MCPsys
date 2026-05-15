<script setup lang="ts">
import { computed } from 'vue';
import VChart from 'vue-echarts';
import dayjs from 'dayjs';
import './echarts-setup';
import { COLORS, metricColor, tooltipBase } from './chart-theme';
import { METRIC_LABELS, type Metric, type Range, type TimeseriesPoint } from '@/api/stats';

const props = withDefaults(
  defineProps<{
    points: TimeseriesPoint[];
    metric: Metric;
    range?: Range;
    loading?: boolean;
    height?: number;
  }>(),
  { loading: false, height: 280 },
);

const isPercentMetric = computed(() => props.metric === 'error_rate');
const isLatencyMetric = computed(
  () => props.metric === 'p50' || props.metric === 'p95' || props.metric === 'p99',
);

const isEmpty = computed(
  () =>
    props.points.length === 0 ||
    props.points.every((p) => p.value == null || p.value === 0),
);

function fmtY(v: number | string): string {
  const n = typeof v === 'number' ? v : Number(v);
  if (isPercentMetric.value) return (n * 100).toFixed(1) + '%';
  if (isLatencyMetric.value) return n.toFixed(0) + ' ms';
  return String(Math.round(n));
}

// X 轴时间格式按 range 粗略选档；ECharts auto 也可以，但中文项目 UX 上手动指定更稳。
function xAxisFormatter(value: number): string {
  const d = dayjs(value);
  if (props.range === '15m' || props.range === '1h') return d.format('HH:mm');
  if (props.range === '7d') return d.format('MM-DD');
  return d.format('MM-DD HH:mm');
}

const option = computed(() => ({
  grid: { left: 56, right: 16, top: 24, bottom: 32 },
  xAxis: {
    type: 'time',
    axisLine: { lineStyle: { color: COLORS.gray200() } },
    axisLabel: {
      color: COLORS.gray500(),
      fontSize: 11,
      formatter: xAxisFormatter,
    },
  },
  yAxis: {
    type: 'value',
    minInterval: isPercentMetric.value ? undefined : 1,
    axisLine: { show: false },
    splitLine: { lineStyle: { color: COLORS.gray100() } },
    axisLabel: { color: COLORS.gray500(), fontSize: 11, formatter: fmtY },
  },
  tooltip: {
    trigger: 'axis',
    ...tooltipBase(),
    formatter: (params: { axisValue: number; data: [string, number] }[]) => {
      if (!params.length) return '';
      const p = params[0];
      const ts = dayjs(p.axisValue).format('YYYY-MM-DD HH:mm');
      return `${ts}<br/>${METRIC_LABELS[props.metric]}: <b>${fmtY(p.data[1])}</b>`;
    },
  },
  series: [
    {
      type: 'line',
      smooth: false,
      symbol: 'none',
      sampling: 'lttb',
      areaStyle: { opacity: 0.1 },
      lineStyle: { width: 2 },
      data: props.points.map((p) => [p.ts, p.value ?? 0]),
      color: metricColor(props.metric),
    },
  ],
}));
</script>

<template>
  <div class="chart-wrap" :style="{ height: height + 'px' }">
    <div v-if="loading" class="chart-status">加载中…</div>
    <div v-else-if="isEmpty" class="chart-status">暂无数据</div>
    <v-chart v-else :option="option" autoresize />
  </div>
</template>

<style scoped>
.chart-wrap {
  width: 100%;
  background: var(--color-surface);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-base);
  padding: var(--space-2);
  position: relative;
}
.chart-status {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--color-gray-400);
  font-size: var(--text-sm);
}
</style>
