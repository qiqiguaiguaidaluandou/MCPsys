<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getService, type McpService } from '@/api/services';
import PageHeader from '@/components/common/PageHeader.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import HealthDot from '@/components/feature/HealthDot.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import CopyButton from '@/components/common/CopyButton.vue';
import Icon from '@/components/icons/Icon.vue';
import { formatDateTime } from '@/utils/format';

const route = useRoute();
const router = useRouter();
const service = ref<McpService | null>(null);
const loading = ref(false);
const tab = ref('overview');

async function load() {
  loading.value = true;
  try {
    service.value = await getService(Number(route.params.id));
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
</style>
