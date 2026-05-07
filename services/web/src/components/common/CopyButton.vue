<script setup lang="ts">
import { useClipboard } from '@vueuse/core';
import { ElMessage } from 'element-plus';
import Icon from '@/components/icons/Icon.vue';

const props = defineProps<{
  text: string;
  size?: 'small' | 'default';
}>();

const { copy, copied } = useClipboard({ source: () => props.text, legacy: true });

async function handleCopy() {
  try {
    await copy(props.text);
    if (copied.value) {
      ElMessage.success('已复制');
    } else {
      ElMessage.warning('复制失败，请手动选中文本复制');
    }
  } catch {
    ElMessage.warning('复制失败，请手动选中文本复制');
  }
}
</script>

<template>
  <el-button :size="size ?? 'small'" link @click="handleCopy">
    <Icon name="copy" :size="14" />
  </el-button>
</template>
