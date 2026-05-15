import { describe, expect, it } from 'vitest';
import { mount, shallowMount } from '@vue/test-utils';

import KpiCard from '@/components/charts/KpiCard.vue';
import RangePicker from '@/components/charts/RangePicker.vue';
import TimeseriesChart from '@/components/charts/TimeseriesChart.vue';
import Sparkline from '@/components/charts/Sparkline.vue';
import BarChartComp from '@/components/charts/BarChart.vue';
import LatencyHistogram from '@/components/charts/LatencyHistogram.vue';
import type { BreakdownRow, LatencyBucket, TimeseriesPoint } from '@/api/stats';

// chart 组件用 shallowMount —— 自动 stub 子组件（包括 vue-echarts 的 <v-chart>），
// 避免 jsdom 下 ECharts 触发 canvas API 报错。我们只测「该不该出图」这层逻辑，
// 不测 ECharts 内部渲染。

describe('KpiCard', () => {
  it('renders label & value', () => {
    const w = mount(KpiCard, { props: { label: '调用次数', value: 1234 } });
    expect(w.text()).toContain('调用次数');
    expect(w.text()).toContain('1,234');  // toLocaleString
  });

  it('shows em-dash when loading', () => {
    const w = mount(KpiCard, { props: { label: 'x', value: 99, loading: true } });
    expect(w.find('.kpi-card__value').text()).toBe('—');
  });

  it('shows em-dash for null/undefined value', () => {
    const w = mount(KpiCard, { props: { label: 'x', value: null } });
    expect(w.find('.kpi-card__value').text()).toBe('—');
  });

  it('applies custom formatter', () => {
    const w = mount(KpiCard, {
      props: {
        label: 'rate',
        value: 0.0327,
        formatter: (v) => ((v as number) * 100).toFixed(2) + '%',
      },
    });
    expect(w.find('.kpi-card__value').text()).toBe('3.27%');
  });

  it('renders sub text when given', () => {
    const w = mount(KpiCard, {
      props: { label: 'x', value: 1, sub: '上次登录 3 分钟前' },
    });
    expect(w.text()).toContain('上次登录 3 分钟前');
  });
});

describe('RangePicker', () => {
  it('renders 4 options', () => {
    const w = mount(RangePicker, { props: { range: '24h' } });
    // 4 个 el-radio-button 渲染为 label/span
    const text = w.text();
    expect(text).toContain('15 分钟');
    expect(text).toContain('1 小时');
    expect(text).toContain('24 小时');
    expect(text).toContain('7 天');
  });
});

describe('TimeseriesChart', () => {
  it('shows placeholder when points are empty', () => {
    const w = shallowMount(TimeseriesChart, {
      props: { points: [], metric: 'calls' },
    });
    expect(w.text()).toContain('暂无数据');
  });

  it('shows placeholder when all values are zero', () => {
    const points: TimeseriesPoint[] = [
      { ts: '2026-05-15T00:00:00Z', value: 0 },
      { ts: '2026-05-15T00:01:00Z', value: 0 },
    ];
    const w = shallowMount(TimeseriesChart, { props: { points, metric: 'calls' } });
    expect(w.text()).toContain('暂无数据');
  });

  it('shows chart when points have non-zero values', () => {
    const points: TimeseriesPoint[] = [
      { ts: '2026-05-15T00:00:00Z', value: 42 },
      { ts: '2026-05-15T00:01:00Z', value: 17 },
    ];
    const w = shallowMount(TimeseriesChart, { props: { points, metric: 'calls' } });
    expect(w.text()).not.toContain('暂无数据');
    // shallowMount 把 <v-chart> 渲染为 stub 元素（类似 <v-chart-stub />），
    // 出现即说明不在 empty 分支
    // shallowMount 把 vue-echarts 渲染为 <echarts-stub>（vue-echarts 组件 name=echarts）
    expect(w.find('echarts-stub').exists()).toBe(true);
  });

  it('shows loading state', () => {
    const w = shallowMount(TimeseriesChart, {
      props: { points: [], metric: 'calls', loading: true },
    });
    expect(w.text()).toContain('加载中');
  });
});

describe('Sparkline', () => {
  it('shows em-dash placeholder when empty', () => {
    const w = shallowMount(Sparkline, { props: { points: [] } });
    expect(w.find('.sparkline__empty').text()).toBe('—');
  });

  it('renders chart with non-zero points', () => {
    const points: TimeseriesPoint[] = [{ ts: '2026-05-15T00:00:00Z', value: 5 }];
    const w = shallowMount(Sparkline, { props: { points } });
    // shallowMount 把 vue-echarts 渲染为 <echarts-stub>（vue-echarts 组件 name=echarts）
    expect(w.find('echarts-stub').exists()).toBe(true);
  });
});

describe('BarChart', () => {
  function row(label: string, count: number, error_count = 0): BreakdownRow {
    return { key: label, label, count, error_count, error_rate: count ? error_count / count : 0 };
  }

  it('placeholder when no rows', () => {
    const w = shallowMount(BarChartComp, { props: { rows: [] } });
    expect(w.text()).toContain('暂无数据');
  });

  it('renders chart when rows present', () => {
    const rows = [row('a', 10), row('b', 5)];
    const w = shallowMount(BarChartComp, { props: { rows } });
    // shallowMount 把 vue-echarts 渲染为 <echarts-stub>（vue-echarts 组件 name=echarts）
    expect(w.find('echarts-stub').exists()).toBe(true);
  });
});

describe('LatencyHistogram', () => {
  it('placeholder when all buckets are zero', () => {
    const buckets: LatencyBucket[] = [
      { lo: 0, hi: 50, count: 0 },
      { lo: 50, hi: 100, count: 0 },
    ];
    const w = shallowMount(LatencyHistogram, { props: { buckets } });
    expect(w.text()).toContain('暂无数据');
  });

  it('renders chart when at least one bucket has data', () => {
    const buckets: LatencyBucket[] = [
      { lo: 0, hi: 50, count: 100 },
      { lo: 50, hi: 100, count: 50 },
      { lo: 100, hi: 200, count: 25 },
      { lo: 200, hi: 500, count: 10 },
      { lo: 500, hi: 1000, count: 5 },
      { lo: 1000, hi: 2000, count: 2 },
      { lo: 2000, hi: null, count: 1 },
    ];
    const w = shallowMount(LatencyHistogram, { props: { buckets } });
    // shallowMount 把 vue-echarts 渲染为 <echarts-stub>（vue-echarts 组件 name=echarts）
    expect(w.find('echarts-stub').exists()).toBe(true);
    expect(w.text()).not.toContain('暂无数据');
  });
});
