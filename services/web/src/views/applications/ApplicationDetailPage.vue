<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  getApplication,
  updateApplication,
  type Application,
} from '@/api/applications';
import { listServices, type McpService } from '@/api/services';
import { useAuthStore } from '@/stores/auth';
import PageHeader from '@/components/common/PageHeader.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import Icon from '@/components/icons/Icon.vue';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const app = ref<Application | null>(null);
const services = ref<McpService[]>([]);
const loading = ref(false);

const draft = ref<number[]>([]);
const saving = ref(false);

const canEdit = computed(() => auth.hasRole('admin', 'operator'));

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
  <el-button link @click="router.back()" style="margin-bottom: 12px;">
    <Icon name="chevron-left" :size="14" /> 返回
  </el-button>

  <div v-if="app" v-loading="loading">
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
        <el-table-column label="服务 slug" width="220">
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
</style>
