import { describe, it, expect, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import MockAdapter from 'axios-mock-adapter';
import { client } from '@/api/client';
import { getApiKey } from '@/api/api-keys';

describe('getApiKey', () => {
  let mock: MockAdapter;

  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    mock = new MockAdapter(client);
  });

  it('GETs /api/v1/api-keys/:id and returns body', async () => {
    mock.onGet('/api/v1/api-keys/42').reply(200, {
      id: 42,
      key_prefix: 'mcpk_abc',
      name: 'k',
      owner_type: 'application',
      owner_id: 7,
      scopes: null,
      rate_limit_qps: null,
      expires_at: null,
      last_used_at: null,
      revoked_at: null,
      created_at: '2026-05-18T00:00:00Z',
    });
    const res = await getApiKey(42);
    expect(res.id).toBe(42);
    expect(res.owner_id).toBe(7);
    expect(res.owner_type).toBe('application');
  });

  it('propagates 404 as rejected promise', async () => {
    mock.onGet('/api/v1/api-keys/9999').reply(404, { detail: 'api key not found' });
    await expect(getApiKey(9999)).rejects.toThrow();
  });
});
