import { vi } from 'vitest';

interface MockStorage {
  store: Record<string, string>;
  getItem(key: string): string | null;
  setItem(key: string, val: string): void;
  removeItem(key: string): void;
  clear(): void;
}

const mockStorage: MockStorage = {
  store: {},
  getItem(key: string) { return this.store[key] ?? null; },
  setItem(key: string, val: string) { this.store[key] = val; },
  removeItem(key: string) { delete this.store[key]; },
  clear() { this.store = {}; },
};

vi.stubGlobal('localStorage', mockStorage);
