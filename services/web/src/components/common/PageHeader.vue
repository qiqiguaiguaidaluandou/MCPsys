<script setup lang="ts">
defineProps<{
  title: string;
  description?: string;
}>();
</script>

<template>
  <div class="page-header">
    <div class="page-header__main">
      <h1 class="page-header__title">{{ title }}</h1>
      <p v-if="description" class="page-header__desc">{{ description }}</p>
    </div>
    <div class="page-header__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  padding: var(--space-6) 0 var(--space-4);
  border-bottom: 1px solid var(--color-gray-200);
  margin-bottom: var(--space-6);
}
.page-header__title {
  font-size: var(--text-xl);
  font-weight: var(--font-weight-semibold);
}
.page-header__desc {
  margin-top: var(--space-1);
  color: var(--color-gray-500);
  font-size: var(--text-sm);
}
.page-header__actions {
  display: flex;
  gap: var(--space-2);
}
</style>
