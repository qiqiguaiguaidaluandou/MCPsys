import { describe, it, expect } from 'vitest';
import { hasRole, type Role } from '@/utils/permissions';

describe('hasRole', () => {
  it('returns true when user role is in allowed', () => {
    const allowed: Role[] = ['admin', 'operator'];
    expect(hasRole('admin', allowed)).toBe(true);
    expect(hasRole('operator', allowed)).toBe(true);
  });
  it('returns false when user role is not in allowed', () => {
    expect(hasRole('viewer', ['admin', 'operator'])).toBe(false);
  });
  it('returns false for null role', () => {
    expect(hasRole(null, ['admin'])).toBe(false);
  });
  it('returns true for empty allowed list (no restriction)', () => {
    expect(hasRole('viewer', [])).toBe(true);
  });
});
