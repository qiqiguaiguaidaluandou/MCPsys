<script setup lang="ts">
import { computed } from 'vue';
import VChart from 'vue-echarts';
import './echarts-setup';
import { COLORS, tooltipBase } from './chart-theme';
import type { BreakdownRow } from '@/api/stats';

const props = withDefaults(
  defineProps<{
    rows: BreakdownRow[];
    /** 用哪个字段画条；'count' 适合 metric=calls，'error_count' 适合 metric=errors。 */
    valueField?: 'count' | 'error_count';
    loading?: boolean;
    height?: number;
    /** 横向 Top 榜（默认）或纵向柱。 */
    orientation?: 'horizontal' | 'vertical';
  }>(),
  {
    valueField: 'count',
    loading: false,
    height: 280,
    orientation: 'horizontal',
  },
);

const emit = defineEmits<{
  /** 点击某条 → 父组件 drill-down 路由。 */
  rowClick: [row: BreakdownRow];
}>();

const isEmpty = computed(() => props.rows.length === 0);

const sortedRows = computed(() => {
  // 横向 Top：ECharts category 轴默认是从下到上，需 reverse 让最大值在顶部
  return props.orientation === 'horizontal' ? [...props.rows].reverse() : props.rows;
});

const labels = computed(() => sortedRows.value.map((r) => r.label ?? '(unknown)'));
const values = computed(() => sortedRows.value.map((r) => r[props.valueField]));

const option = computed(() => {
  const horizontal = props.orientation === 'horizontal';
  return {
    grid: horizontal
      ? { left: 130, right: 24, top: 8, bottom: 24 }
      : { left: 40, right: 16, top: 16, bottom: 32 },
    xAxis: horizontal
      ? {
          type: 'value',
          axisLine: { show: false },
          splitLine: { lineStyle: { color: COLORS.gray100() } },
          axisLabel: { color: COLORS.gray500(), fontSize: 11 },
        }
      : {
          type: 'category',
          data: labels.value,
          axisLine: { lineStyle: { color: COLORS.gray200() } },
          axisLabel: { color: COLORS.gray500(), fontSize: 11, interval: 0 },
        },
    yAxis: horizontal
      ? {
          type: 'category',
          data: labels.value,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: {
            color: COLORS.gray700(),
            fontSize: 12,
            width: 120,
            overflow: 'truncate',
          },
        }
      : {
          type: 'value',
          axisLine: { show: false },
          splitLine: { lineStyle: { color: COLORS.gray100() } },
          axisLabel: { color: COLORS.gray500(), fontSize: 11 },
        },
    tooltip: {
      trigger: 'item',
      ...tooltipBase(),
      formatter: (p: { name: string; value: number; dataIndex: number }) => {
        const row = sortedRows.value[p.dataIndex];
        const lines = [`<b>${row.label ?? '(unknown)'}</b>`];
        lines.push(`调用：${row.count.toLocaleString()}`);
        lines.push(`错误：${row.error_count.toLocaleString()}`);
        lines.push(`错误率：${(row.error_rate * 100).toFixed(2)}%`);
        return lines.join('<br/>');
      },
    },
    series: [
      {
        type: 'bar',
        data: values.value,
        itemStyle: {
          color: COLORS.primary(),
          borderRadius: horizontal ? [0, 3, 3, 0] : [3, 3, 0, 0],
        },
        barMaxWidth: 28,
      },
    ],
  };
});

function onChartClick(params: { dataIndex: number }) {
  const row = sortedRows.value[params.dataIndex];
  if (row) emit('rowClick', row);
}
</script>

<template>
  <div class="chart-wrap" :style="{ height: height + 'px' }">
    <div v-if="loading" class="chart-status">加载中…</div>
    <div v-else-if="isEmpty" class="chart-status">暂无数据</div>
    <v-chart v-else :option="option" autoresize @click="onChartClick" />
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
