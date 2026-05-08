import { client } from './client';

export interface Permission {
  id: number;
  application_id: number;
  service_id: number;
  granted_by: number | null;
  granted_at: string;
  note: string | null;
}

export interface PermissionList {
  items: Permission[];
  total: number;
}

export function listServicePermissions(slug: string): Promise<PermissionList> {
  return client.get(`/api/v1/services/${slug}/permissions`).then((r) => r.data);
}

export function grantPermission(
  slug: string,
  application_id: number,
  note?: string,
): Promise<Permission> {
  return client
    .post(`/api/v1/services/${slug}/permissions`, { application_id, note })
    .then((r) => r.data);
}

export function revokePermission(slug: string, application_id: number): Promise<void> {
  return client
    .delete(`/api/v1/services/${slug}/permissions/${application_id}`)
    .then(() => undefined);
}

export function listApplicationPermissions(application_id: number): Promise<PermissionList> {
  return client
    .get(`/api/v1/applications/${application_id}/permissions`)
    .then((r) => r.data);
}
