import axios, { type AxiosError } from 'axios';
import { ElMessage } from 'element-plus';

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

client.interceptors.response.use(
  (resp) => resp,
  async (err: AxiosError<{ detail?: string }>) => {
    const { useAuthStore } = await import('@/stores/auth');
    const auth = useAuthStore();
    const status = err.response?.status;
    const detail = err.response?.data?.detail;
    const msg = typeof detail === 'string' ? detail : '';

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
