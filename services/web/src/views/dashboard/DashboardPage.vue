<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { client } from '@/api/client';
import { useAuthStore } from '@/stores/auth';
import PageHeader from '@/components/common/PageHeader.vue';
import Icon from '@/components/icons/Icon.vue';
import { ROLE_LABELS } from '@/utils/constants';
import { formatRelative } from '@/utils/format';

const auth = useAuthStore();

const stats = ref({
  serviceCount: 0,
  callsLast24h: 0,
  errorRateLast24h: 0,
  loading: true,
});

const roleLabel = computed(() => {
  const role = auth.user?.role;
  return role ? ROLE_LABELS[role] : '—';
});

interface CallLogLite { ts: string; status: string; }

async function loadStats() {
  stats.value.loading = true;
  try {
    const [services, logs] = await Promise.all([
      client.get('/api/v1/services').then((r) => r.data),
      client.get('/api/v1/call-logs?limit=1000').then((r) => r.data),
    ]);
    stats.value.serviceCount = services.total ?? services.items?.length ?? 0;
    const items: CallLogLite[] = logs.items ?? [];
    const cutoff = Date.now() - 24 * 3600 * 1000;
    const recent = items.filter((l) => new Date(l.ts).getTime() >= cutoff);
    stats.value.callsLast24h = recent.length;
    const errors = recent.filter((l) => l.status !== 'success').length;
    stats.value.errorRateLast24h = recent.length > 0 ? (errors / recent.length) * 100 : 0;
  } finally {
    stats.value.loading = false;
  }
}

onMounted(loadStats);
</script>

<template>
  <PageHeader title="仪表盘" description="MCP 系统总体概况" />

  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-card__icon" style="background: var(--color-info-bg); color: var(--color-info);">
        <Icon name="boxes" :size="20" />
      </div>
      <div class="kpi-card__main">
        <div class="kpi-card__label">注册服务数</div>
        <div class="kpi-card__value">{{ stats.loading ? '—' : stats.serviceCount }}</div>
      </div>
    </div>

    <div class="kpi-card">
      <div class="kpi-card__icon" style="background: var(--color-primary-50); color: var(--color-primary-500);">
        <Icon name="activity" :size="20" />
      </div>
      <div class="kpi-card__main">
        <div class="kpi-card__label">24h 调用次数</div>
        <div class="kpi-card__value">{{ stats.loading ? '—' : stats.callsLast24h.toLocaleString() }}</div>
      </div>
    </div>

    <div class="kpi-card">
      <div class="kpi-card__icon" style="background: var(--color-warning-bg); color: var(--color-warning);">
        <Icon name="trending-up" :size="20" />
      </div>
      <div class="kpi-card__main">
        <div class="kpi-card__label">24h 错误率</div>
        <div class="kpi-card__value">{{ stats.loading ? '—' : stats.errorRateLast24h.toFixed(1) + ' %' }}</div>
      </div>
    </div>

    <div class="kpi-card">
      <div class="kpi-card__icon" style="background: var(--color-success-bg); color: var(--color-success);">
        <Icon name="user-circle" :size="20" />
      </div>
      <div class="kpi-card__main">
        <div class="kpi-card__label">我的角色</div>
        <div class="kpi-card__value">{{ roleLabel }}</div>
        <div class="kpi-card__sub">上次登录 {{ formatRelative(auth.user?.last_login_at) }}</div>
      </div>
    </div>
  </div>

  <div class="dashboard-iframe-wrap">
    <iframe
      class="dashboard-iframe"
      src="/grafana/d/mcpsys-overview/mcp-overview?theme=light&kiosk=tv"
      title="MCP Overview"
    />
  </div>
</template>

<style scoped>
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}
.kpi-card {
  display: flex;
  gap: var(--space-3);
  background: var(--color-surface);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-base);
  padding: var(--space-5);
}
.kpi-card__icon {
  width: 40px; height: 40px;
  border-radius: var(--radius-base);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.kpi-card__label {
  font-size: var(--text-sm);
  color: var(--color-gray-500);
}
.kpi-card__value {
  font-size: var(--text-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-gray-900);
  line-height: var(--leading-tight);
  margin-top: var(--space-1);
}
.kpi-card__sub {
  font-size: var(--text-xs);
  color: var(--color-gray-400);
  margin-top: var(--space-1);
}
.dashboard-iframe-wrap {
  background: var(--color-surface);
  border-radius: var(--radius-base);
  border: 1px solid var(--color-gray-200);
  overflow: hidden;
}
.dashboard-iframe {
  width: 100%;
  height: 720px;
  border: none;
}
</style>
