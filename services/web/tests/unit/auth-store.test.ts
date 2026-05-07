import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useAuthStore } from '@/stores/auth';
import * as authApi from '@/api/auth';

vi.mock('@/api/auth');

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    vi.resetAllMocks();
  });

  it('login sets token and fetches user', async () => {
    vi.mocked(authApi.login).mockResolvedValue({ access_token: 'T', token_type: 'bearer' });
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: 1, username: 'admin', role: 'admin', status: 'active',
      last_login_at: null, created_at: '2026-05-06T00:00:00Z',
    });

    const auth = useAuthStore();
    await auth.login('admin', 'admin123');

    expect(auth.token).toBe('T');
    expect(auth.user?.username).toBe('admin');
    expect(auth.isAuthenticated).toBe(true);
  });

  it('hasRole respects role list', () => {
    const auth = useAuthStore();
    auth.user = { id: 1, username: 'u', role: 'operator', status: 'active', last_login_at: null, created_at: '' };
    expect(auth.hasRole('admin', 'operator')).toBe(true);
    expect(auth.hasRole('admin')).toBe(false);
  });

  it('clear wipes token and user', () => {
    const auth = useAuthStore();
    auth.token = 'X';
    auth.user = { id: 1, username: 'u', role: 'admin', status: 'active', last_login_at: null, created_at: '' };
    auth.clear();
    expect(auth.token).toBe('');
    expect(auth.user).toBeNull();
  });
});
