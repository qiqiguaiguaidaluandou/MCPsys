import type { Router } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

export function setupGuards(router: Router): void {
  router.beforeEach(async (to) => {
    const auth = useAuthStore();

    if (to.meta.requiresAuth === false) {
      return true;
    }

    if (!auth.token) {
      return { name: 'Login', query: { redirect: to.fullPath } };
    }

    if (!auth.user) {
      try {
        await auth.fetchMe();
      } catch {
        auth.clear();
        return { name: 'Login', query: { redirect: to.fullPath } };
      }
    }

    if (to.meta.roles && to.meta.roles.length > 0) {
      if (!auth.hasRole(...to.meta.roles)) {
        return { name: 'Forbidden' };
      }
    }

    return true;
  });
}
