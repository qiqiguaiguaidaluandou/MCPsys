export type Role = 'admin' | 'operator' | 'viewer';

export function hasRole(userRole: Role | null | undefined, allowed: Role[]): boolean {
  if (allowed.length === 0) return true;
  if (!userRole) return false;
  return allowed.includes(userRole);
}
