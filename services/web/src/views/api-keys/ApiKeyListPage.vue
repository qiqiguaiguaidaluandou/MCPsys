<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import {
  listApiKeys,
  revokeApiKey,
  deleteApiKeyPermanent,
  updateApiKey,
  type ApiKey,
} from '@/api/api-keys';
import { useAuthStore } from '@/stores/auth';
import PageHeader from '@/components/common/PageHeader.vue';
import DataTable from '@/components/common/DataTable.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import ApiKeyIssueModal from '@/components/feature/ApiKeyIssueModal.vue';
import Icon from '@/components/icons/Icon.vue';
import { ElMessage, ElMessageBox } from 'element-plus';

const route = useRoute();
const auth = useAuthStore();
const items = ref<ApiKey[]>([]);
const loading = ref(false);
const issueOpen = ref(false);

const canEdit = computed(() => auth.hasRole('admin', 'operator'));

const qpsDrafts = ref<Record<number, number | null>>({});
const qpsSavingId = ref<number | null>(null);

function formatQps(qps: number | null | undefined): string {
  if (qps === null || qps === undefined) return '不限';
  if (qps === 0) return '停用 (0)';
  return `${qps} QPS`;
}

function onQpsPopoverShow(key: ApiKey) {
  qpsDrafts.value[key.id] = key.rate_limit_qps;
}

async function onSaveQps(key: ApiKey) {
  qpsSavingId.value = key.id;
  try {
    await updateApiKey(key.id, { rate_limit_qps: qpsDrafts.value[key.id] ?? null });
    ElMessage.success('已保存');
    await load();
  } finally {
    qpsSavingId.value = null;
  }
}

async function load() {
  loading.value = true;
  try {
    items.value = (await listApiKeys()).items;
  } finally {
    loading.value = false;
  }
}

async function onRevoke(key: ApiKey) {
  await ElMessageBox.confirm(`确认吊销 "${key.name}" (${key.key_prefix}...)？此操作不可逆。`, '吊销 API Key', {
    type: 'warning',
    confirmButtonText: '吊销',
    cancelButtonText: '取消',
  });
  await revokeApiKey(key.id);
  ElMessage.success('已吊销');
  await load();
}

async function onDelete(key: ApiKey) {
  await ElMessageBox.confirm(
    `确认永久删除 "${key.name}" (${key.key_prefix}...)？删除后记录从列表移除，无法恢复。`,
    '永久删除 API Key',
    {
      type: 'warning',
      confirmButtonText: '永久删除',
      cancelButtonText: '取消',
      confirmButtonClass: 'el-button--danger',
    },
  );
  await deleteApiKeyPermanent(key.id);
  ElMessage.success('已删除');
  await load();
}

onMounted(load);
</script>

<template>
  <PageHeader title="API Key" description="所有签发的 API Key；密钥明文只在签发时显示一次">
    <template #actions>
      <el-button type="primary" @click="issueOpen = true">
        <Icon name="plus" :size="14" /> 签发新 Key
      </el-button>
    </template>
  </PageHeader>

  <DataTable :data="items" :loading="loading">
    <el-table-column label="Prefix" width="140">
      <template #default="{ row }: { row: ApiKey }">
        <span class="mono">{{ row.key_prefix }}...</span>
      </template>
    </el-table-column>
    <el-table-column prop="name" label="名称" min-width="200" />
    <el-table-column label="归属" width="160">
      <template #default="{ row }: { row: ApiKey }">
        {{ row.owner_type }} #{{ row.owner_id }}
      </template>
    </el-table-column>
    <el-table-column label="QPS 限流" width="180">
      <template #default="{ row }: { row: ApiKey }">
        <span class="qps-cell">{{ formatQps(row.rate_limit_qps) }}</span>
        <el-popover
          v-if="canEdit && !row.revoked_at"
          trigger="click"
          :width="260"
          @before-enter="onQpsPopoverShow(row)"
        >
          <template #reference>
            <el-button link type="primary" size="small">编辑</el-button>
          </template>
          <div class="qps-pop">
            <el-input-number
              v-model="qpsDrafts[row.id]"
              :min="0"
              :controls="false"
              placeholder="不限"
              style="width: 140px;"
            />
            <el-button link type="primary" size="small" @click="qpsDrafts[row.id] = null">不限</el-button>
            <div class="qps-pop__hint">留空 = 不限；0 = 停用</div>
            <div class="qps-pop__actions">
              <el-button
                type="primary"
                size="small"
                :loading="qpsSavingId === row.id"
                @click="onSaveQps(row)"
              >保存</el-button>
            </div>
          </div>
        </el-popover>
      </template>
    </el-table-column>
    <el-table-column label="最近使用" width="140">
      <template #default="{ row }: { row: ApiKey }"><RelativeTime :value="row.last_used_at" /></template>
    </el-table-column>
    <el-table-column label="状态" width="100">
      <template #default="{ row }: { row: ApiKey }">
        <StatusTag :status="row.revoked_at ? 'revoked' : 'active'" />
      </template>
    </el-table-column>
    <el-table-column label="创建时间" width="140">
      <template #default="{ row }: { row: ApiKey }"><RelativeTime :value="row.created_at" /></template>
    </el-table-column>
    <el-table-column label="操作" width="160" fixed="right">
      <template #default="{ row }: { row: ApiKey }">
        <el-button
          link
          type="danger"
          :disabled="!!row.revoked_at"
          @click="onRevoke(row)"
        >吊销</el-button>
        <el-button
          link
          type="danger"
          :disabled="!row.revoked_at"
          @click="onDelete(row)"
        >删除</el-button>
      </template>
    </el-table-column>
  </DataTable>

  <ApiKeyIssueModal
    v-model="issueOpen"
    :default-application-id="Number(route.query.application_id) || undefined"
    @issued="load"
  />
</template>

<style scoped>
.qps-cell {
  margin-right: var(--space-2);
}
.qps-pop {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.qps-pop__hint {
  font-size: var(--text-xs);
  color: var(--color-gray-500);
}
.qps-pop__actions {
  display: flex;
  justify-content: flex-end;
}
</style>
