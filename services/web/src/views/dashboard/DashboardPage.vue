<script setup lang="ts">
import { ref, reactive, watch, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import {
  getOverview,
  getTimeseries,
  getBreakdown,
  type BreakdownResp,
  type BreakdownRow,
  type Metric,
  type OverviewResp,
  type Range,
  type TimeseriesResp,
} from '@/api/stats';
import PageHeader from '@/components/common/PageHeader.vue';
import RangePicker from '@/components/charts/RangePicker.vue';
import KpiCard from '@/components/charts/KpiCard.vue';
import TimeseriesChart from '@/components/charts/TimeseriesChart.vue';
import BarChart from '@/components/charts/BarChart.vue';

const router = useRouter();

const range = ref<Range>('24h');

type TsMetric = Extract<Metric, 'calls' | 'error_rate' | 'p95'>;
const tsMetric = ref<TsMetric>('calls');
const TS_METRIC_TABS: { value: TsMetric; label: string }[] = [
  { value: 'calls', label: '调用次数' },
  { value: 'error_rate', label: '错误率' },
  { value: 'p95', label: 'P95 延迟' },
];

const overview = ref<OverviewResp | null>(null);
const overviewLoading = ref(false);

const ts = ref<TimeseriesResp | null>(null);
const tsLoading = ref(false);

interface BdState {
  data: BreakdownResp | null;
  loading: boolean;
}
// 5 个 dim 中本页只用 4 个（不含 api_key —— 顶级仪表盘默认看 application 即可）
const bd = reactive<Record<'service' | 'application' | 'tool' | 'status', BdState>>({
  service: { data: null, loading: false },
  application: { data: null, loading: false },
  tool: { data: null, loading: false },
  status: { data: null, loading: false },
});
type BdDim = keyof typeof bd;

async function loadOverview() {
  overviewLoading.value = true;
  try {
    overview.value = await getOverview({ range: range.value });
  } finally {
    overviewLoading.value = false;
  }
}

async function loadTimeseries() {
  tsLoading.value = true;
  try {
    ts.value = await getTimeseries({ metric: tsMetric.value, range: range.value });
  } finally {
    tsLoading.value = false;
  }
}

async function loadBreakdown(dim: BdDim) {
  bd[dim].loading = true;
  try {
    bd[dim].data = await getBreakdown({ dim, range: range.value, limit: 10 });
  } finally {
    bd[dim].loading = false;
  }
}

async function loadAll() {
  // 并发拉所有切片：每张图独立 loading，谁先到谁先渲染
  await Promise.all([
    loadOverview(),
    loadTimeseries(),
    loadBreakdown('service'),
    loadBreakdown('application'),
    loadBreakdown('tool'),
    loadBreakdown('status'),
  ]);
}

watch(range, () => {
  void loadAll();
});
watch(tsMetric, () => {
  void loadTimeseries();
});
onMounted(loadAll);

// ---- 格式化辅助 ----
function pctFormatter(v: string | number | null | undefined): string {
  if (v == null) return '—';
  const n = typeof v === 'number' ? v : Number(v);
  return (n * 100).toFixed(2) + '%';
}
function msFormatter(v: string | number | null | undefined): string {
  if (v == null) return '—';
  const n = typeof v === 'number' ? v : Number(v);
  return Math.round(n).toLocaleString() + ' ms';
}

// ---- Drill-down ----
function onBarClick(dim: BdDim, row: BreakdownRow) {
  if (dim === 'service') {
    // breakdown label 就是 mcp_services.slug —— 直接跳详情
    if (row.label) router.push(`/services/${row.label}`);
  } else if (dim === 'application') {
    if (row.key != null) router.push(`/applications/${row.key}`);
  } else if (dim === 'tool') {
    // spec §4.4：tool / status drill-down 固定带 range=24h，落到 call-logs 列表
    router.push({
      name: 'CallLogList',
      query: { tool: String(row.key ?? ''), range: '24h' },
    });
  } else if (dim === 'status') {
    router.push({
      name: 'CallLogList',
      query: { status: String(row.key ?? ''), range: '24h' },
    });
  }
}
</script>

<template>
  <PageHeader title="仪表盘" description="MCP 系统总体概况">
    <template #actions>
      <RangePicker v-model:range="range" />
    </template>
  </PageHeader>

  <div class="kpi-grid">
    <KpiCard
      label="调用次数"
      icon="activity"
      tone="primary"
      :value="overview?.calls ?? null"
      :loading="overviewLoading"
    />
    <KpiCard
      label="错误率"
      icon="alert-triangle"
      tone="error"
      :value="overview?.error_rate ?? null"
      :loading="overviewLoading"
      :formatter="pctFormatter"
    />
    <KpiCard
      label="P95 延迟"
      icon="trending-up"
      tone="warning"
      :value="overview?.p95_ms ?? null"
      :loading="overviewLoading"
      :formatter="msFormatter"
    />
    <KpiCard
      label="被限流数"
      icon="zap-off"
      tone="info"
      :value="overview?.throttled ?? null"
      :loading="overviewLoading"
    />
  </div>

  <div class="section">
    <div class="section__header">
      <h3 class="section__title">时序趋势</h3>
      <el-radio-group v-model="tsMetric" size="small">
        <el-radio-button
          v-for="t in TS_METRIC_TABS"
          :key="t.value"
          :value="t.value"
        >{{ t.label }}</el-radio-button>
      </el-radio-group>
    </div>
    <TimeseriesChart
      :points="ts?.points ?? []"
      :metric="tsMetric"
      :range="range"
      :loading="tsLoading"
      :height="320"
    />
  </div>

  <div class="grid-2">
    <div class="section">
      <h3 class="section__title">Top 服务（按调用）</h3>
      <BarChart
        :rows="bd.service.data?.rows ?? []"
        :loading="bd.service.loading"
        @row-click="onBarClick('service', $event)"
      />
    </div>
    <div class="section">
      <h3 class="section__title">Top 调用方（按应用）</h3>
      <BarChart
        :rows="bd.application.data?.rows ?? []"
        :loading="bd.application.loading"
        @row-click="onBarClick('application', $event)"
      />
    </div>
  </div>

  <div class="grid-2">
    <div class="section">
      <h3 class="section__title">Top 工具</h3>
      <BarChart
        :rows="bd.tool.data?.rows ?? []"
        :loading="bd.tool.loading"
        @row-click="onBarClick('tool', $event)"
      />
    </div>
    <div class="section">
      <h3 class="section__title">状态分布</h3>
      <BarChart
        :rows="bd.status.data?.rows ?? []"
        :loading="bd.status.loading"
        @row-click="onBarClick('status', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}
.section {
  margin-bottom: var(--space-6);
}
.section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}
.section__title {
  margin: 0;
  font-size: var(--text-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-gray-800);
}
.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
}
@media (max-width: 960px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .grid-2 { grid-template-columns: 1fr; }
}
</style>
