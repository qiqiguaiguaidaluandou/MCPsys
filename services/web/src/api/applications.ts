import { client } from './client';
import type { PaginatedList } from './types';

export interface Application {
  id: number;
  name: string;
  team: string | null;
  description: string | null;
  owner_user_id: number;
  created_at?: string;
  // 应用可调用的服务 id 列表，驱动授权白名单
  service_ids: number[];
}

export function listApplications(): Promise<PaginatedList<Application>> {
  return client.get('/api/v1/applications').then((r) => r.data);
}

export function getApplication(id: number): Promise<Application> {
  return client.get(`/api/v1/applications/${id}`).then((r) => r.data);
}

export interface CreateApplicationPayload {
  name: string;
  team?: string;
  description?: string;
  service_ids?: number[];
}

export function createApplication(payload: CreateApplicationPayload): Promise<Application> {
  return client.post('/api/v1/applications', payload).then((r) => r.data);
}

export interface UpdateApplicationPayload {
  name?: string;
  team?: string;
  description?: string;
  // 省略 = 不改授权；给出列表 = 作为新的完整可调用服务集合
  service_ids?: number[];
}

export function updateApplication(
  id: number,
  payload: UpdateApplicationPayload,
): Promise<Application> {
  return client.patch(`/api/v1/applications/${id}`, payload).then((r) => r.data);
}
