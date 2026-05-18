<script setup lang="ts">
import { ref, onMounted, reactive, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { queryCallLogs, type CallLog, type CallLogQuery, type CallStatus } from '@/api/call-logs';
import { listServices, type McpService } from '@/api/services';
import { listApplications, type Application } from '@/api/applications';
import { getTimeseries, type Range, type TimeseriesPoint } from '@/api/stats';
import PageHeader from '@/components/common/PageHeader.vue';
import DataTable from '@/components/common/DataTable.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import Sparkline from '@/components/charts/Sparkline.vue';
import Icon from '@/components/icons/Icon.vue';
import { formatDateTime, formatDuration } from '@/utils/format';
import dayjs from 'dayjs';

type RangeOpt = '1h' | '24h' | '7d' | 'all';
const VALID_RANGES: RangeOpt[] = ['1h', '24h', '7d', 'all'];
const VALID_STATUS: CallStatus[] = ['success', 'error', 'timeout', 'denied', 'throttled'];

const router = useRouter();
const route = useRoute();
const items = ref<CallLog[]>([]);
const total = ref(0);
const loading = ref(false);
const services = ref<McpService[]>([]);
const apps = ref<Application[]>([]);

const filters = reactive<{
  range: RangeOpt;
  status: CallStatus | '';
  service_id: number | '';
  application_id: number | '';
  tool: string;
  page: number;
  pageSize: number;
}>({
  range: '24h',
  status: '',
  service_id: '',
  application_id: '',
  tool: '',
  page: 1,
  pageSize: 50,
});

function seedFromQuery() {
  const q = route.query;
  const range = typeof q.range === 'string' ? q.range : '';
  if ((VALID_RANGES as string[]).includes(range)) filters.range = range as RangeOpt;
  const stat = typeof q.status === 'string' ? q.status : '';
  if ((VALID_STATUS as string[]).includes(stat)) filters.status = stat as CallStatus;
  if (typeof q.tool === 'string' && q.tool) filters.tool = q.tool;
  const sid = Number(q.service_id);
  if (Number.isFinite(sid) && sid > 0) filters.service_id = sid;
  const aid = Number(q.application_id);
  if (Number.isFinite(aid) && aid > 0) filters.application_id = aid;
}

async function load() {
  loading.value = true;
  try {
    const params: CallLogQuery = {
      limit: filters.pageSize,
      offset: (filters.page - 1) * filters.pageSize,
    };
    if (filters.status) params.status = filters.status;
    if (filters.service_id) params.service_id = filters.service_id;
    if (filters.application_id) params.application_id = filters.application_id;
    if (filters.tool) params.tool = filters.tool;
    if (filters.range !== 'all') {
      const map = { '1h': 1, '24h': 24, '7d': 24 * 7 };
      params.from = dayjs().subtract(map[filters.range], 'hour').toISOString();
    }
    const resp = await queryCallLogs(params);
    items.value = resp.items;
    total.value = resp.total;
  } finally {
    loading.value = false;
  }
}

async function loadServices() {
  services.value = (await listServices()).items;
}

async function loadApps() {
  apps.value = (await listApplications()).items;
}

// ---- Sparkline（calls + errors） ----
// stats/timeseries 只支持 entity 三选一过滤，不接 tool / status，所以 sparkline 视角永远是
// 「当前选中实体的 24h 整体调用 / 错误曲线」，与表格 tool / status 过滤可能不一致——这是 spec
// §4.6 接受的折衷（点击 sparkline 不做 brush，sparkline 只用作 shape）。
const callsPoints = ref<TimeseriesPoint[]>([]);
const errorsPoints = ref<TimeseriesPoint[]>([]);
const sparkLoading = ref(false);

function sparkRange(): Range {
  // range=all 时退回 24h，避免空白
  if (filters.range === 'all' || filters.range === '1h') return '24h';
  return filters.range;
}

async function loadSparkline() {
  sparkLoading.value = true;
  try {
    const baseParams: Parameters<typeof getTimeseries>[0] = {
      metric: 'calls',
      range: sparkRange(),
      bucket: '1h',
    };
    // entity 优先级：service > application（同后端 pick_filter）
    if (filters.service_id) baseParams.service_id = filters.service_id;
    else if (filters.application_id) baseParams.application_id = filters.application_id;
    const errParams = { ...baseParams, metric: 'errors' as const };
    const [calls, errors] = await Promise.all([
      getTimeseries(baseParams),
      getTimeseries(errParams),
    ]);
    callsPoints.value = calls.points;
    errorsPoints.value = errors.points;
  } finally {
    sparkLoading.value = false;
  }
}

watch(
  () => [filters.range, filters.service_id, filters.application_id] as const,
  () => void loadSparkline(),
);

onMounted(async () => {
  seedFromQuery();
  await Promise.all([loadServices(), loadApps()]);
  await Promise.all([load(), loadSparkline()]);
});

function isSlowCall(ms: number) {
  return ms > 1000;
}

function getServiceSlug(id: number): string {
  return services.value.find((s) => s.id === id)?.slug ?? `#${id}`;
}

function resetFilters() {
  filters.status = '';
  filters.service_id = '';
  filters.application_id = '';
  filters.tool = '';
  filters.page = 1;
  load();
}
</script>

<template>
  <PageHeader title="调用日志" description="所有 MCP 调用的明细记录" />

  <div class="filter-bar">
    <el-select v-model="filters.range" style="width: 140px;" @change="load">
      <el-option label="最近 1 小时" value="1h" />
      <el-option label="最近 24 小时" value="24h" />
      <el-option label="最近 7 天" value="7d" />
      <el-option label="全部" value="all" />
    </el-select>
    <el-select v-model="filters.service_id" placeholder="服务" clearable style="width: 180px;" @change="load">
      <el-option v-for="s in services" :key="s.id" :value="s.id" :label="s.slug" />
    </el-select>
    <el-select
      v-model="filters.application_id"
      placeholder="应用"
      clearable
      style="width: 180px;"
      @change="load"
    >
      <el-option v-for="a in apps" :key="a.id" :value="a.id" :label="a.name" />
    </el-select>
    <el-select v-model="filters.status" placeholder="状态" clearable style="width: 120px;" @change="load">
      <el-option label="成功" value="success" />
      <el-option label="错误" value="error" />
      <el-option label="超时" value="timeout" />
      <el-option label="拒绝" value="denied" />
      <el-option label="限流" value="throttled" />
    </el-select>
    <el-input
      v-model="filters.tool"
      placeholder="工具名"
      clearable
      style="width: 160px;"
      @change="load"
    />
    <div style="flex: 1" />
    <el-button @click="resetFilters">重置</el-button>
    <el-button @click="load"><Icon name="refresh-cw" :size="14" /> 刷新</el-button>
  </div>

  <div v-loading="sparkLoading" class="spark-card">
    <div class="spark-card__legend">
      <span class="spark-card__title">调用趋势（{{ sparkRange() }}）</span>
      <span class="legend"><span class="dot dot--primary" />调用</span>
      <span class="legend"><span class="dot dot--error" />错误</span>
    </div>
    <Sparkline
      :points="callsPoints"
      :error-points="errorsPoints"
      :height="64"
    />
  </div>

  <DataTable
    :data="items"
    :loading="loading"
    :total="total"
    :page="filters.page"
    :page-size="filters.pageSize"
    @update:page="(p: number) => { filters.page = p; load(); }"
    @update:page-size="(s: number) => { filters.pageSize = s; load(); }"
  >
    <el-table-column label="时间" width="180">
      <template #default="{ row }: { row: CallLog }">
        <span class="mono" style="font-size: 12px;">{{ formatDateTime(row.ts) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="服务" width="200">
      <template #default="{ row }: { row: CallLog }">
        <span class="mono">{{ getServiceSlug(row.service_id) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="API Key" width="140">
      <template #default="{ row }: { row: CallLog }">
        <span class="mono text-secondary">#{{ row.api_key_id ?? '—' }}</span>
      </template>
    </el-table-column>
    <el-table-column label="状态" width="100">
      <template #default="{ row }: { row: CallLog }"><StatusTag :status="row.status" /></template>
    </el-table-column>
    <el-table-column label="HTTP" width="80">
      <template #default="{ row }: { row: CallLog }">
        <span class="mono">{{ row.http_status ?? '—' }}</span>
      </template>
    </el-table-column>
    <el-table-column label="耗时" width="100">
      <template #default="{ row }: { row: CallLog }">
        <span :style="{ color: isSlowCall(row.duration_ms) ? 'var(--color-error)' : 'var(--color-gray-700)' }">
          {{ formatDuration(row.duration_ms) }}
        </span>
      </template>
    </el-table-column>
    <el-table-column label="工具" width="160">
      <template #default="{ row }: { row: CallLog }">{{ row.tool_name ?? '—' }}</template>
    </el-table-column>
    <el-table-column label="错误" min-width="200" show-overflow-tooltip>
      <template #default="{ row }: { row: CallLog }">
        <span v-if="row.error_message" class="text-secondary">{{ row.error_message }}</span>
        <span v-else>—</span>
      </template>
    </el-table-column>
    <el-table-column label="操作" width="80" fixed="right">
      <template #default="{ row }: { row: CallLog }">
        <el-button link type="primary" @click="router.push(`/call-logs/${row.id}`)">详情</el-button>
      </template>
    </el-table-column>
  </DataTable>
</template>

<style scoped>
.filter-bar {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: var(--space-3);
}
.spark-card {
  background: var(--color-surface);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-base);
  padding: var(--space-3);
  margin-bottom: var(--space-4);
}
.spark-card__legend {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--text-xs);
  color: var(--color-gray-500);
  margin-bottom: var(--space-1);
}
.spark-card__title {
  color: var(--color-gray-700);
  font-weight: var(--font-weight-semibold);
}
.legend {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 999px;
}
.dot--primary { background: var(--color-primary-500); }
.dot--error { background: var(--color-error); }
</style>
