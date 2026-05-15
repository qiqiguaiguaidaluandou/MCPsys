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

// jsdom 没实现 ResizeObserver；vue-echarts 的 autoresize composable 在 mounted
// 钩子里读它。chart 测试已经把 <v-chart> stub 掉了，但保险起见全局填一个空实现，
// 避免任何边缘情况下出 ReferenceError。
class MockResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
vi.stubGlobal('ResizeObserver', MockResizeObserver);
