<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { listApplications, createApplication, type Application } from '@/api/applications';
import PageHeader from '@/components/common/PageHeader.vue';
import DataTable from '@/components/common/DataTable.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import Icon from '@/components/icons/Icon.vue';
import { ElMessage } from 'element-plus';

const router = useRouter();
const items = ref<Application[]>([]);
const loading = ref(false);

const newDialog = reactive({
  visible: false,
  form: { name: '', team: '', description: '' },
  submitting: false,
});

async function load() {
  loading.value = true;
  try {
    items.value = (await listApplications()).items;
  } finally {
    loading.value = false;
  }
}

async function onCreate() {
  if (!newDialog.form.name) {
    ElMessage.warning('请输入应用名');
    return;
  }
  newDialog.submitting = true;
  try {
    await createApplication({
      name: newDialog.form.name,
      team: newDialog.form.team || undefined,
      description: newDialog.form.description || undefined,
    });
    ElMessage.success('应用创建成功');
    newDialog.visible = false;
    newDialog.form = { name: '', team: '', description: '' };
    await load();
  } finally {
    newDialog.submitting = false;
  }
}

onMounted(load);
</script>

<template>
  <PageHeader title="应用" description="Agent 在系统中的归属主体；一个应用可以拥有多个 API Key">
    <template #actions>
      <el-button type="primary" @click="newDialog.visible = true">
        <Icon name="plus" :size="14" /> 新建应用
      </el-button>
    </template>
  </PageHeader>

  <DataTable :data="items" :loading="loading">
    <el-table-column prop="name" label="应用名" width="220">
      <template #default="{ row }: { row: Application }">
        <router-link :to="`/applications/${row.id}`" class="mono">{{ row.name }}</router-link>
      </template>
    </el-table-column>
    <el-table-column prop="team" label="团队" width="160">
      <template #default="{ row }: { row: Application }">{{ row.team || '—' }}</template>
    </el-table-column>
    <el-table-column prop="owner_user_id" label="创建人 ID" width="120" />
    <el-table-column label="描述" min-width="240" show-overflow-tooltip>
      <template #default="{ row }: { row: Application }">{{ row.description || '—' }}</template>
    </el-table-column>
    <el-table-column label="创建时间" width="160">
      <template #default="{ row }: { row: Application }"><RelativeTime :value="row.created_at" /></template>
    </el-table-column>
    <el-table-column label="操作" width="100" fixed="right">
      <template #default="{ row }: { row: Application }">
        <el-button link type="primary" @click="router.push(`/applications/${row.id}`)">详情</el-button>
      </template>
    </el-table-column>
  </DataTable>

  <el-dialog v-model="newDialog.visible" title="新建应用" width="480">
    <el-form label-position="top">
      <el-form-item label="应用名" required>
        <el-input v-model="newDialog.form.name" placeholder="例如：team-foo-agent" />
      </el-form-item>
      <el-form-item label="所属团队">
        <el-input v-model="newDialog.form.team" placeholder="例如：foo" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="newDialog.form.description" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="newDialog.visible = false">取消</el-button>
      <el-button type="primary" :loading="newDialog.submitting" @click="onCreate">创建</el-button>
    </template>
  </el-dialog>
</template>
