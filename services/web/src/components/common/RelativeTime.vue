<script setup lang="ts">
import { formatDateTime, formatRelative } from '@/utils/format';

const props = defineProps<{
  value: string | null | undefined;
}>();
</script>

<template>
  <el-tooltip v-if="props.value" :content="formatDateTime(props.value)" placement="top">
    <span class="text-secondary">{{ formatRelative(props.value) }}</span>
  </el-tooltip>
  <span v-else class="text-tertiary">—</span>
</template>
