import { client } from './client';
import type { User } from './types';

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const params = new URLSearchParams();
  params.append('username', username);
  params.append('password', password);
  const { data } = await client.post<LoginResponse>('/api/v1/auth/login', params, {
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
  });
  return data;
}

export async function getMe(): Promise<User> {
  const { data } = await client.get<User>('/api/v1/auth/me');
  return data;
}
