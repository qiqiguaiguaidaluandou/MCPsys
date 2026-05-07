<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { listApiKeys, revokeApiKey, deleteApiKeyPermanent, type ApiKey } from '@/api/api-keys';
import PageHeader from '@/components/common/PageHeader.vue';
import DataTable from '@/components/common/DataTable.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import CopyButton from '@/components/common/CopyButton.vue';
import ApiKeyIssueModal from '@/components/feature/ApiKeyIssueModal.vue';
import Icon from '@/components/icons/Icon.vue';
import { ElMessage, ElMessageBox } from 'element-plus';

const route = useRoute();
const items = ref<ApiKey[]>([]);
const loading = ref(false);
const issueOpen = ref(false);

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
    <el-table-column label="Prefix" width="180">
      <template #default="{ row }: { row: ApiKey }">
        <span class="mono">{{ row.key_prefix }}...</span>
        <CopyButton :text="row.key_prefix" />
      </template>
    </el-table-column>
    <el-table-column prop="name" label="名称" min-width="200" />
    <el-table-column label="归属" width="160">
      <template #default="{ row }: { row: ApiKey }">
        {{ row.owner_type }} #{{ row.owner_id }}
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
