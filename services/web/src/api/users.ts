import { client } from './client';
import type { PaginatedList, Role, User, UserStatus } from './types';

export function listUsers(): Promise<PaginatedList<User>> {
  return client.get('/api/v1/users').then((r) => r.data);
}

export function getUser(id: number): Promise<User> {
  return client.get(`/api/v1/users/${id}`).then((r) => r.data);
}

export interface CreateUserPayload {
  username: string;
  password: string;
  role: Role;
  status?: UserStatus;
}

export function createUser(payload: CreateUserPayload): Promise<User> {
  return client.post('/api/v1/users', payload).then((r) => r.data);
}

export interface UpdateUserPayload {
  role?: Role;
  status?: UserStatus;
  password?: string;
}

export function updateUser(id: number, payload: UpdateUserPayload): Promise<User> {
  return client.put(`/api/v1/users/${id}`, payload).then((r) => r.data);
}
