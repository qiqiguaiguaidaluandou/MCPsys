<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import {
  getService,
  getServiceHealthHistory,
  updateService,
  type HealthHistoryItem,
  type HealthStatus,
  type McpService,
} from '@/api/services';
import { listApplications, type Application } from '@/api/applications';
import { listServicePermissions, type Permission } from '@/api/permissions';
import {
  getOverview,
  getTimeseries,
  getBreakdown,
  type BreakdownRow,
  type OverviewResp,
  type Range,
  type TimeseriesResp,
} from '@/api/stats';
import { useAuthStore } from '@/stores/auth';
import PageHeader from '@/components/common/PageHeader.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import HealthDot from '@/components/feature/HealthDot.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import CopyButton from '@/components/common/CopyButton.vue';
import Icon from '@/components/icons/Icon.vue';
import KpiCard from '@/components/charts/KpiCard.vue';
import TimeseriesChart from '@/components/charts/TimeseriesChart.vue';
import BarChart from '@/components/charts/BarChart.vue';
import RangePicker from '@/components/charts/RangePicker.vue';
import { formatDateTime, gatewayUrl } from '@/utils/format';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const service = ref<McpService | null>(null);
const loading = ref(false);
const tab = ref('overview');

const permissions = ref<Permission[]>([]);
const permLoading = ref(false);
const apps = ref<Application[]>([]);

const qpsDraft = ref<number | null>(null);
const qpsSaving = ref(false);

const canEdit = computed(() => auth.hasRole('admin', 'operator'));

function formatQps(qps: number | null | undefined): string {
  if (qps === null || qps === undefined) return '不限';
  if (qps === 0) return '停用 (0)';
  return `${qps} QPS`;
}

async function onSaveQps() {
  if (!service.value) return;
  qpsSaving.value = true;
  try {
    await updateService(service.value.slug, { rate_limit_qps: qpsDraft.value });
    ElMessage.success('已保存');
    await load();
  } finally {
    qpsSaving.value = false;
  }
}

function clearQpsDraft() {
  qpsDraft.value = null;
}

function appNameById(id: number): string {
  return apps.value.find((a) => a.id === id)?.name ?? '(unknown)';
}

async function reloadPermissions() {
  if (!service.value) return;
  permLoading.value = true;
  try {
    const list = await listServicePermissions(service.value.slug);
    permissions.value = list.items;
  } finally {
    permLoading.value = false;
  }
}

async function reloadApps() {
  const list = await listApplications();
  apps.value = list.items;
}

async function load() {
  loading.value = true;
  try {
    service.value = await getService(String(route.params.slug));
    qpsDraft.value = service.value.rate_limit_qps;
    await Promise.all([reloadPermissions(), reloadApps()]);
  } finally {
    loading.value = false;
  }
}

// ---- 调用统计 tab（默认 24h，支持切 7d/30d/all） ----
const statsRange = ref<Range>('24h');
const overview = ref<OverviewResp | null>(null);
const overviewLoading = ref(false);
const sparkline = ref<TimeseriesResp | null>(null);
const sparkLoading = ref(false);
const topApps = ref<BreakdownRow[]>([]);
const topAppsLoading = ref(false);
// 记录最近一次加载使用的 range；切换 tab / range 与之不同才重新拉，避免抖动。
const loadedRange = ref<Range | null>(null);

async function loadStats() {
  if (!service.value) return;
  const sid = service.value.id;
  const r = statsRange.value;
  loadedRange.value = r;
  const filter = { service_id: sid };
  overviewLoading.value = true;
  sparkLoading.value = true;
  topAppsLoading.value = true;
  await Promise.all([
    getOverview({ range: r, ...filter })
      .then((res) => (overview.value = res))
      .finally(() => (overviewLoading.value = false)),
    getTimeseries({ metric: 'calls', range: r, ...filter })
      .then((res) => (sparkline.value = res))
      .finally(() => (sparkLoading.value = false)),
    getBreakdown({ dim: 'application', range: r, limit: 5, ...filter })
      .then((res) => (topApps.value = res.rows))
      .finally(() => (topAppsLoading.value = false)),
  ]);
}

watch([tab, service, statsRange], ([t, s, r]) => {
  if (t === 'stats' && s && loadedRange.value !== r) void loadStats();
});

