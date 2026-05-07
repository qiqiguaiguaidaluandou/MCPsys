<script setup lang="ts">
import { useClipboard } from '@vueuse/core';
import { ElMessage } from 'element-plus';
import Icon from '@/components/icons/Icon.vue';

const props = defineProps<{
  text: string;
  size?: 'small' | 'default';
}>();

const { copy } = useClipboard({ source: () => props.text });

async function handleCopy() {
  await copy(props.text);
  ElMessage.success('已复制');
}
</script>

<template>
  <el-button :size="size ?? 'small'" link @click="handleCopy">
    <Icon name="copy" :size="14" />
  </el-button>
</template>
