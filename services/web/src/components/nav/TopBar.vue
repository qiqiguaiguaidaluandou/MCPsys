<script setup lang="ts">
import { useUiStore } from '@/stores/ui';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { computed } from 'vue';
import Icon from '@/components/icons/Icon.vue';
import UserMenu from './UserMenu.vue';

const { t } = useI18n();
const ui = useUiStore();
const route = useRoute();

const pageTitle = computed(() => {
  const key = route.meta.title as string | undefined;
  return key ? t(key) : '';
});
</script>

<template>
  <header class="topbar">
    <button class="topbar__toggle" @click="ui.toggleSidebar">
      <Icon :name="ui.state.sidebarCollapsed ? 'panel-left-open' : 'panel-left-close'" :size="18" />
    </button>
    <h2 class="topbar__title">{{ pageTitle }}</h2>
    <div style="flex: 1" />
    <UserMenu />
  </header>
</template>

<style scoped>
.topbar {
  height: var(--layout-topbar-height);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-gray-200);
  padding: 0 var(--space-5);
  display: flex;
  align-items: center;
  gap: var(--space-4);
}
.topbar__toggle {
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-gray-600);
  padding: var(--space-2);
  border-radius: var(--radius-base);
  display: inline-flex;
  align-items: center;
}
.topbar__toggle:hover { background: var(--color-gray-100); }
.topbar__title {
  font-size: var(--text-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-gray-900);
}
</style>
