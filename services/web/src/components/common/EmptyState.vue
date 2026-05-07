<script setup lang="ts">
import Icon from '@/components/icons/Icon.vue';
withDefaults(defineProps<{
  icon?: string;
  title?: string;
  description?: string;
}>(), {
  icon: 'inbox',
  title: '暂无数据',
  description: '',
});
</script>

<template>
  <div class="empty-state">
    <Icon :name="icon" :size="48" :stroke-width="1.5" color="var(--color-gray-400)" />
    <h3 class="empty-state__title">{{ title }}</h3>
    <p v-if="description" class="empty-state__desc">{{ description }}</p>
    <div class="empty-state__action"><slot /></div>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-12) var(--space-6);
  text-align: center;
}
.empty-state__title {
  margin-top: var(--space-3);
  font-size: var(--text-md);
  color: var(--color-gray-700);
}
.empty-state__desc {
  margin-top: var(--space-1);
  color: var(--color-gray-500);
  font-size: var(--text-sm);
}
.empty-state__action { margin-top: var(--space-4); }
</style>
