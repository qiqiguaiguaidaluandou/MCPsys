<script setup lang="ts">
import { ref, onMounted, computed, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { listServices, createService, type McpService } from '@/api/services';
import { useAuthStore } from '@/stores/auth';
import PageHeader from '@/components/common/PageHeader.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import HealthDot from '@/components/feature/HealthDot.vue';
import DataTable from '@/components/common/DataTable.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import Icon from '@/components/icons/Icon.vue';
import { ElMessage } from 'element-plus';

const router = useRouter();
const auth = useAuthStore();

const items = ref<McpService[]>([]);
const loading = ref(false);
const search = ref('');
const filterStatus = ref<string>('');
const filterHealth = ref<string>('');

const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$/;

const newDialog = reactive({
  visible: false,
  submitting: false,
  form: {
    slug: '',
    display_name: '',
    endpoint_url: '',
    description: '',
    owner_team: '',
    rate_limit_qps: null as number | null,
  },
});

function resetForm() {
  newDialog.form = {
    slug: '',
    display_name: '',
    endpoint_url: '',
    description: '',
    owner_team: '',
    rate_limit_qps: null,
  };
}

async function onCreate() {
  const f = newDialog.form;
  if (!f.slug || !f.display_name || !f.endpoint_url) {
    ElMessage.warning('slug、显示名、端点 URL 为必填');
    return;
  }
  if (!SLUG_RE.test(f.slug)) {
    ElMessage.warning('slug 仅允许小写字母、数字与连字符，长度 2-64');
    return;
  }
  newDialog.submitting = true;
  try {
    await createService({
      slug: f.slug,
      display_name: f.display_name,
      endpoint_url: f.endpoint_url,
      description: f.description || undefined,
      owner_team: f.owner_team || undefined,
      rate_limit_qps: f.rate_limit_qps,
    });
    ElMessage.success('服务注册成功');
    newDialog.visible = false;
    resetForm();
    await load();
  } finally {
    newDialog.submitting = false;
  }
}

async function load() {
  loading.value = true;
  try {
    const resp = await listServices();
    items.value = resp.items;
  } finally {
    loading.value = false;
  }
}

const filtered = computed(() => {
  return items.value.filter((s) => {
    if (filterStatus.value && s.status !== filterStatus.value) return false;
    if (filterHealth.value && s.health_status !== filterHealth.value) return false;
    if (search.value) {
      const q = search.value.toLowerCase();
      return (
        s.slug.toLowerCase().includes(q) ||
        s.display_name.toLowerCase().includes(q) ||
        (s.owner_team ?? '').toLowerCase().includes(q)
      );
    }
    return true;
  });
});

onMounted(load);
</script>

<template>
  <PageHeader title="服务目录" description="所有已注册的 MCP 服务">
    <template #actions>
      <el-button v-if="auth.hasRole('admin', 'operator')" type="primary" @click="newDialog.visible = true">
        <Icon name="plus" :size="14" /> 注册新服务
      </el-button>
    </template>
  </PageHeader>

  <div class="filter-bar">
    <el-input v-model="search" placeholder="搜索 slug / 名称 / 团队" style="width: 280px;" clearable>
      <template #prefix><Icon name="search" :size="14" /></template>
    </el-input>
    <el-select v-model="filterStatus" placeholder="状态" clearable style="width: 120px;">
      <el-option label="启用" value="active" />
      <el-option label="禁用" value="disabled" />
    </el-select>
    <el-select v-model="filterHealth" placeholder="健康" clearable style="width: 120px;">
      <el-option label="健康" value="healthy" />
      <el-option label="异常" value="unhealthy" />
      <el-option label="未知" value="unknown" />
    </el-select>
    <div style="flex: 1" />
    <el-button @click="load">
      <Icon name="refresh-cw" :size="14" /> 刷新
    </el-button>
  </div>

  <DataTable :data="filtered" :loading="loading">
    <el-table-column prop="slug" label="Slug" width="200">
      <template #default="{ row }: { row: McpService }">
        <span class="mono"><router-link :to="`/services/${row.slug}`">{{ row.slug }}</router-link></span>
      </template>
    </el-table-column>
    <el-table-column prop="display_name" label="显示名" width="240" />
    <el-table-column prop="owner_team" label="团队" width="120">
      <template #default="{ row }: { row: McpService }">{{ row.owner_team || '—' }}</template>
    </el-table-column>
    <el-table-column label="健康" width="100">
      <template #default="{ row }: { row: McpService }">
        <HealthDot :status="row.health_status" />
      </template>
    </el-table-column>
    <el-table-column label="状态" width="80">
      <template #default="{ row }: { row: McpService }">
        <StatusTag :status="row.status" />
      </template>
    </el-table-column>
    <el-table-column prop="endpoint_url" label="端点" min-width="240" show-overflow-tooltip />
    <el-table-column label="最近检查" width="140">
      <template #default="{ row }: { row: McpService }">
        <RelativeTime :value="row.last_health_check_at" />
      </template>
    </el-table-column>
    <el-table-column label="操作" width="80" fixed="right">
      <template #default="{ row }: { row: McpService }">
        <el-button link type="primary" @click="router.push(`/services/${row.slug}`)">详情</el-button>
      </template>
    </el-table-column>
  </DataTable>

  <el-dialog v-model="newDialog.visible" title="注册新服务" width="520">
    <el-form label-position="top">
      <el-form-item label="Slug" required>
        <el-input v-model="newDialog.form.slug" placeholder="小写字母/数字/连字符，2-64 字符，例如 weather-mcp" />
      </el-form-item>
      <el-form-item label="显示名" required>
        <el-input v-model="newDialog.form.display_name" placeholder="例如：Weather MCP" />
      </el-form-item>
      <el-form-item label="端点 URL" required>
        <el-input v-model="newDialog.form.endpoint_url" placeholder="http://upstream:9000/mcp" />
      </el-form-item>
      <el-form-item label="所属团队">
        <el-input v-model="newDialog.form.owner_team" placeholder="例如：platform" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="newDialog.form.description" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="限流 QPS（可选，留空不限）">
        <el-input-number v-model="newDialog.form.rate_limit_qps" :min="0" :step="1" controls-position="right" style="width: 100%;" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="newDialog.visible = false">取消</el-button>
      <el-button type="primary" :loading="newDialog.submitting" @click="onCreate">创建</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.filter-bar {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-4);
}
</style>
