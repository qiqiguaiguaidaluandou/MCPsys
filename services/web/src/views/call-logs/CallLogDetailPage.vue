<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getCallLog, type CallLogDetail } from '@/api/call-logs';
import PageHeader from '@/components/common/PageHeader.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import Icon from '@/components/icons/Icon.vue';
import { formatDateTime, formatDuration } from '@/utils/format';

const route = useRoute();
const router = useRouter();
const log = ref<CallLogDetail | null>(null);
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    log.value = await getCallLog(String(route.params.id));
  } finally {
    loading.value = false;
  }
}

function prettyJson(raw: string | null): string | null {
  if (raw == null) return null;
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

const requestPretty = computed(() => prettyJson(log.value?.request_body ?? null));
const responsePretty = computed(() => prettyJson(log.value?.response_body ?? null));

onMounted(load);
</script>

<template>
  <el-button link style="margin-bottom: 12px;" @click="router.back()">
    <Icon name="chevron-left" :size="14" /> 返回
  </el-button>

  <div v-if="log">
    <PageHeader title="调用日志详情" :description="`ID: ${log.id}`">
      <template #actions>
        <StatusTag :status="log.status" />
      </template>
    </PageHeader>

    <div class="card-base" style="margin-bottom: 16px;">
      <el-descriptions :column="3" border>
        <el-descriptions-item label="时间">{{ formatDateTime(log.ts) }}</el-descriptions-item>
        <el-descriptions-item label="耗时">{{ formatDuration(log.duration_ms) }}</el-descriptions-item>
        <el-descriptions-item label="HTTP">{{ log.http_status ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="服务 ID">{{ log.service_id }}</el-descriptions-item>
        <el-descriptions-item label="工具">{{ log.tool_name ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="API Key ID">{{ log.api_key_id ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="Application ID">{{ log.application_id ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="客户端 IP">{{ log.client_ip ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="请求 ID">{{ log.request_id ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="请求 bytes">{{ log.request_bytes ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="响应 bytes">{{ log.response_bytes ?? '—' }}</el-descriptions-item>
        <el-descriptions-item v-if="log.error_code" label="错误码">{{ log.error_code }}</el-descriptions-item>
        <el-descriptions-item v-if="log.error_message" label="错误消息" :span="3">
          <span class="mono" style="color: var(--color-error);">{{ log.error_message }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <div class="card-base" style="margin-bottom: 16px;">
      <h3 style="margin-bottom: 12px;">请求 body</h3>
      <pre v-if="requestPretty !== null" class="json-block">{{ requestPretty }}</pre>
      <el-empty v-else description="body 已清理（30 天保留期）或本次调用未携带 body" :image-size="60" />
    </div>

    <div class="card-base">
      <h3 style="margin-bottom: 12px;">响应 body</h3>
      <pre v-if="responsePretty !== null" class="json-block">{{ responsePretty }}</pre>
      <el-empty v-else description="body 已清理（30 天保留期）或本次调用未返回 body" :image-size="60" />
    </div>
  </div>

  <el-empty v-else-if="!loading" description="未找到该调用日志" />
</template>

<style scoped>
.json-block {
  background: var(--color-gray-50);
  padding: var(--space-3);
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 12px;
  white-space: pre;
  overflow-x: auto;
  max-height: 480px;
  overflow-y: auto;
  margin: 0;
}
</style>
