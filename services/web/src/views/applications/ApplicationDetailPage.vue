<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getApplication, type Application } from '@/api/applications';
import { listServices, type McpService } from '@/api/services';
import { listApplicationPermissions, type Permission } from '@/api/permissions';
import PageHeader from '@/components/common/PageHeader.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import Icon from '@/components/icons/Icon.vue';
import { formatDateTime } from '@/utils/format';

const route = useRoute();
const router = useRouter();
const app = ref<Application | null>(null);
const permissions = ref<Permission[]>([]);
const permLoading = ref(false);
const services = ref<McpService[]>([]);

function serviceById(id: number): McpService | undefined {
  return services.value.find((s) => s.id === id);
}

async function loadPermissions(applicationId: number) {
  permLoading.value = true;
  try {
    const [permList, svcList] = await Promise.all([
      listApplicationPermissions(applicationId),
      listServices(),
    ]);
    permissions.value = permList.items;
    services.value = svcList.items;
  } finally {
    permLoading.value = false;
  }
}

async function load() {
  const id = Number(route.params.id);
  app.value = await getApplication(id);
  await loadPermissions(id);
}
onMounted(load);
</script>

<template>
  <el-button link @click="router.back()" style="margin-bottom: 12px;">
    <Icon name="chevron-left" :size="14" /> 返回
  </el-button>

  <div v-if="app">
    <PageHeader :title="app.name" :description="`团队：${app.team || '—'}`" />

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

    <div style="margin-top: 24px;">
      <h3 style="margin-bottom: 12px;">API Keys</h3>
      <p class="text-secondary" style="font-size: 13px;">
        请到
        <router-link :to="{ name: 'ApiKeyList', query: { application_id: app.id } }">API Key 管理</router-link>
        查看本应用的密钥。
      </p>
    </div>

    <div style="margin-top: 24px;" v-loading="permLoading">
      <h3 style="margin-bottom: 12px;">可调服务</h3>
      <el-table :data="permissions" empty-text="暂无授权服务" style="width: 100%;">
        <el-table-column prop="service_id" label="服务 ID" width="100" />
        <el-table-column label="服务 slug" width="220">
          <template #default="{ row }">
            <span class="mono">{{ serviceById(row.service_id)?.slug ?? '(unknown)' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="服务名称">
          <template #default="{ row }">
            {{ serviceById(row.service_id)?.display_name ?? '—' }}
          </template>
        </el-table-column>
        <el-table-column label="授权时间" width="200">
          <template #default="{ row }">{{ formatDateTime(row.granted_at) }}</template>
        </el-table-column>
        <el-table-column prop="note" label="备注">
          <template #default="{ row }">{{ row.note || '—' }}</template>
        </el-table-column>
      </el-table>
      <p class="text-secondary" style="font-size: 13px; margin-top: 8px;">
        如需为本应用新增可调服务，请到对应服务的详情页授权。
      </p>
    </div>
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
</style>
