<script setup lang="ts">
import { ref, reactive } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import type { AxiosError } from 'axios';
import Icon from '@/components/icons/Icon.vue';
import AuthLayout from '@/layouts/AuthLayout.vue';

const { t } = useI18n();
const router = useRouter();
const route = useRoute();
const auth = useAuthStore();

const form = reactive({ username: '', password: '' });
const errorMsg = ref('');
const submitting = ref(false);

async function onSubmit() {
  errorMsg.value = '';
  if (!form.username || !form.password) {
    errorMsg.value = '请输入用户名和密码';
    return;
  }
  submitting.value = true;
  try {
    await auth.login(form.username, form.password);
    const redirect = (route.query.redirect as string) ?? '/';
    router.push(redirect);
    ElMessage.success(`欢迎回来，${auth.user?.username}`);
  } catch (err) {
    const status = (err as AxiosError).response?.status;
    if (status === 401) errorMsg.value = t('auth.login.error.invalid');
    else errorMsg.value = t('auth.login.error.network');
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <AuthLayout>
    <div class="login-card">
      <div class="login-card__brand">
        <Icon name="network" :size="40" color="var(--color-primary-500)" :stroke-width="1.75" />
        <h1>{{ t('app.name') }}</h1>
      </div>

      <el-form @submit.prevent="onSubmit" size="default" label-position="top">
        <el-form-item :label="t('auth.login.username')">
          <el-input v-model="form.username" placeholder="admin" autofocus autocomplete="username" />
        </el-form-item>
        <el-form-item :label="t('auth.login.password')">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            autocomplete="current-password"
            @keyup.enter="onSubmit"
          />
        </el-form-item>
        <p v-if="errorMsg" class="login-card__error">{{ errorMsg }}</p>
        <el-button
          type="primary"
          native-type="submit"
          :loading="submitting"
          style="width: 100%; margin-top: 8px;"
          @click="onSubmit"
        >
          {{ submitting ? t('auth.login.submitting') : t('auth.login.submit') }}
        </el-button>
      </el-form>

      <div class="login-card__footer">{{ t('app.version') }} · 内部使用</div>
    </div>
  </AuthLayout>
</template>

<style scoped>
.login-card {
  width: 480px;
  background: var(--color-surface);
  border-radius: 12px;
  box-shadow: var(--shadow-md);
  padding: var(--space-10);
}
.login-card__brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-8);
}
.login-card__brand h1 {
  font-size: var(--text-2xl);
  font-weight: var(--font-weight-semibold);
}
.login-card__error {
  color: var(--color-error);
  font-size: var(--text-sm);
  margin: var(--space-2) 0;
}
.login-card__footer {
  text-align: center;
  margin-top: var(--space-8);
  color: var(--color-gray-400);
  font-size: var(--text-xs);
}
</style>
