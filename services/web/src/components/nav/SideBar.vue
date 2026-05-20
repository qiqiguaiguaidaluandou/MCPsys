<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useUiStore } from '@/stores/ui';
import { useAuthStore } from '@/stores/auth';
import Icon from '@/components/icons/Icon.vue';
import { useI18n } from 'vue-i18n';
import type { Role } from '@/api/types';

const { t } = useI18n();
const ui = useUiStore();
const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

interface MenuItem {
  key: string;
  routeName?: string;
  icon: string;
  labelKey: string;
  roles?: Role[];
  children?: MenuItem[];
  disabled?: boolean;
}

const menu = computed<MenuItem[]>(() => [
  { key: 'dashboard', routeName: 'Dashboard', icon: 'layout-dashboard', labelKey: 'nav.dashboard' },
  {
    key: 'services-group', icon: 'boxes', labelKey: 'nav.services',
    children: [
      { key: 'service-list', routeName: 'ServiceList', icon: 'box', labelKey: 'nav.serviceList' },
      { key: 'call-logs', routeName: 'CallLogList', icon: 'scroll-text', labelKey: 'nav.callLogs', roles: ['admin', 'operator'] },
    ],
  },
  {
    key: 'onboarding-group', icon: 'plug', labelKey: 'nav.onboarding', roles: ['admin', 'operator'],
    children: [
      { key: 'apps', routeName: 'ApplicationList', icon: 'package', labelKey: 'nav.applications' },
      { key: 'keys', routeName: 'ApiKeyList', icon: 'key-round', labelKey: 'nav.apiKeys' },
    ],
  },
  {
    key: 'system-group', icon: 'settings', labelKey: 'nav.system', roles: ['admin'],
    children: [
      { key: 'users', routeName: 'UserList', icon: 'users', labelKey: 'nav.users' },
      { key: 'audit', routeName: 'AuditEventList', icon: 'clipboard-list', labelKey: 'nav.audit' },
    ],
  },
  {
    key: 'upcoming-group', icon: 'sparkles', labelKey: 'nav.upcoming',
    children: [
      { key: 'permissions', icon: 'shield', labelKey: 'nav.permissions', disabled: true },
      { key: 'config',      icon: 'sliders', labelKey: 'nav.config',      disabled: true },
    ],
  },
]);

const visibleMenu = computed(() =>
  menu.value
    .filter((g) => !g.roles || auth.hasRole(...g.roles))
    .map((g) => ({
      ...g,
      children: g.children?.filter((c) => !c.roles || auth.hasRole(...c.roles)),
    })),
);

const activeKey = computed(() => route.name as string);

function go(item: MenuItem) {
  if (item.disabled || !item.routeName) return;
  router.push({ name: item.routeName });
}
</script>

<template>
  <aside class="sidebar" :class="{ 'sidebar--collapsed': ui.state.sidebarCollapsed }">
    <div class="sidebar__brand">
      <Icon name="network" :size="22" color="var(--color-primary-500)" />
      <span v-if="!ui.state.sidebarCollapsed" class="sidebar__brand-text">MCPsys</span>
    </div>

    <nav class="sidebar__nav">
      <template v-for="group in visibleMenu" :key="group.key">
        <div v-if="group.children" class="sidebar__group">
          <div v-if="!ui.state.sidebarCollapsed" class="sidebar__group-title">
            {{ t(group.labelKey) }}
          </div>
          <button
            v-for="child in group.children"
            :key="child.key"
            class="sidebar__item"
            :class="{
              'sidebar__item--active': activeKey === child.routeName,
              'sidebar__item--disabled': child.disabled,
            }"
            :disabled="child.disabled"
            @click="go(child)"
          >
            <Icon :name="child.icon" :size="18" />
            <span v-if="!ui.state.sidebarCollapsed">{{ t(child.labelKey) }}</span>
          </button>
        </div>
        <button
          v-else
          class="sidebar__item sidebar__item--top"
          :class="{ 'sidebar__item--active': activeKey === group.routeName }"
          @click="go(group)"
        >
          <Icon :name="group.icon" :size="18" />
          <span v-if="!ui.state.sidebarCollapsed">{{ t(group.labelKey) }}</span>
        </button>
      </template>
    </nav>
  </aside>
</template>

<style scoped>
.sidebar {
  width: var(--layout-sidebar-width);
  background: var(--color-surface);
  border-right: 1px solid var(--color-gray-200);
  display: flex;
  flex-direction: column;
  transition: width 200ms ease;
  flex-shrink: 0;
}
.sidebar--collapsed { width: var(--layout-sidebar-width-collapsed); }
.sidebar__brand {
  height: var(--layout-topbar-height);
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0 var(--space-5);
  border-bottom: 1px solid var(--color-gray-200);
}
.sidebar__brand-text {
  font-size: var(--text-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-gray-900);
}
.sidebar__nav { flex: 1; padding: var(--space-3) var(--space-2); overflow-y: auto; }
.sidebar__group { margin-bottom: var(--space-3); }
.sidebar__group-title {
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-gray-400);
  font-weight: var(--font-weight-medium);
}
.sidebar__item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: none;
  cursor: pointer;
  border-radius: var(--radius-base);
  font-size: var(--text-sm);
  color: var(--color-gray-700);
  text-align: left;
  transition: var(--transition-base);
}
.sidebar__item:hover:not(:disabled) {
  background: var(--color-gray-100);
  color: var(--color-gray-900);
}
.sidebar__item--active {
  background: var(--color-primary-50);
  color: var(--color-primary-600);
  font-weight: var(--font-weight-medium);
}
.sidebar__item--disabled {
  color: var(--color-gray-400);
  cursor: not-allowed;
}
.sidebar__item--top { margin-bottom: var(--space-1); }
</style>
