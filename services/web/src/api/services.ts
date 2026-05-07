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
  last_health_check_at: string | null;
  created_at: string;
  updated_at: string;
}

export function listServices(): Promise<PaginatedList<McpService>> {
  return client.get('/api/v1/services').then((r) => r.data);
}

export function getService(id: number): Promise<McpService> {
  return client.get(`/api/v1/services/${id}`).then((r) => r.data);
}

export interface CreateServicePayload {
  slug: string;
  display_name: string;
  endpoint_url: string;
  description?: string;
  owner_team?: string;
}

export function createService(payload: CreateServicePayload): Promise<McpService> {
  return client.post('/api/v1/services', payload).then((r) => r.data);
}

export function disableService(id: number): Promise<void> {
  return client.delete(`/api/v1/services/${id}`).then(() => undefined);
}
