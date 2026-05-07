<script setup lang="ts">
import { ref, computed } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { updateUser } from '@/api/users';
import PageHeader from '@/components/common/PageHeader.vue';
import { ROLE_LABELS } from '@/utils/constants';
import { ElMessage } from 'element-plus';

const auth = useAuthStore();
const oldPassword = ref('');
const newPassword = ref('');
const confirmPassword = ref('');
const saving = ref(false);

const roleLabel = computed(() => {
  const role = auth.user?.role;
  return role ? ROLE_LABELS[role] : '—';
});

async function changePassword() {
  if (!oldPassword.value || !newPassword.value) {
    ElMessage.warning('请输入旧密码和新密码');
    return;
  }
  if (newPassword.value !== confirmPassword.value) {
    ElMessage.warning('两次输入的新密码不一致');
    return;
  }
  if (!auth.user) return;
  saving.value = true;
  try {
    await updateUser(auth.user.id, { password: newPassword.value });
    ElMessage.success('密码修改成功，请重新登录');
    auth.clear();
    location.assign('/login');
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <PageHeader title="个人资料" />

  <div class="card-base" style="max-width: 560px;">
    <el-descriptions :column="1" border>
      <el-descriptions-item label="用户名">{{ auth.user?.username }}</el-descriptions-item>
      <el-descriptions-item label="角色">{{ roleLabel }}</el-descriptions-item>
      <el-descriptions-item label="状态">{{ auth.user?.status }}</el-descriptions-item>
    </el-descriptions>
  </div>

  <div class="card-base" style="max-width: 560px; margin-top: 24px;">
    <h3 style="margin-bottom: 16px;">修改密码</h3>
    <el-form label-position="top">
      <el-form-item label="旧密码">
        <el-input v-model="oldPassword" type="password" show-password autocomplete="current-password" />
      </el-form-item>
      <el-form-item label="新密码">
        <el-input v-model="newPassword" type="password" show-password autocomplete="new-password" />
      </el-form-item>
      <el-form-item label="确认新密码">
        <el-input v-model="confirmPassword" type="password" show-password autocomplete="new-password" />
      </el-form-item>
      <el-button type="primary" :loading="saving" @click="changePassword">修改密码</el-button>
    </el-form>
  </div>
</template>
