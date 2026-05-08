<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { queryCallLogs, type CallLog, type CallLogQuery, type CallStatus } from '@/api/call-logs';
import { listServices, type McpService } from '@/api/services';
import PageHeader from '@/components/common/PageHeader.vue';
import DataTable from '@/components/common/DataTable.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import Icon from '@/components/icons/Icon.vue';
import { formatDateTime, formatDuration } from '@/utils/format';
import dayjs from 'dayjs';

const items = ref<CallLog[]>([]);
const total = ref(0);
const loading = ref(false);
const services = ref<McpService[]>([]);

const filters = reactive<{
  range: '1h' | '24h' | '7d' | 'all';
  status: CallStatus | '';
  service_id: number | '';
  page: number;
  pageSize: number;
}>({
  range: '24h',
  status: '',
  service_id: '',
  page: 1,
  pageSize: 50,
});

async function load() {
  loading.value = true;
  try {
    const params: CallLogQuery = {
      limit: filters.pageSize,
      offset: (filters.page - 1) * filters.pageSize,
    };
    if (filters.status) params.status = filters.status;
    if (filters.service_id) params.service_id = filters.service_id;
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

onMounted(async () => {
  await loadServices();
  await load();
});

function isSlowCall(ms: number) {
  return ms > 1000;
}

function getServiceSlug(id: number): string {
  return services.value.find((s) => s.id === id)?.slug ?? `#${id}`;
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
    <el-select v-model="filters.service_id" placeholder="服务" clearable style="width: 200px;" @change="load">
      <el-option v-for="s in services" :key="s.id" :value="s.id" :label="s.slug" />
    </el-select>
    <el-select v-model="filters.status" placeholder="状态" clearable style="width: 120px;" @change="load">
      <el-option label="成功" value="success" />
      <el-option label="错误" value="error" />
      <el-option label="超时" value="timeout" />
      <el-option label="拒绝" value="denied" />
      <el-option label="限流" value="throttled" />
    </el-select>
    <div style="flex: 1" />
    <el-button @click="load"><Icon name="refresh-cw" :size="14" /> 刷新</el-button>
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
  </DataTable>
</template>

<style scoped>
.filter-bar {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-4);
}
</style>
