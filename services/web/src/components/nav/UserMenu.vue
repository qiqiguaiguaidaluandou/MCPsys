<script setup lang="ts">
import { computed } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { useRouter } from 'vue-router';
import { ROLE_LABELS } from '@/utils/constants';
import Icon from '@/components/icons/Icon.vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();

const roleLabel = computed(() => {
  const role = auth.user?.role;
  return role ? ROLE_LABELS[role] : '';
});

function handleCommand(cmd: string) {
  if (cmd === 'profile') router.push({ name: 'Profile' });
  if (cmd === 'logout') {
    auth.clear();
    router.push({ name: 'Login' });
  }
}
</script>

<template>
  <el-dropdown trigger="click" @command="handleCommand">
    <span class="user-menu">
      <span class="user-menu__avatar">
        <Icon name="user" :size="14" />
      </span>
      <span class="user-menu__name">{{ auth.user?.username }}</span>
      <el-tag size="small" type="info" effect="plain">
        {{ roleLabel }}
      </el-tag>
      <Icon name="chevron-down" :size="14" />
    </span>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item command="profile">
          <Icon name="user-circle" :size="14" /> {{ t('nav.profile') }}
        </el-dropdown-item>
        <el-dropdown-item divided command="logout">
          <Icon name="log-out" :size="14" /> {{ t('auth.logout') }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style scoped>
.user-menu {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-base);
  transition: var(--transition-base);
}
.user-menu:hover { background: var(--color-gray-100); }
.user-menu__avatar {
  width: 28px; height: 28px;
  border-radius: var(--radius-full);
  background: var(--color-primary-100);
  color: var(--color-primary-600);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.user-menu__name {
  font-size: var(--text-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-gray-700);
}
</style>
