import { client } from './client';

/**
 * 授权关系（应用 × 服务白名单）只读视图。
 * 授权的增删统一在应用侧完成（创建应用 / 应用详情页编辑可调用服务），
 * 见 api/applications.ts 的 createApplication / updateApplication。
 */
export interface Permission {
  id: number;
  application_id: number;
  service_id: number;
  granted_by: number | null;
  granted_at: string;
}

export interface PermissionList {
  items: Permission[];
  total: number;
}

/** 某服务被哪些应用授权调用。 */
export function listServicePermissions(slug: string): Promise<PermissionList> {
  return client.get(`/api/v1/services/${slug}/permissions`).then((r) => r.data);
}

/** 某应用可调用哪些服务。 */
export function listApplicationPermissions(application_id: number): Promise<PermissionList> {
  return client
    .get(`/api/v1/applications/${application_id}/permissions`)
    .then((r) => r.data);
}
