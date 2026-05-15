<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { getService, updateService, type McpService } from '@/api/services';
import { listApplications, type Application } from '@/api/applications';
import { listServicePermissions, type Permission } from '@/api/permissions';
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

const qpsDraft = ref<number | null>(null);
const qpsSaving = ref(false);

const canEdit = computed(() => auth.hasRole('admin', 'operator'));

function formatQps(qps: number | null | undefined): string {
  if (qps === null || qps === undefined) return '不限';
  if (qps === 0) return '停用 (0)';
  return `${qps} QPS`;
}

async function onSaveQps() {
  if (!service.value) return;
  qpsSaving.value = true;
  try {
    await updateService(service.value.slug, { rate_limit_qps: qpsDraft.value });
    ElMessage.success('已保存');
    await load();
  } finally {
    qpsSaving.value = false;
  }
}

function clearQpsDraft() {
  qpsDraft.value = null;
}

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

async function load() {
  loading.value = true;
  try {
    service.value = await getService(String(route.params.slug));
    qpsDraft.value = service.value.rate_limit_qps;
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
            <div class="overview__label">QPS 限流</div>
            <div class="overview__value">
              <template v-if="canEdit">
                <div class="qps-edit">
                  <el-input-number
                    v-model="qpsDraft"
                    :min="0"
                    :controls="false"
                    placeholder="不限"
                    style="width: 140px;"
                  />
                  <el-button
                    type="primary"
                    size="small"
                    :loading="qpsSaving"
                    @click="onSaveQps"
                  >保存</el-button>
                  <el-button link type="primary" size="small" @click="clearQpsDraft">不限</el-button>
                  <span class="qps-edit__current">当前：{{ formatQps(service.rate_limit_qps) }}</span>
                </div>
              </template>
              <template v-else>
                {{ formatQps(service.rate_limit_qps) }}
              </template>
            </div>
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
      <el-tab-pane :label="`授权应用（${permissions.length}）`" name="permissions">
        <div v-loading="permLoading" class="perm-panel">
          <div class="perm-panel__header">
            <span class="perm-panel__title">授权应用</span>
            <span class="perm-panel__hint">
              授权由应用自主管理：在
              <router-link to="/applications">应用列表</router-link>
              的对应应用详情中勾选/取消本服务。
            </span>
          </div>
          <el-table :data="permissions" empty-text="暂无授权应用" style="width: 100%;">
            <el-table-column prop="application_id" label="应用 ID" width="100" />
            <el-table-column label="应用名称">
              <template #default="{ row }">
                <router-link :to="`/applications/${row.application_id}`">
                  {{ appNameById(row.application_id) }}
                </router-link>
              </template>
            </el-table-column>
            <el-table-column label="授权时间" width="200">
              <template #default="{ row }">{{ formatDateTime(row.granted_at) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
      <el-tab-pane label="调用统计" name="stats">
        <div class="text-secondary" style="padding: 16px;">
          本服务调用统计将在 v1-d PR4 中以原生 KPI + 时序图呈现；当前可通过
          <router-link to="/dashboard">仪表盘</router-link>
          看全局视图，并在 BarChart 「Top 服务」 中点击本服务跳转。
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
.perm-panel__hint {
  font-size: var(--text-xs);
  color: var(--color-gray-500);
}
.qps-edit {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.qps-edit__current {
  margin-left: var(--space-2);
  color: var(--color-gray-500);
  font-size: var(--text-xs);
}
</style>
