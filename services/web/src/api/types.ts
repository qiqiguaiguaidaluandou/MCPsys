export type Role = 'admin' | 'operator' | 'viewer';
export type UserStatus = 'active' | 'disabled';

export interface User {
  id: number;
  username: string;
  role: Role;
  status: UserStatus;
  last_login_at: string | null;
  created_at: string;
}

export interface PaginatedList<T> {
  items: T[];
  total: number;
}

export interface ApiErrorItem {
  type?: string;
  loc?: (string | number)[];
  msg: string;
  ctx?: Record<string, unknown>;
  input?: unknown;
}

export interface ApiError {
  detail?: string | ApiErrorItem[];
}
