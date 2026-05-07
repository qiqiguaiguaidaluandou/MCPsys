import { defineStore } from 'pinia';
import { useStorage } from '@vueuse/core';
import { computed, ref } from 'vue';
import { login as apiLogin, getMe } from '@/api/auth';
import { STORAGE_KEY_TOKEN } from '@/utils/constants';
import type { Role, User } from '@/api/types';

export const useAuthStore = defineStore('auth', () => {
  const token = useStorage<string>(STORAGE_KEY_TOKEN, '');
  const user = ref<User | null>(null);
  const loading = ref(false);

  const isAuthenticated = computed(() => !!token.value);

  function hasRole(...roles: Role[]): boolean {
    if (roles.length === 0) return true;
    if (!user.value) return false;
    return roles.includes(user.value.role);
  }

  async function login(username: string, password: string): Promise<void> {
    loading.value = true;
    try {
      const resp = await apiLogin(username, password);
      token.value = resp.access_token;
      user.value = await getMe();
    } finally {
      loading.value = false;
    }
  }

  async function fetchMe(): Promise<void> {
    if (!token.value) return;
    user.value = await getMe();
  }

  function clear(): void {
    token.value = '';
    user.value = null;
  }

  return { token, user, loading, isAuthenticated, hasRole, login, fetchMe, clear };
});
