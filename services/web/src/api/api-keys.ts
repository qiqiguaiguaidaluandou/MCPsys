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
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export function listApiKeys(params?: { owner_type?: OwnerType; owner_id?: number }): Promise<PaginatedList<ApiKey>> {
  return client.get('/api/v1/api-keys', { params }).then((r) => r.data);
}

export interface IssueApiKeyPayload {
  name: string;
  owner_type: OwnerType;
  owner_id: number;
  expires_at?: string;
}

export interface IssueApiKeyResponse extends ApiKey {
  plaintext: string;
}

export function issueApiKey(payload: IssueApiKeyPayload): Promise<IssueApiKeyResponse> {
  return client.post('/api/v1/api-keys', payload).then((r) => r.data);
}

export function revokeApiKey(id: number): Promise<void> {
  return client.delete(`/api/v1/api-keys/${id}`).then(() => undefined);
}

export function deleteApiKeyPermanent(id: number): Promise<void> {
  return client.delete(`/api/v1/api-keys/${id}/permanent`).then(() => undefined);
}
