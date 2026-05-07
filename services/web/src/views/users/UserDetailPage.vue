<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getUser, updateUser } from '@/api/users';
import type { User, Role, UserStatus } from '@/api/types';
import { useAuthStore } from '@/stores/auth';
import PageHeader from '@/components/common/PageHeader.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import Icon from '@/components/icons/Icon.vue';
import { ROLE_LABELS } from '@/utils/constants';
import { ElMessage } from 'element-plus';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const user = ref<User | null>(null);
const editRole = ref<Role>('viewer');
const editStatus = ref<UserStatus>('active');
const newPassword = ref('');
const saving = ref(false);

async function load() {
  user.value = await getUser(Number(route.params.id));
  editRole.value = user.value.role;
  editStatus.value = user.value.status;
}

const isSelf = () => user.value?.id === auth.user?.id;

async function onSave() {
  if (!user.value) return;
  if (isSelf()) {
    ElMessage.warning('不能修改自己的角色或状态');
    return;
  }
  saving.value = true;
  try {
    await updateUser(user.value.id, {
      role: editRole.value,
      status: editStatus.value,
      password: newPassword.value || undefined,
    });
    ElMessage.success('已保存');
    newPassword.value = '';
    await load();
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <el-button link @click="router.back()" style="margin-bottom: 12px;">
    <Icon name="chevron-left" :size="14" /> 返回
  </el-button>
  <div v-if="user">
    <PageHeader :title="user.username" :description="`用户 ID: ${user.id}`">
      <template #actions>
        <StatusTag :status="user.status" />
      </template>
    </PageHeader>

    <div class="card-base" style="max-width: 560px;">
      <el-form label-position="top">
        <el-form-item label="角色">
          <el-select v-model="editRole" :disabled="isSelf()" style="width: 100%;">
            <el-option v-for="r in (['admin','operator','viewer'] as const)" :key="r" :value="r" :label="ROLE_LABELS[r]" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editStatus" :disabled="isSelf()" style="width: 100%;">
            <el-option label="启用" value="active" />
            <el-option label="禁用" value="disabled" />
          </el-select>
        </el-form-item>
        <el-form-item label="重置密码（留空不修改）">
          <el-input v-model="newPassword" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="上次登录">
          <RelativeTime :value="user.last_login_at" />
        </el-form-item>
        <el-form-item>
          <el-button v-if="isSelf()" disabled>不能修改自己</el-button>
          <el-button v-else type="primary" :loading="saving" @click="onSave">保存</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>
