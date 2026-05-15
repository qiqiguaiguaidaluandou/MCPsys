<script setup lang="ts">
import { computed } from 'vue';
import VChart from 'vue-echarts';
import './echarts-setup';
import { COLORS, tooltipBase } from './chart-theme';
import type { LatencyBucket } from '@/api/stats';

const props = withDefaults(
  defineProps<{
    buckets: LatencyBucket[];
    loading?: boolean;
    height?: number;
  }>(),
  { loading: false, height: 240 },
);

const isEmpty = computed(
  () => props.buckets.length === 0 || props.buckets.every((b) => b.count === 0),
);

const labels = computed(() =>
  props.buckets.map((b) => (b.hi === null ? `≥${b.lo}` : `${b.lo}–${b.hi}`)),
);

const counts = computed(() => props.buckets.map((b) => b.count));

/**
 * 后端返回的桶很粗（7 档非均匀宽度）。P95 / P99 用累积线性插值估算：
 * 找到累积 >= target 的桶，按桶内比例落在 lo + (hi-lo) * within。
 * 末桶 hi=null 时按 lo*1.5 兜底（视觉提示，精度让 spec 接受的 trade-off）。
 */
function approxPercentile(p: number): number | null {
  const total = counts.value.reduce((s, c) => s + c, 0);
  if (total === 0) return null;
  const target = total * p;
  let cumul = 0;
  for (const b of props.buckets) {
    if (cumul + b.count >= target) {
      const within = b.count === 0 ? 0 : (target - cumul) / b.count;
      const hi = b.hi ?? Math.round(b.lo * 1.5);
      return Math.round(b.lo + (hi - b.lo) * within);
    }
    cumul += b.count;
  }
  return props.buckets[props.buckets.length - 1].lo;
}

const p95 = computed(() => approxPercentile(0.95));
const p99 = computed(() => approxPercentile(0.99));

/** 把估算的 ms 值翻译成对应桶的 axis 索引（用于 markLine xAxis 位置）。 */
function bucketIndexForMs(ms: number): number {
  for (let i = 0; i < props.buckets.length; i++) {
    const b = props.buckets[i];
    if (b.hi === null) return i;
    if (ms < b.hi) return i;
  }
  return props.buckets.length - 1;
}

const option = computed(() => ({
  grid: { left: 48, right: 16, top: 32, bottom: 36 },
  xAxis: {
    type: 'category',
    data: labels.value,
    name: 'ms',
    nameGap: 24,
    nameTextStyle: { color: COLORS.gray500(), fontSize: 11 },
    axisLine: { lineStyle: { color: COLORS.gray200() } },
    axisLabel: { color: COLORS.gray500(), fontSize: 11 },
  },
  yAxis: {
    type: 'value',
    minInterval: 1,
    axisLine: { show: false },
    splitLine: { lineStyle: { color: COLORS.gray100() } },
    axisLabel: { color: COLORS.gray500(), fontSize: 11 },
  },
  tooltip: {
    trigger: 'item',
    ...tooltipBase(),
    formatter: (p: { name: string; value: number }) =>
      `${p.name} ms<br/>样本数：<b>${p.value.toLocaleString()}</b>`,
  },
  series: [
    {
      type: 'bar',
      data: counts.value,
      itemStyle: { color: COLORS.primary(), borderRadius: [3, 3, 0, 0] },
      barMaxWidth: 32,
      markLine:
        p95.value != null || p99.value != null
          ? {
              silent: true,
              symbol: ['none', 'none'],
              label: { color: COLORS.gray700(), fontSize: 11 },
              lineStyle: { type: 'dashed', width: 1 },
              data: [
                ...(p95.value != null
                  ? [
                      {
                        xAxis: bucketIndexForMs(p95.value),
                        label: { formatter: `P95 ≈ ${p95.value} ms` },
                        lineStyle: { color: COLORS.warning() },
                      },
                    ]
                  : []),
                ...(p99.value != null
                  ? [
                      {
                        xAxis: bucketIndexForMs(p99.value),
                        label: { formatter: `P99 ≈ ${p99.value} ms` },
                        lineStyle: { color: COLORS.error() },
                      },
                    ]
                  : []),
              ],
            }
          : undefined,
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
