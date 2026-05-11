<script setup lang="ts">
import { onMounted, ref, reactive } from 'vue';
import { listAuditEvents, type AuditEvent, type AuditEventFilter } from '@/api/audit';
import { listUsers } from '@/api/users';
import type { User } from '@/api/types';
import PageHeader from '@/components/common/PageHeader.vue';
import DataTable from '@/components/common/DataTable.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';

const items = ref<AuditEvent[]>([]);
const total = ref(0);
const loading = ref(false);
const users = ref<User[]>([]);
const filter = reactive<AuditEventFilter>({ page: 1, page_size: 50 });
const dateRange = ref<[string, string] | null>(null);

const ACTIONS: { value: string; label: string; group: string }[] = [
  { value: 'user.create',           label: '创建用户',       group: 'user' },
  { value: 'user.delete',           label: '删除用户',       group: 'user' },
  { value: 'user.password_change',  label: '修改密码',       group: 'user' },
  { value: 'application.create',    label: '创建应用',       group: 'application' },
  { value: 'api_key.issue',         label: '签发 API Key',  group: 'api_key' },
  { value: 'api_key.revoke',        label: '吊销 API Key',  group: 'api_key' },
  { value: 'api_key.update',        label: '修改 API Key',  group: 'api_key' },
  { value: 'api_key.delete',        label: '永久删除 API Key', group: 'api_key' },
  { value: 'service.create',        label: '注册服务',       group: 'service' },
  { value: 'service.update',        label: '修改服务',       group: 'service' },
  { value: 'service.delete',        label: '下线服务',       group: 'service' },
  { value: 'service_permission.grant',  label: '授予权限', group: 'service_permission' },
  { value: 'service_permission.revoke', label: '吊销权限', group: 'service_permission' },
];

const TARGET_TYPES: { value: string; label: string }[] = [
  { value: 'user',               label: '用户' },
  { value: 'application',        label: '应用' },
  { value: 'api_key',            label: 'API Key' },
  { value: 'mcp_service',        label: '服务' },
  { value: 'service_permission', label: '权限' },
];

async function load() {
  loading.value = true;
  try {
    filter.from_ts = dateRange.value?.[0] ?? undefined;
    filter.to_ts   = dateRange.value?.[1] ?? undefined;
    const data = await listAuditEvents(filter);
    items.value = data.items;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

function reset() {
  filter.actor_user_id = undefined;
  filter.action = undefined;
  filter.target_type = undefined;
  filter.target_id = undefined;
  dateRange.value = null;
  filter.page = 1;
  load();
}

function actionLabel(v: string): string {
  return ACTIONS.find((a) => a.value === v)?.label ?? v;
}

onMounted(async () => {
  users.value = (await listUsers()).items;
  await load();
});
</script>

<template>
  <PageHeader title="审计" description="管理动作变更历史" />

  <div class="card-base filter-bar">
    <el-select v-model="filter.action" placeholder="动作" clearable style="width:160px;">
      <el-option-group label="用户">
        <el-option v-for="a in ACTIONS.filter(x => x.group === 'user')" :key="a.value" :label="a.label" :value="a.value" />
      </el-option-group>
      <el-option-group label="应用">
        <el-option v-for="a in ACTIONS.filter(x => x.group === 'application')" :key="a.value" :label="a.label" :value="a.value" />
      </el-option-group>
      <el-option-group label="API Key">
        <el-option v-for="a in ACTIONS.filter(x => x.group === 'api_key')" :key="a.value" :label="a.label" :value="a.value" />
      </el-option-group>
      <el-option-group label="服务">
        <el-option v-for="a in ACTIONS.filter(x => x.group === 'service')" :key="a.value" :label="a.label" :value="a.value" />
      </el-option-group>
      <el-option-group label="权限">
        <el-option v-for="a in ACTIONS.filter(x => x.group === 'service_permission')" :key="a.value" :label="a.label" :value="a.value" />
      </el-option-group>
    </el-select>

    <el-select v-model="filter.target_type" placeholder="目标类型" clearable style="width:140px;">
      <el-option v-for="t in TARGET_TYPES" :key="t.value" :label="t.label" :value="t.value" />
    </el-select>

    <el-input v-model="filter.target_id" placeholder="目标 ID" :disabled="!filter.target_type" style="width:120px;" />

    <el-select v-model="filter.actor_user_id" placeholder="操作者" clearable style="width:160px;">
      <el-option v-for="u in users" :key="u.id" :label="u.username" :value="u.id" />
    </el-select>

    <el-date-picker v-model="dateRange" type="datetimerange" range-separator="-" value-format="YYYY-MM-DDTHH:mm:ss" />

    <el-button @click="reset">重置</el-button>
    <el-button type="primary" @click="load">查询</el-button>
  </div>

  <DataTable :data="items" :loading="loading">
    <el-table-column type="expand">
      <template #default="{ row }: { row: AuditEvent }">
        <div class="diff-grid" :class="{ single: !row.before || !row.after }">
          <div v-if="row.before">
            <div class="diff-label">before</div>
            <pre class="json-block">{{ JSON.stringify(row.before, null, 2) }}</pre>
          </div>
          <div v-if="row.after">
            <div class="diff-label">after</div>
            <pre class="json-block">{{ JSON.stringify(row.after, null, 2) }}</pre>
          </div>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="时间" width="160">
      <template #default="{ row }: { row: AuditEvent }"><RelativeTime :value="row.ts" /></template>
    </el-table-column>
    <el-table-column label="操作者" width="140">
      <template #default="{ row }: { row: AuditEvent }">
        <span v-if="row.actor_username">{{ row.actor_username }}</span>
        <span v-else-if="row.actor_user_id" style="color: var(--color-gray-500);">已删用户#{{ row.actor_user_id }}</span>
        <span v-else>—</span>
      </template>
    </el-table-column>
    <el-table-column label="动作" width="180">
      <template #default="{ row }: { row: AuditEvent }">
        <el-tag size="small">{{ actionLabel(row.action) }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="目标" min-width="200">
      <template #default="{ row }: { row: AuditEvent }">
        <span class="mono">{{ row.target_type }} / {{ row.target_id ?? '—' }}</span>
      </template>
    </el-table-column>
    <el-table-column label="IP" width="140" prop="ip" />
  </DataTable>

  <el-pagination
    v-model:current-page="filter.page"
    :page-size="filter.page_size"
    :total="total"
    layout="prev, pager, next, total"
    style="margin-top: var(--space-4); justify-content: flex-end;"
    @current-change="load"
  />
</template>

<style scoped>
.filter-bar { display: flex; gap: var(--space-3); align-items: center; flex-wrap: wrap; margin-bottom: var(--space-4); }
.diff-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); padding: var(--space-3); }
.diff-grid.single { grid-template-columns: 1fr; max-width: 600px; }
.diff-label { font-size: 12px; color: var(--color-gray-500); margin-bottom: 4px; text-transform: uppercase; }
.json-block {
  background: var(--color-gray-50);
  padding: var(--space-3);
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 12px;
  white-space: pre;
  overflow-x: auto;
  max-height: 360px;
  overflow-y: auto;
  margin: 0;
}
</style>
