import { client } from './client';
import type { PaginatedList } from './types';

export interface AuditEvent {
  id: number;
  ts: string;
  actor_user_id: number | null;
  actor_username: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string | null;
}

export interface AuditEventFilter {
  actor_user_id?: number;
  action?: string;
  target_type?: string;
  target_id?: string;
  from_ts?: string;
  to_ts?: string;
  page?: number;
  page_size?: number;
}

export function listAuditEvents(
  filter?: AuditEventFilter,
): Promise<PaginatedList<AuditEvent>> {
  return client.get('/api/v1/audit-events', { params: filter }).then((r) => r.data);
}
