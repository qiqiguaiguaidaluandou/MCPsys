import { client } from './client';
import type { PaginatedList } from './types';

export interface Application {
  id: number;
  name: string;
  team: string | null;
  description: string | null;
  owner_user_id: number;
  created_at?: string;
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
}

export function createApplication(payload: CreateApplicationPayload): Promise<Application> {
  return client.post('/api/v1/applications', payload).then((r) => r.data);
}
