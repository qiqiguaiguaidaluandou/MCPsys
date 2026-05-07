<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  status: 'healthy' | 'unhealthy' | 'unknown';
}>();

const COLOR: Record<string, string> = {
  healthy:   'var(--color-success)',
  unhealthy: 'var(--color-error)',
  unknown:   'var(--color-gray-400)',
};
const LABEL: Record<string, string> = {
  healthy: '健康', unhealthy: '异常', unknown: '未知',
};

const color = computed(() => COLOR[props.status] ?? COLOR.unknown);
const label = computed(() => LABEL[props.status] ?? '未知');
</script>

<template>
  <span class="health-dot" :title="label">
    <span class="health-dot__pulse" :style="{ background: color }" />
    <span>{{ label }}</span>
  </span>
</template>

<style scoped>
.health-dot {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
}
.health-dot__pulse {
  width: 8px; height: 8px;
  border-radius: var(--radius-full);
  display: inline-block;
}
</style>
