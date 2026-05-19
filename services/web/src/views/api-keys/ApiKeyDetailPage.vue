<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getApiKey, type ApiKey } from '@/api/api-keys';
import { listApplications, type Application } from '@/api/applications';
import {
  getOverview,
  getTimeseries,
  type OverviewResp,
  type Range,
  type TimeseriesResp,
} from '@/api/stats';
import PageHeader from '@/components/common/PageHeader.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import Icon from '@/components/icons/Icon.vue';
import KpiCard from '@/components/charts/KpiCard.vue';
import TimeseriesChart from '@/components/charts/TimeseriesChart.vue';
import RangePicker from '@/components/charts/RangePicker.vue';
import { formatDateTime, formatRelative } from '@/utils/format';

const route = useRoute();
const router = useRouter();

const key = ref<ApiKey | null>(null);
const apps = ref<Application[]>([]);
const loading = ref(false);

const statsRange = ref<Range>('24h');
const overview = ref<OverviewResp | null>(null);
const overviewLoading = ref(false);
const callsSeries = ref<TimeseriesResp | null>(null);
const callsLoading = ref(false);
const throttledSeries = ref<TimeseriesResp | null>(null);
const throttledLoading = ref(false);

const ownerLabel = computed(() => {
  if (!key.value) return '';
  if (key.value.owner_type === 'application') {
    const app = apps.value.find((a) => a.id === key.value!.owner_id);
    return app ? app.name : `应用 #${key.value.owner_id}`;
  }
  return `用户 #${key.value.owner_id}（已弃用）`;
});

function formatQps(qps: number | null | undefined): string {
  if (qps === null || qps === undefined) return '不限';
  if (qps === 0) return '停用 (0)';
  return `${qps} QPS`;
}

async function loadStats(id: number) {
  const r = statsRange.value;
  const filter = { api_key_id: id };
  overviewLoading.value = true;
  callsLoading.value = true;
  throttledLoading.value = true;
  await Promise.all([
    getOverview({ range: r, ...filter })
      .then((res) => (overview.value = res))
      .finally(() => (overviewLoading.value = false)),
    getTimeseries({ metric: 'calls', range: r, ...filter })
      .then((res) => (callsSeries.value = res))
      .finally(() => (callsLoading.value = false)),
    getTimeseries({ metric: 'throttled', range: r, ...filter })
      .then((res) => (throttledSeries.value = res))
      .finally(() => (throttledLoading.value = false)),
  ]);
}

async function load() {
  loading.value = true;
  try {
    const id = Number(route.params.id);
    const [k, appList] = await Promise.all([getApiKey(id), listApplications()]);
    key.value = k;
    apps.value = appList.items;
  } finally {
    loading.value = false;
  }
}

// key 就绪 / range 切换 都触发一次加载（首次 load 完 + 之后切 range 都靠这里）。
watch([key, statsRange], ([k]) => {
  if (k) void loadStats(k.id);
});

onMounted(load);
</script>

<template>
  <el-button link style="margin-bottom: 12px;" @click="router.back()">
    <Icon name="chevron-left" :size="14" /> 返回
  </el-button>

  <div v-if="key" v-loading="loading">
    <PageHeader :title="key.name" :description="`${key.key_prefix}...`">
      <template #actions>
        <StatusTag :status="key.revoked_at ? 'revoked' : 'active'" />
      </template>
    </PageHeader>

    <div class="overview">
      <div class="overview__row">
        <div class="overview__label">Prefix</div>
        <div class="overview__value mono">{{ key.key_prefix }}...</div>
      </div>
      <div class="overview__row">
        <div class="overview__label">所属</div>
        <div class="overview__value">
          <router-link
            v-if="key.owner_type === 'application'"
            :to="`/applications/${key.owner_id}`"
          >{{ ownerLabel }}</router-link>
          <span v-else class="text-secondary">{{ ownerLabel }}</span>
        </div>
      </div>
      <div class="overview__row">
        <div class="overview__label">QPS 限流</div>
        <div class="overview__value">{{ formatQps(key.rate_limit_qps) }}</div>
      </div>
      <div class="overview__row">
        <div class="overview__label">创建时间</div>
        <div class="overview__value">{{ formatDateTime(key.created_at) }}</div>
      </div>
      <div class="overview__row">
        <div class="overview__label">过期时间</div>
        <div class="overview__value">{{ key.expires_at ? formatDateTime(key.expires_at) : '不过期' }}</div>
      </div>
      <div v-if="key.revoked_at" class="overview__row">
        <div class="overview__label">吊销时间</div>
        <div class="overview__value">{{ formatDateTime(key.revoked_at) }}</div>
      </div>
    </div>

    <section class="stats-block">
      <div class="stats-block__header">
        <h3 class="stats-block__title">调用概况</h3>
        <RangePicker v-model:range="statsRange" />
        <span class="stats-block__hint">
          所属应用的整体视图见
          <router-link
            v-if="key.owner_type === 'application'"
            :to="`/applications/${key.owner_id}`"
          >应用详情</router-link>
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
          label="被限流次数"
          icon="zap-off"
          tone="info"
          :value="overview?.throttled ?? null"
          :loading="overviewLoading"
        />
        <KpiCard
          label="最近调用"
          icon="clock"
          tone="success"
          :value="overview?.last_call_at ?? null"
          :loading="overviewLoading"
          :formatter="(v) => (v ? formatRelative(String(v)) : '—')"
        />
      </div>
      <div class="stats-row">
        <div class="stats-row__col">
          <h4 class="stats-row__title">调用趋势</h4>
          <TimeseriesChart
            :points="callsSeries?.points ?? []"
            metric="calls"
            :range="statsRange"
            :loading="callsLoading"
            :height="240"
          />
        </div>
        <div class="stats-row__col">
          <h4 class="stats-row__title">被限流趋势</h4>
          <TimeseriesChart
            :points="throttledSeries?.points ?? []"
            metric="throttled"
            :range="statsRange"
            :loading="throttledLoading"
            :height="240"
          />
        </div>
      </div>
    </section>
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
