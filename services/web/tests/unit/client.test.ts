import { describe, it, expect, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import MockAdapter from 'axios-mock-adapter';
import { client, formatDetail } from '@/api/client';
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

describe('formatDetail', () => {
  it('returns string detail as-is', () => {
    expect(formatDetail('boom')).toBe('boom');
  });

  it('returns empty for undefined or non-array non-string', () => {
    expect(formatDetail(undefined)).toBe('');
  });

  it('formats single FastAPI 422 item with body-prefixed loc', () => {
    expect(
      formatDetail([
        {
          type: 'string_too_short',
          loc: ['body', 'password'],
          msg: 'String should have at least 8 characters',
        },
      ]),
    ).toBe('password: String should have at least 8 characters');
  });

  it('joins multiple items with ；and drops body prefix', () => {
    expect(
      formatDetail([
        { loc: ['body', 'username'], msg: 'too short' },
        { loc: ['body', 'password'], msg: 'too short' },
      ]),
    ).toBe('username: too short；password: too short');
  });

  it('falls back to bare msg when loc missing or empty', () => {
    expect(formatDetail([{ msg: 'nope' }])).toBe('nope');
    expect(formatDetail([{ loc: [], msg: 'nope' }])).toBe('nope');
  });
});
