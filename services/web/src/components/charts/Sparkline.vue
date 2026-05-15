<script setup lang="ts">
import { computed } from 'vue';
import VChart from 'vue-echarts';
import './echarts-setup';
import { COLORS } from './chart-theme';
import type { TimeseriesPoint } from '@/api/stats';

const props = withDefaults(
  defineProps<{
    points: TimeseriesPoint[];
    height?: number;
    color?: string;
  }>(),
  { height: 32 },
);

const isEmpty = computed(
  () =>
    props.points.length === 0 ||
    props.points.every((p) => p.value == null || p.value === 0),
);

const option = computed(() => ({
  grid: { left: 0, right: 0, top: 2, bottom: 2, containLabel: false },
  xAxis: { type: 'time', show: false },
  yAxis: { type: 'value', show: false },
  tooltip: { show: false },
  series: [
    {
      type: 'line',
      symbol: 'none',
      smooth: true,
      sampling: 'lttb',
      areaStyle: { opacity: 0.15 },
      lineStyle: { width: 1.5 },
      data: props.points.map((p) => [p.ts, p.value ?? 0]),
      color: props.color ?? COLORS.primary(),
    },
  ],
}));
</script>

<template>
  <div class="sparkline" :style="{ height: height + 'px' }">
    <span v-if="isEmpty" class="sparkline__empty">—</span>
    <v-chart v-else :option="option" autoresize />
  </div>
</template>

<style scoped>
.sparkline {
  width: 100%;
  position: relative;
}
.sparkline__empty {
  display: block;
  text-align: center;
  color: var(--color-gray-300);
  font-size: var(--text-xs);
  line-height: inherit;
}
</style>
