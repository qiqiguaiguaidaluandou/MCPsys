import { client } from './client';
import type { PaginatedList } from './types';

export type Transport = 'streamable_http';
export type ServiceStatus = 'active' | 'disabled';
export type HealthStatus = 'healthy' | 'unhealthy' | 'unknown';

export interface McpService {
  id: number;
  slug: string;
  display_name: string;
  description: string | null;
  owner_team: string | null;
  tags: string[] | null;
  endpoint_url: string;
  transport: Transport;
  status: ServiceStatus;
  health_status: HealthStatus;
  rate_limit_qps: number | null;
  last_health_check_at: string | null;
  created_at: string;
  updated_at: string;
}

export function listServices(): Promise<PaginatedList<McpService>> {
  return client.get('/api/v1/services').then((r) => r.data);
}

export function getService(slug: string): Promise<McpService> {
  return client.get(`/api/v1/services/${slug}`).then((r) => r.data);
}

export interface CreateServicePayload {
  slug: string;
  display_name: string;
  endpoint_url: string;
  description?: string;
  owner_team?: string;
  rate_limit_qps?: number | null;
}

export function createService(payload: CreateServicePayload): Promise<McpService> {
  return client.post('/api/v1/services', payload).then((r) => r.data);
}

export interface UpdateServicePayload {
  endpoint_url?: string;
  status?: ServiceStatus;
  rate_limit_qps?: number | null;
  display_name?: string;
  description?: string;
  owner_team?: string;
}

export function updateService(slug: string, payload: UpdateServicePayload): Promise<McpService> {
  return client.patch(`/api/v1/services/${slug}`, payload).then((r) => r.data);
}

export function disableService(slug: string): Promise<void> {
  return client.delete(`/api/v1/services/${slug}`).then(() => undefined);
}
