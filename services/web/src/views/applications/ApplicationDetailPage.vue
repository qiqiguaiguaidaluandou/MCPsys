<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getApplication, type Application } from '@/api/applications';
import PageHeader from '@/components/common/PageHeader.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import Icon from '@/components/icons/Icon.vue';

const route = useRoute();
const router = useRouter();
const app = ref<Application | null>(null);

async function load() {
  app.value = await getApplication(Number(route.params.id));
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

    <div style="margin-top: 24px;">
      <h3 style="margin-bottom: 12px;">服务权限</h3>
      <p class="text-secondary" style="font-size: 13px;">
        v1 上线后可在此为本应用授权可调用的服务。
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
