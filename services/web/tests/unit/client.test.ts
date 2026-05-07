import { describe, it, expect, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import MockAdapter from 'axios-mock-adapter';
import { client } from '@/api/client';
import { useAuthStore } from '@/stores/auth';

describe('axios client', () => {
  let mock: MockAdapter;

  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    mock = new MockAdapter(client);
  });

  it('attaches Bearer token when set', async () => {
    const auth = useAuthStore();
    auth.token = 'TEST_TOKEN';
    mock.onGet('/api/v1/foo').reply((config) => {
      expect(config.headers?.Authorization).toBe('Bearer TEST_TOKEN');
      return [200, { ok: true }];
    });
    await client.get('/api/v1/foo');
  });

  it('does not attach Authorization when token empty', async () => {
    mock.onGet('/api/v1/foo').reply((config) => {
      expect(config.headers?.Authorization).toBeUndefined();
      return [200, { ok: true }];
    });
    await client.get('/api/v1/foo');
  });

  it('clears token and rejects on 401', async () => {
    const auth = useAuthStore();
    auth.token = 'TOKEN';
    mock.onGet('/api/v1/foo').reply(401);
    await expect(client.get('/api/v1/foo')).rejects.toThrow();
    expect(auth.token).toBe('');
  });
});
