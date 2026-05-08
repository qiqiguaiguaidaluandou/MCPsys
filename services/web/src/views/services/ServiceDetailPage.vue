<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { getService, type McpService } from '@/api/services';
import { listApplications, type Application } from '@/api/applications';
import {
  listServicePermissions,
  grantPermission,
  revokePermission,
  type Permission,
} from '@/api/permissions';
import { useAuthStore } from '@/stores/auth';
import PageHeader from '@/components/common/PageHeader.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import HealthDot from '@/components/feature/HealthDot.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import CopyButton from '@/components/common/CopyButton.vue';
import Icon from '@/components/icons/Icon.vue';
import { formatDateTime } from '@/utils/format';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const service = ref<McpService | null>(null);
const loading = ref(false);
const tab = ref('overview');

const permissions = ref<Permission[]>([]);
const permLoading = ref(false);
const apps = ref<Application[]>([]);
const grantDialogOpen = ref(false);
const grantForm = ref<{ application_id: number | null; note: string }>({
  application_id: null,
  note: '',
});
const granting = ref(false);

const canEdit = computed(() => auth.hasRole('admin', 'operator'));

const availableApps = computed(() => {
  const granted = new Set(permissions.value.map((p) => p.application_id));
  return apps.value.filter((a) => !granted.has(a.id));
});

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

function openGrantDialog() {
  grantForm.value = { application_id: null, note: '' };
  grantDialogOpen.value = true;
}

async function onGrant() {
  if (!service.value || !grantForm.value.application_id) return;
  granting.value = true;
  try {
    await grantPermission(
      service.value.slug,
      grantForm.value.application_id,
      grantForm.value.note || undefined,
    );
    ElMessage.success('已授权');
    grantDialogOpen.value = false;
    await reloadPermissions();
  } finally {
    granting.value = false;
  }
}

async function onRevoke(applicationId: number) {
  if (!service.value) return;
  try {
    await ElMessageBox.confirm(
      '撤销后，该应用将立刻无法调用本服务（最长 30 秒生效）',
      '确认撤销',
      { type: 'warning' },
    );
  } catch {
    return;
  }
  await revokePermission(service.value.slug, applicationId);
  ElMessage.success('已撤销');
  await reloadPermissions();
}

async function load() {
  loading.value = true;
  try {
    service.value = await getService(Number(route.params.id));
    await Promise.all([reloadPermissions(), reloadApps()]);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <el-button link @click="router.back()" style="margin-bottom: 12px;">
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
      <el-tab-pane label="授权应用" name="permissions">
        <div v-loading="permLoading" class="perm-panel">
          <div class="perm-panel__header">
            <span class="perm-panel__title">授权应用</span>
            <el-button
              v-if="canEdit"
              type="primary"
              size="small"
              @click="openGrantDialog"
            >
              <Icon name="plus" :size="14" /> 授权
            </el-button>
          </div>
          <el-table :data="permissions" empty-text="暂无授权应用" style="width: 100%;">
            <el-table-column prop="application_id" label="应用 ID" width="100" />
            <el-table-column label="应用名称">
              <template #default="{ row }">{{ appNameById(row.application_id) }}</template>
            </el-table-column>
            <el-table-column label="授权时间" width="200">
              <template #default="{ row }">{{ formatDateTime(row.granted_at) }}</template>
            </el-table-column>
            <el-table-column prop="note" label="备注">
              <template #default="{ row }">{{ row.note || '—' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button
                  type="danger"
                  size="small"
                  link
                  :disabled="!canEdit"
                  @click="onRevoke(row.application_id)"
                >
                  撤销
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <el-dialog v-model="grantDialogOpen" title="授权应用调用此服务" width="480">
          <el-form :model="grantForm" label-width="80px">
            <el-form-item label="应用">
              <el-select
                v-model="grantForm.application_id"
                filterable
                placeholder="选择应用"
                style="width: 100%;"
              >
                <el-option
                  v-for="app in availableApps"
                  :key="app.id"
                  :label="`${app.id} · ${app.name}`"
                  :value="app.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="备注">
              <el-input
                v-model="grantForm.note"
                maxlength="200"
                placeholder="可选"
                show-word-limit
              />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="grantDialogOpen = false">取消</el-button>
            <el-button
              type="primary"
              :loading="granting"
              :disabled="!grantForm.application_id"
              @click="onGrant"
            >
              确认授权
            </el-button>
          </template>
        </el-dialog>
      </el-tab-pane>
      <el-tab-pane label="调用统计" name="stats">
        <div class="text-secondary" style="padding: 16px;">
          调用统计图表将在本服务接入 Grafana 子面板后显示（v1）。
        </div>
      </el-tab-pane>
      <el-tab-pane label="健康历史" name="health">
        <div class="text-secondary" style="padding: 16px;">健康检查历史（v1）。</div>
      </el-tab-pane>
      <el-tab-pane label="版本（v1）" name="versions" disabled />
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
</style>
