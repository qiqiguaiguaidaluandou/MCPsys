<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { listUsers, createUser, deleteUser, type CreateUserPayload } from '@/api/users';
import type { User, Role, UserStatus } from '@/api/types';
import { useAuthStore } from '@/stores/auth';
import PageHeader from '@/components/common/PageHeader.vue';
import DataTable from '@/components/common/DataTable.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import Icon from '@/components/icons/Icon.vue';
import { ROLE_LABELS } from '@/utils/constants';
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus';

const auth = useAuthStore();
const items = ref<User[]>([]);
const loading = ref(false);

const formRef = ref<FormInstance>();
const newDialog = reactive<{
  visible: boolean;
  submitting: boolean;
  form: { username: string; password: string; role: Role; status: UserStatus };
}>({
  visible: false,
  submitting: false,
  form: { username: '', password: '', role: 'viewer', status: 'active' },
});

const rules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 64, message: '用户名长度需在 3–64 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入初始密码', trigger: 'blur' },
    { min: 8, max: 128, message: '密码长度需在 8–128 个字符', trigger: 'blur' },
  ],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
};

async function load() {
  loading.value = true;
  try {
    items.value = (await listUsers()).items;
  } finally {
    loading.value = false;
  }
}

async function onCreate() {
  if (!formRef.value) return;
  try {
    await formRef.value.validate();
  } catch {
    return;
  }
  newDialog.submitting = true;
  try {
    await createUser(newDialog.form as CreateUserPayload);
    ElMessage.success('用户创建成功');
    newDialog.visible = false;
    newDialog.form = { username: '', password: '', role: 'viewer', status: 'active' };
    formRef.value.resetFields();
    await load();
  } finally {
    newDialog.submitting = false;
  }
}

async function onDelete(row: User) {
  try {
    await ElMessageBox.confirm(
      `确认删除用户 ${row.username}？此操作不可撤销。`,
      '删除用户',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      },
    );
  } catch {
    return;
  }
  await deleteUser(row.id);
  ElMessage.success('已删除');
  await load();
}

onMounted(load);
</script>

<template>
  <PageHeader title="用户" description="管理系统中的本地账号">
    <template #actions>
      <el-button type="primary" @click="newDialog.visible = true">
        <Icon name="plus" :size="14" /> 新建用户
      </el-button>
    </template>
  </PageHeader>

  <DataTable :data="items" :loading="loading">
    <el-table-column prop="username" label="用户名" min-width="200">
      <template #default="{ row }: { row: User }">
        <span class="mono">{{ row.username }}</span>
        <el-tag v-if="row.id === auth.user?.id" size="small" effect="plain" style="margin-left: 8px;">我自己</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="角色" width="120">
      <template #default="{ row }: { row: User }">{{ ROLE_LABELS[row.role] ?? row.role }}</template>
    </el-table-column>
    <el-table-column label="状态" width="100">
      <template #default="{ row }: { row: User }"><StatusTag :status="row.status" /></template>
    </el-table-column>
    <el-table-column label="上次登录" width="160">
      <template #default="{ row }: { row: User }"><RelativeTime :value="row.last_login_at" /></template>
    </el-table-column>
    <el-table-column label="创建时间" width="160">
      <template #default="{ row }: { row: User }"><RelativeTime :value="row.created_at" /></template>
    </el-table-column>
    <el-table-column label="操作" width="100" fixed="right">
      <template #default="{ row }: { row: User }">
        <el-button
          link
          type="danger"
          :disabled="row.id === auth.user?.id"
          @click="onDelete(row)"
        >删除</el-button>
      </template>
    </el-table-column>
  </DataTable>

  <el-dialog v-model="newDialog.visible" title="新建用户" width="480">
    <el-form ref="formRef" :model="newDialog.form" :rules="rules" label-position="top">
      <el-form-item label="用户名" prop="username">
        <el-input v-model="newDialog.form.username" autocomplete="off" />
      </el-form-item>
      <el-form-item label="初始密码" prop="password">
        <el-input v-model="newDialog.form.password" type="password" show-password autocomplete="new-password" />
      </el-form-item>
      <el-form-item label="角色" prop="role">
        <el-select v-model="newDialog.form.role" style="width: 100%;">
          <el-option label="管理员（admin）" value="admin" />
          <el-option label="运维（operator）" value="operator" />
          <el-option label="只读（viewer）" value="viewer" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="newDialog.visible = false">取消</el-button>
      <el-button type="primary" :loading="newDialog.submitting" @click="onCreate">创建</el-button>
    </template>
  </el-dialog>
</template>
