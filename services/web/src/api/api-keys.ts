import { client } from './client';
import type { PaginatedList } from './types';

export type OwnerType = 'user' | 'application';

export interface ApiKey {
  id: number;
  key_prefix: string;
  name: string;
  owner_type: OwnerType;
  owner_id: number;
  scopes: Record<string, unknown> | null;
  rate_limit_qps: number | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export function listApiKeys(params?: { owner_type?: OwnerType; owner_id?: number }): Promise<PaginatedList<ApiKey>> {
  return client.get('/api/v1/api-keys', { params }).then((r) => r.data);
}

export function getApiKey(id: number): Promise<ApiKey> {
  return client.get(`/api/v1/api-keys/${id}`).then((r) => r.data);
}

export interface IssueApiKeyPayload {
  name: string;
  // Key 永远归属某个应用
  application_id: number;
  expires_at?: string;
  rate_limit_qps?: number | null;
}

export interface IssueApiKeyResponse extends ApiKey {
  plaintext: string;
}

export function issueApiKey(payload: IssueApiKeyPayload): Promise<IssueApiKeyResponse> {
  return client.post('/api/v1/api-keys', payload).then((r) => r.data);
}

export interface UpdateApiKeyPayload {
  rate_limit_qps?: number | null;
}

export function updateApiKey(id: number, payload: UpdateApiKeyPayload): Promise<ApiKey> {
  return client.patch(`/api/v1/api-keys/${id}`, payload).then((r) => r.data);
}

export function revokeApiKey(id: number): Promise<void> {
  return client.delete(`/api/v1/api-keys/${id}`).then(() => undefined);
}

export function deleteApiKeyPermanent(id: number): Promise<void> {
  return client.delete(`/api/v1/api-keys/${id}/permanent`).then(() => undefined);
}
