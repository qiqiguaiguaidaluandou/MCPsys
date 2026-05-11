import axios, { type AxiosError } from 'axios';
import { ElMessage } from 'element-plus';

import type { ApiError } from './types';

export const client = axios.create({
  baseURL: '/',
  timeout: 15_000,
});

client.interceptors.request.use(async (config) => {
  const { useAuthStore } = await import('@/stores/auth');
  const auth = useAuthStore();
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`;
  }
  return config;
});

export function formatDetail(detail: ApiError['detail']): string {
  if (typeof detail === 'string') return detail;
  if (!Array.isArray(detail)) return '';
  return detail
    .map((item) => {
      const loc = Array.isArray(item.loc) ? item.loc.filter((p) => p !== 'body') : [];
      const field = loc.join('.');
      return field ? `${field}: ${item.msg}` : item.msg;
    })
    .join('；');
}

client.interceptors.response.use(
  (resp) => resp,
  async (err: AxiosError<ApiError>) => {
    const { useAuthStore } = await import('@/stores/auth');
    const auth = useAuthStore();
    const status = err.response?.status;
    const msg = formatDetail(err.response?.data?.detail);

    if (status === 401) {
      auth.clear();
      const { default: router } = await import('@/router');
      const current = router.currentRoute.value;
      if (current.name !== 'Login') {
        router.push({ name: 'Login', query: { redirect: current.fullPath } });
      }
    } else if (status === 403) {
      ElMessage.warning('权限不足');
    } else if (status && status >= 500) {
      ElMessage.error('服务端错误，请稍后重试');
      console.error('[5xx]', err);
    } else if (status && status >= 400 && status !== 404) {
      ElMessage.error(msg || `请求失败 (${status})`);
    } else if (!status) {
      ElMessage.error('网络异常');
    }
    return Promise.reject(err);
  },
);
