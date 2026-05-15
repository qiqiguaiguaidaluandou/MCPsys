<script setup lang="ts">
import { computed } from 'vue';
import Icon from '@/components/icons/Icon.vue';

type Tone = 'primary' | 'success' | 'warning' | 'error' | 'info';

const props = withDefaults(
  defineProps<{
    label: string;
    value: string | number | null | undefined;
    sub?: string;
    icon?: string;          // lucide icon name
    tone?: Tone;
    loading?: boolean;
    formatter?: (v: string | number | null | undefined) => string;
  }>(),
  { tone: 'info', loading: false },
);

const TONE_BG: Record<Tone, string> = {
  primary: 'var(--color-primary-50)',
  success: 'var(--color-success-bg)',
  warning: 'var(--color-warning-bg)',
  error: 'var(--color-error-bg)',
  info: 'var(--color-info-bg)',
};
const TONE_FG: Record<Tone, string> = {
  primary: 'var(--color-primary-500)',
  success: 'var(--color-success)',
  warning: 'var(--color-warning)',
  error: 'var(--color-error)',
  info: 'var(--color-info)',
};

const displayValue = computed(() => {
  if (props.loading) return '—';
  const v = props.value;
  if (v === null || v === undefined || v === '') return '—';
  if (props.formatter) return props.formatter(v);
  return typeof v === 'number' ? v.toLocaleString() : String(v);
});
</script>

<template>
  <div class="kpi-card">
    <div
      v-if="icon"
      class="kpi-card__icon"
      :style="{ background: TONE_BG[tone], color: TONE_FG[tone] }"
    >
      <Icon :name="icon" :size="20" />
    </div>
    <div class="kpi-card__main">
      <div class="kpi-card__label">{{ label }}</div>
      <div class="kpi-card__value" :data-loading="loading || undefined">{{ displayValue }}</div>
      <div v-if="sub" class="kpi-card__sub">{{ sub }}</div>
    </div>
  </div>
</template>

<style scoped>
.kpi-card {
  display: flex;
  gap: var(--space-3);
  background: var(--color-surface);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-base);
  padding: var(--space-5);
}
.kpi-card__icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-base);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.kpi-card__label {
  font-size: var(--text-sm);
  color: var(--color-gray-500);
}
.kpi-card__value {
  font-size: var(--text-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-gray-900);
  line-height: var(--leading-tight);
  margin-top: var(--space-1);
}
.kpi-card__sub {
  font-size: var(--text-xs);
  color: var(--color-gray-400);
  margin-top: var(--space-1);
}
</style>
