<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  getApplication,
  updateApplication,
  type Application,
} from '@/api/applications';
import { listServices, type McpService } from '@/api/services';
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
import RelativeTime from '@/components/common/RelativeTime.vue';
import Icon from '@/components/icons/Icon.vue';
import KpiCard from '@/components/charts/KpiCard.vue';
import TimeseriesChart from '@/components/charts/TimeseriesChart.vue';
import BarChart from '@/components/charts/BarChart.vue';
import RangePicker from '@/components/charts/RangePicker.vue';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const app = ref<Application | null>(null);
const services = ref<McpService[]>([]);
const loading = ref(false);

const draft = ref<number[]>([]);
const saving = ref(false);

const canEdit = computed(() => auth.hasRole('admin', 'operator'));

// 编辑团队 / 描述
const infoDialog = ref<{ visible: boolean; submitting: boolean; team: string; description: string }>({
  visible: false,
  submitting: false,
  team: '',
  description: '',
});

function openInfoEdit() {
  if (!app.value) return;
  infoDialog.value.team = app.value.team ?? '';
  infoDialog.value.description = app.value.description ?? '';
  infoDialog.value.visible = true;
}

async function saveInfo() {
  if (!app.value) return;
  infoDialog.value.submitting = true;
  try {
    const updated = await updateApplication(app.value.id, {
      team: infoDialog.value.team.trim(),
      description: infoDialog.value.description.trim(),
    });
    app.value = updated;
    infoDialog.value.visible = false;
    ElMessage.success('已保存');
  } finally {
    infoDialog.value.submitting = false;
  }
}

function serviceById(id: number): McpService | undefined {
  return services.value.find((s) => s.id === id);
}

const dirty = computed(() => {
  if (!app.value) return false;
  const current = [...app.value.service_ids].sort();
  const next = [...draft.value].sort();
  if (current.length !== next.length) return true;
  return current.some((v, i) => v !== next[i]);
});

const authorizedServices = computed<McpService[]>(() => {
  if (!app.value) return [];
  return app.value.service_ids
    .map((id) => serviceById(id))
    .filter((s): s is McpService => s !== undefined);
});

async function load() {
  loading.value = true;
  try {
    const id = Number(route.params.id);
    const [appData, svcList] = await Promise.all([getApplication(id), listServices()]);
    app.value = appData;
    services.value = svcList.items;
    draft.value = [...appData.service_ids];
  } finally {
    loading.value = false;
  }
}

// ---- 调用概况（支持 24h / 7d / 30d / all） ----
const statsRange = ref<Range>('24h');
const overview = ref<OverviewResp | null>(null);
const overviewLoading = ref(false);
const sparkline = ref<TimeseriesResp | null>(null);
const sparkLoading = ref(false);
const topServices = ref<BreakdownRow[]>([]);
const topServicesLoading = ref(false);

async function loadStats() {
  if (!app.value) return;
  const r = statsRange.value;
  const filter = { application_id: app.value.id };
  overviewLoading.value = true;
  sparkLoading.value = true;
  topServicesLoading.value = true;
  await Promise.all([
    getOverview({ range: r, ...filter })
      .then((res) => (overview.value = res))
      .finally(() => (overviewLoading.value = false)),
    getTimeseries({ metric: 'calls', range: r, ...filter })
      .then((res) => (sparkline.value = res))
      .finally(() => (sparkLoading.value = false)),
    getBreakdown({ dim: 'service', range: r, limit: 5, ...filter })
      .then((res) => (topServices.value = res.rows))
      .finally(() => (topServicesLoading.value = false)),
  ]);
}

// 应用对象就绪 / range 切换 都触发一次加载。
watch([app, statsRange], ([a]) => {
  if (a) void loadStats();
});

function pctFormatter(v: string | number | null | undefined): string {
  if (v == null) return '—';
  const n = typeof v === 'number' ? v : Number(v);
  return (n * 100).toFixed(2) + '%';
}

function onTopServiceClick(row: BreakdownRow) {
  // breakdown for dim=service: label 是 slug（与 dashboard 一致）
  if (row.label) router.push(`/services/${row.label}`);
}

function resetDraft() {
  if (app.value) draft.value = [...app.value.service_ids];
}

