<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  status: string;
  label?: string;
}>();

const TYPE_MAP: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
  active: 'success', healthy: 'success',
  disabled: 'info',  unknown: 'info',
  unhealthy: 'danger', revoked: 'danger', error: 'danger',
  warning: 'warning',
};

const LABEL_MAP: Record<string, string> = {
  active: '启用', disabled: '禁用',
  healthy: '健康', unhealthy: '异常', unknown: '未知',
  revoked: '已吊销', error: '错误', success: '成功',
};

const tagType = computed(() => TYPE_MAP[props.status] ?? 'info');
const tagLabel = computed(() => props.label ?? LABEL_MAP[props.status] ?? props.status);
</script>

<template>
  <el-tag :type="tagType" size="small" effect="light">{{ tagLabel }}</el-tag>
</template>
