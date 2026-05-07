import type { Role } from './permissions';

export const STORAGE_KEY_TOKEN = 'mcpsys_token';
export const STORAGE_KEY_UI = 'mcpsys_ui';

export const ROLE_LABELS: Record<Role, string> = {
  admin:    '管理员',
  operator: '运维',
  viewer:   '只读',
};

export type StatusLabel =
  | 'active'
  | 'disabled'
  | 'revoked'
  | 'healthy'
  | 'unhealthy'
  | 'unknown';

export const STATUS_LABELS: Record<StatusLabel, string> = {
  active:    '启用',
  disabled:  '禁用',
  revoked:   '已吊销',
  healthy:   '健康',
  unhealthy: '异常',
  unknown:   '未知',
};
