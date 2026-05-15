<script setup lang="ts">
import { ref, reactive, watch } from 'vue';
import { issueApiKey } from '@/api/api-keys';
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

const form = reactive<{
  name: string;
  application_id: number | null;
  rate_limit_qps: number | null;
}>({
  name: '',
  application_id: null,
  rate_limit_qps: null,
});

const result = ref<{ plaintext: string; prefix: string } | null>(null);

watch(() => props.modelValue, async (v) => {
  if (v) {
    stage.value = 'form';
    form.name = '';
    form.application_id = props.defaultApplicationId ?? null;
    form.rate_limit_qps = null;
    result.value = null;
    apps.value = (await listApplications()).items;
  }
});

async function onSubmit() {
  if (!form.name || !form.application_id) {
    ElMessage.warning('请填写名称并选择所属应用');
    return;
  }
  submitting.value = true;
  try {
    const resp = await issueApiKey({
      name: form.name,
      application_id: form.application_id,
      rate_limit_qps: form.rate_limit_qps,
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
        <el-form-item label="所属应用" required>
          <el-select
            v-model="form.application_id"
            filterable
            placeholder="选择应用"
            style="width: 100%"
          >
            <el-option v-for="a in apps" :key="a.id" :value="a.id" :label="`${a.name} (id=${a.id})`" />
          </el-select>
          <span class="qps-hint">Key 的可调用服务由所属应用的服务授权决定</span>
        </el-form-item>
        <el-form-item label="QPS 限流">
          <el-input-number
            v-model="form.rate_limit_qps"
            :min="0"
            :controls="false"
            placeholder="不限"
            style="width: 200px;"
          />
          <span class="qps-hint">留空 = 不限；0 = 停用；正整数 = 每秒上限</span>
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
.qps-hint {
  margin-left: var(--space-3);
  font-size: var(--text-xs);
  color: var(--color-gray-500);
}
</style>