async function onSave() {
  if (!app.value) return;
  const removed = app.value.service_ids.filter((id) => !draft.value.includes(id));
  if (removed.length > 0) {
    try {
      const removedSlugs = removed
        .map((id) => serviceById(id)?.slug ?? `#${id}`)
        .join('、');
      await ElMessageBox.confirm(
        `将取消该应用对 ${removedSlugs} 的调用权限（最长 30 秒生效）。确认保存？`,
        '确认变更',
        { type: 'warning' },
      );
    } catch {
      return;
    }
  }
  saving.value = true;
  try {
    const updated = await updateApplication(app.value.id, {
      service_ids: draft.value,
    });
    app.value = updated;
    draft.value = [...updated.service_ids];
    ElMessage.success('已保存');
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <el-button link style="margin-bottom: 12px;" @click="router.back()">
    <Icon name="chevron-left" :size="14" /> 返回
  </el-button>

  <div v-if="app" v-loading="loading">
    <PageHeader :title="app.name" :description="`团队：${app.team || '—'}`">
      <template v-if="canEdit" #actions>
        <el-button @click="openInfoEdit">编辑信息</el-button>
      </template>
    </PageHeader>

    <div class="overview">
      <div class="overview__row">
        <div class="overview__label">应用 ID</div>
        <div class="overview__value mono">{{ app.id }}</div>
      </div>
      <div class="overview__row">
        <div class="overview__label">描述</div>
        <div class="overview__value">{{ app.description || '—' }}</div>
      </div>
      <div class="overview__row">
        <div class="overview__label">创建时间</div>
        <div class="overview__value"><RelativeTime :value="app.created_at" /></div>
      </div>
      <div class="overview__row">
        <div class="overview__label">创建人 ID</div>
        <div class="overview__value">{{ app.owner_user_id }}</div>
      </div>
    </div>

    <section class="stats-block">
      <div class="stats-block__header">
        <h3 class="stats-block__title">调用概况</h3>
        <RangePicker v-model:range="statsRange" />
        <span class="stats-block__hint">完整视图见<router-link to="/dashboard">仪表盘</router-link></span>
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
          label="被限流次数"
          icon="zap-off"
          tone="info"
          :value="overview?.throttled ?? null"
          :loading="overviewLoading"
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
          <h4 class="stats-row__title">Top 5 被调服务</h4>
          <BarChart
            :rows="topServices"
            :loading="topServicesLoading"
            :height="220"
            @row-click="onTopServiceClick"
          />
        </div>
      </div>
    </section>

    <div style="margin-top: 24px;">
      <h3 style="margin-bottom: 12px;">API Keys</h3>
      <p class="text-secondary" style="font-size: 13px;">
        请到
        <router-link :to="{ name: 'ApiKeyList', query: { application_id: app.id } }">API Key 管理</router-link>
        查看本应用的密钥。
      </p>
    </div>

    <div class="services-block">
      <div class="services-block__header">
        <h3>可调用服务</h3>
        <span class="services-block__hint">
          勾选的服务才能被本应用调用。授权关系会自动同步到对应服务的「授权应用」列表。
        </span>
      </div>

      <template v-if="canEdit">
        <el-select
          v-model="draft"
          multiple
          filterable
          placeholder="选择该应用可调用的服务"
          style="width: 100%; max-width: 720px;"
        >
          <el-option
            v-for="s in services"
            :key="s.id"
            :value="s.id"
            :label="`${s.slug} · ${s.display_name}`"
          />
        </el-select>
        <div class="services-block__actions">
          <el-button
            type="primary"
            :loading="saving"
            :disabled="!dirty"
            @click="onSave"
          >保存</el-button>
          <el-button :disabled="!dirty || saving" @click="resetDraft">还原</el-button>
        </div>
      </template>

      <el-table
        :data="authorizedServices"
        empty-text="暂无授权服务"
        style="width: 100%; margin-top: 16px;"
      >
        <el-table-column prop="id" label="服务 ID" width="100" />
        <el-table-column label="服务标识" width="220">
          <template #default="{ row }: { row: McpService }">
            <router-link :to="`/services/${row.slug}`" class="mono">{{ row.slug }}</router-link>
          </template>
        </el-table-column>
        <el-table-column label="服务名称">
          <template #default="{ row }: { row: McpService }">{{ row.display_name }}</template>
        </el-table-column>
        <el-table-column label="所属团队" width="160">
          <template #default="{ row }: { row: McpService }">{{ row.owner_team || '—' }}</template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="infoDialog.visible" title="编辑应用信息" width="480">
      <el-form label-position="top">
        <el-form-item label="团队">
          <el-input
            v-model="infoDialog.team"
            maxlength="128"
            show-word-limit
            placeholder="可留空"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="infoDialog.description"
            type="textarea"
            :rows="3"
            placeholder="可留空"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="infoDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="infoDialog.submitting" @click="saveInfo">保存</el-button>
      </template>
    </el-dialog>
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
  font-size: var(--text-sm);
}
.services-block {
  margin-top: 24px;
}
.services-block__header {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: 12px;
}
.services-block__header h3 {
  margin: 0;
}
.services-block__hint {
  font-size: var(--text-xs);
  color: var(--color-gray-500);
}
.services-block__actions {
  margin-top: var(--space-3);
  display: flex;
  gap: var(--space-2);
}
.stats-block {
  margin-top: var(--space-6);
}
.stats-block__header {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}
.stats-block__title {
  margin: 0;
  font-size: var(--text-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-gray-800);
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
@media (max-width: 960px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .stats-row { grid-template-columns: 1fr; }
}
</style>