// ---- 健康历史 tab（懒加载，与 stats 同款哨兵模式） ----
const healthEvents = ref<HealthHistoryItem[]>([]);
const healthLoading = ref(false);
let healthLoadedFor: string | null = null;

const HEALTH_LABEL: Record<HealthStatus, string> = {
  healthy: '健康',
  unhealthy: '异常',
  unknown: '未知',
};

function healthLabel(s: HealthStatus | null | undefined): string {
  if (!s) return '未知';
  return HEALTH_LABEL[s] ?? s;
}

async function loadHealthHistory() {
  if (!service.value) return;
  const slug = service.value.slug;
  healthLoadedFor = slug;
  healthLoading.value = true;
  try {
    const resp = await getServiceHealthHistory(slug);
    healthEvents.value = resp.items;
  } finally {
    healthLoading.value = false;
  }
}

watch([tab, service], ([t, s]) => {
  if (t === 'health' && s && healthLoadedFor !== s.slug) void loadHealthHistory();
});

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

function onTopAppClick(row: BreakdownRow) {
  if (row.key != null) router.push(`/applications/${row.key}`);
}

onMounted(load);
</script>

<template>
  <el-button link style="margin-bottom: 12px;" @click="router.back()">
    <Icon name="chevron-left" :size="14" /> 返回
  </el-button>

  <div v-if="service">
    <PageHeader :title="service.slug" :description="service.display_name">
      <template #actions>
        <HealthDot :status="service.health_status" />
        <StatusTag :status="service.status" />
      </template>
    </PageHeader>

    <el-tabs v-model="tab">
      <el-tab-pane label="概览" name="overview">
        <div class="overview">
          <div class="overview__row">
            <div class="overview__label">调用路径</div>
            <div class="overview__value mono">
              {{ gatewayUrl(service.slug) }}
              <CopyButton :text="gatewayUrl(service.slug)" />
            </div>
          </div>
          <div class="overview__row">
            <div class="overview__label">端点 URL</div>
            <div class="overview__value mono">
              {{ service.endpoint_url }}
              <CopyButton :text="service.endpoint_url" />
            </div>
          </div>
          <div class="overview__row">
            <div class="overview__label">Transport</div>
            <div class="overview__value">{{ service.transport }}</div>
          </div>
          <div class="overview__row">
            <div class="overview__label">显示名</div>
            <div class="overview__value">{{ service.display_name }}</div>
          </div>
          <div class="overview__row">
            <div class="overview__label">所属团队</div>
            <div class="overview__value">{{ service.owner_team || '—' }}</div>
          </div>
          <div class="overview__row">
            <div class="overview__label">QPS 限流</div>
            <div class="overview__value">
              <template v-if="canEdit">
                <div class="qps-edit">
                  <el-input-number
                    v-model="qpsDraft"
                    :min="0"
                    :controls="false"
                    placeholder="不限"
                    style="width: 140px;"
                  />
                  <el-button
                    type="primary"
                    size="small"
                    :loading="qpsSaving"
                    @click="onSaveQps"
                  >保存</el-button>
                  <el-button link type="primary" size="small" @click="clearQpsDraft">不限</el-button>
                  <span class="qps-edit__current">当前：{{ formatQps(service.rate_limit_qps) }}</span>
                </div>
              </template>
              <template v-else>
                {{ formatQps(service.rate_limit_qps) }}
              </template>
            </div>
          </div>
          <div class="overview__row">
            <div class="overview__label">描述</div>
            <div class="overview__value">{{ service.description || '—' }}</div>
          </div>
          <div class="overview__row">
            <div class="overview__label">注册时间</div>
            <div class="overview__value">{{ formatDateTime(service.created_at) }}</div>
          </div>
          <div class="overview__row">
            <div class="overview__label">最近修改</div>
            <div class="overview__value">{{ formatDateTime(service.updated_at) }}</div>
          </div>
          <div class="overview__row">
            <div class="overview__label">最近健康检查</div>
            <div class="overview__value"><RelativeTime :value="service.last_health_check_at" /></div>
          </div>
        </div>
      </el-tab-pane>
      <el-tab-pane :label="`授权应用（${permissions.length}）`" name="permissions">
        <div v-loading="permLoading" class="perm-panel">
          <div class="perm-panel__header">
            <span class="perm-panel__title">授权应用</span>
            <span class="perm-panel__hint">
              授权由应用自主管理：在
              <router-link to="/applications">应用列表</router-link>
              的对应应用详情中勾选/取消本服务。
            </span>
          </div>
          <el-table :data="permissions" empty-text="暂无授权应用" style="width: 100%;">
            <el-table-column prop="application_id" label="应用 ID" width="100" />
            <el-table-column label="应用名称">
              <template #default="{ row }">
                <router-link :to="`/applications/${row.application_id}`">
                  {{ appNameById(row.application_id) }}
                </router-link>
              </template>
            </el-table-column>
            <el-table-column label="授权时间" width="200">
              <template #default="{ row }">{{ formatDateTime(row.granted_at) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
      <el-tab-pane label="调用统计" name="stats">
        <div class="stats-block">
          <div class="stats-toolbar">
            <RangePicker v-model:range="statsRange" />
            <span class="stats-block__hint">
              完整视图见 <router-link to="/dashboard">仪表盘</router-link>。
            </span>
          </div>
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
          </div>
          <div class="stats-row">
            <div class="stats-row__col">
              <h4 class="stats-row__title">调用趋势</h4>
              <TimeseriesChart
                :points="sparkline?.points ?? []"
                metric="calls"
                :range="statsRange"
                :loading="sparkLoading"
                :height="240"
              />
            </div>
            <div class="stats-row__col">
              <h4 class="stats-row__title">Top 5 调用方应用</h4>
              <BarChart
                :rows="topApps"
                :loading="topAppsLoading"
                :height="220"
                @row-click="onTopAppClick"
              />
            </div>
          </div>
        </div>
      </el-tab-pane>
      <el-tab-pane label="健康历史" name="health">
        <div v-loading="healthLoading" class="health-history">
          <el-table
            :data="healthEvents"
            empty-text="暂无状态变化记录"
            style="width: 100%;"
          >
            <el-table-column label="发生时间" width="200">
              <template #default="{ row }: { row: HealthHistoryItem }">
                {{ formatDateTime(row.ts) }}
              </template>
            </el-table-column>
            <el-table-column label="状态变化">
              <template #default="{ row }: { row: HealthHistoryItem }">
                <span class="health-change">
                  <HealthDot :status="row.from_status ?? 'unknown'" />
                  <span class="health-change__label">{{ healthLabel(row.from_status) }}</span>
                  <span class="health-change__arrow">→</span>
                  <HealthDot :status="row.to_status ?? 'unknown'" />
                  <span class="health-change__label">{{ healthLabel(row.to_status) }}</span>
                </span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.overview {
  background: var(--color-surface);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-base);
}
.overview__row {
  display: flex;
  padding: var(--space-3) var(--space-5);
  border-bottom: 1px solid var(--color-gray-100);
}
.overview__row:last-child { border-bottom: none; }
.overview__label {
  width: 160px;
  color: var(--color-gray-500);
  font-size: var(--text-sm);
}
.overview__value {
  flex: 1;
  color: var(--color-gray-800);
  font-size: var(--text-sm);
}
.perm-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}
.perm-panel__title {
  font-size: var(--text-base);
  font-weight: 500;
  color: var(--color-gray-800);
}
.perm-panel__hint {
  font-size: var(--text-xs);
  color: var(--color-gray-500);
}
.qps-edit {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.qps-edit__current {
  margin-left: var(--space-2);
  color: var(--color-gray-500);
  font-size: var(--text-xs);
}
.stats-block {
  padding: var(--space-2) 0 var(--space-4);
}
.stats-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}
.stats-block__hint {
  font-size: var(--text-xs);
  color: var(--color-gray-500);
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}
.stats-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
}
.stats-row__title {
  margin: 0 0 var(--space-2);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-gray-700);
}
.health-history {
  padding: var(--space-2) 0;
}
.health-change {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
}
.health-change__label {
  color: var(--color-gray-700);
}
.health-change__arrow {
  color: var(--color-gray-400);
  margin: 0 var(--space-1);
}
@media (max-width: 960px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .stats-row { grid-template-columns: 1fr; }
}
</style>
