import { describe, it, expect } from 'vitest';
import { formatBytes, formatDuration, formatDateTime, formatRelative } from '@/utils/format';

describe('formatBytes', () => {
  it('returns "0 B" for 0', () => {
    expect(formatBytes(0)).toBe('0 B');
  });
  it('formats KB', () => {
    expect(formatBytes(2048)).toBe('2.00 KB');
  });
  it('formats MB', () => {
    expect(formatBytes(1024 * 1024 * 3.5)).toBe('3.50 MB');
  });
});

describe('formatDuration', () => {
  it('shows ms for < 1s', () => {
    expect(formatDuration(450)).toBe('450ms');
  });
  it('shows seconds for >= 1s', () => {
    expect(formatDuration(1500)).toBe('1.50s');
  });
});

describe('formatDateTime', () => {
  it('formats ISO to YYYY-MM-DD HH:mm:ss', () => {
    expect(formatDateTime('2026-05-06T03:14:25Z')).toMatch(/2026-05-0\d \d{2}:14:25/);
  });
});

describe('formatRelative', () => {
  it('returns "刚刚" for now', () => {
    expect(formatRelative(new Date().toISOString())).toMatch(/刚刚|秒前|前/);
  });
});
