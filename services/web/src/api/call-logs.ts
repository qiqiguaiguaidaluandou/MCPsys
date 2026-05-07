import { client } from './client';
import type { PaginatedList } from './types';

export type CallStatus = 'success' | 'error' | 'timeout';

export interface CallLog {
  id: string;
  ts: string;
  api_key_id: number | null;
  application_id: number | null;
  user_id: number | null;
  service_id: number;
  service_slug?: string;
  service_version: string | null;
  tool_name: string | null;
  request_id: string | null;
  status: CallStatus;
  http_status: number | null;
  error_code: string | null;
  error_message: string | null;
  duration_ms: number;
  request_bytes: number;
  response_bytes: number;
  client_ip: string | null;
}

export interface CallLogQuery {
  service_id?: number;
  status?: CallStatus;
  api_key_id?: number;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}

export function queryCallLogs(params: CallLogQuery): Promise<PaginatedList<CallLog>> {
  return client.get('/api/v1/call-logs', { params }).then((r) => r.data);
}
