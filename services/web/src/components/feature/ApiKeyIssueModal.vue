<script setup lang="ts">
import { ref, reactive, watch } from 'vue';
import { issueApiKey, type OwnerType } from '@/api/api-keys';
import { listApplications, type Application } from '@/api/applications';
import { ElMessage } from 'element-plus';
import Icon from '@/components/icons/Icon.vue';
import CopyButton from '@/components/common/CopyButton.vue';

const props = defineProps<{
  modelValue: boolean;
  defaultApplicationId?: number;
}>();
const emit = defineEmits<{
  'update:modelValue': [v: boolean];
  'issued': [];
}>();

const stage = ref<'form' | 'plaintext'>('form');
const submitting = ref(false);
const apps = ref<Application[]>([]);

const form = reactive<{ name: string; owner_type: OwnerType; owner_id: number | null }>({
  name: '',
  owner_type: 'application',
  owner_id: null,
});

const result = ref<{ plaintext: string; prefix: string } | null>(null);

watch(() => props.modelValue, async (v) => {
  if (v) {
    stage.value = 'form';
    form.name = '';
    form.owner_type = 'application';
    form.owner_id = props.defaultApplicationId ?? null;
    result.value = null;
    apps.value = (await listApplications()).items;
  }
});

async function onSubmit() {
  if (!form.name || !form.owner_id) {
    ElMessage.warning('请填写名称和所属');
    return;
  }
  submitting.value = true;
  try {
    const resp = await issueApiKey({
      name: form.name,
      owner_type: form.owner_type,
      owner_id: form.owner_id,
    });
    result.value = { plaintext: resp.plaintext, prefix: resp.key_prefix };
    stage.value = 'plaintext';
    emit('issued');
  } finally {
    submitting.value = false;
  }
}

function close() {
  result.value = null;
  emit('update:modelValue', false);
}

function selectAll(e: MouseEvent) {
  const node = e.currentTarget as HTMLElement;
  const range = document.createRange();
  range.selectNodeContents(node);
  const sel = window.getSelection();
  if (sel) {
    sel.removeAllRanges();
    sel.addRange(range);
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="stage === 'form' ? '签发新 API Key' : '✓ 签发成功'"
    width="520"
    :close-on-click-modal="false"
    :close-on-press-escape="stage === 'form'"
    :show-close="stage === 'form'"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template v-if="stage === 'form'">
      <el-form label-position="top">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="例如：team-foo prod" />
        </el-form-item>
        <el-form-item label="归属类型">
          <el-radio-group v-model="form.owner_type">
            <el-radio-button value="application">应用</el-radio-button>
            <el-radio-button value="user">用户</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.owner_type === 'application'" label="选择应用" required>
          <el-select v-model="form.owner_id" placeholder="选择应用" style="width: 100%">
            <el-option v-for="a in apps" :key="a.id" :value="a.id" :label="`${a.name} (id=${a.id})`" />
          </el-select>
        </el-form-item>
        <el-form-item v-else label="用户 ID" required>
          <el-input-number v-model="form.owner_id" :min="1" style="width: 200px;" />
        </el-form-item>
      </el-form>
    </template>

    <template v-else>
      <div class="plaintext-warning">
        <Icon name="alert-triangle" :size="20" color="var(--color-warning)" />
        <div>
          <div class="plaintext-warning__title">此密钥只显示这一次</div>
          <div class="plaintext-warning__desc">请立即复制并妥善保存。关闭后无法再次查看，需要重新签发新密钥。</div>
        </div>
      </div>
      <div class="plaintext-box mono" @click="selectAll">
        {{ result?.plaintext }}
      </div>
      <div class="plaintext-actions">
        <span class="plaintext-hint">点击文本框单击全选；如复制按钮失效请手动 Cmd/Ctrl+C</span>
        <CopyButton :text="result?.plaintext ?? ''" size="default" />
      </div>
    </template>

    <template #footer>
      <template v-if="stage === 'form'">
        <el-button @click="emit('update:modelValue', false)">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">签发</el-button>
      </template>
      <template v-else>
        <el-button type="primary" @click="close">我已保存，关闭</el-button>
      </template>
    </template>
  </el-dialog>
</template>

<style scoped>
.plaintext-warning {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-base);
  margin-bottom: var(--space-4);
}
.plaintext-warning__title {
  font-weight: var(--font-weight-semibold);
  color: var(--color-warning);
  margin-bottom: var(--space-1);
}
.plaintext-warning__desc {
  font-size: var(--text-sm);
  color: var(--color-gray-700);
}
.plaintext-box {
  padding: var(--space-3) var(--space-4);
  background: var(--color-gray-50);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-base);
  font-size: var(--text-base);
  line-height: 1.55;
  word-break: break-all;
  user-select: all;
  cursor: text;
  color: var(--color-gray-900);
}
.plaintext-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-top: var(--space-2);
}
.plaintext-hint {
  font-size: var(--text-xs);
  color: var(--color-gray-500);
}
</style>
