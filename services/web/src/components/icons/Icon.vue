<script setup lang="ts">
import * as icons from 'lucide-vue-next';
import { computed } from 'vue';

const props = withDefaults(defineProps<{
  name: string;
  size?: number;
  strokeWidth?: number;
  color?: string;
}>(), {
  size: 16,
  strokeWidth: 2,
  color: 'currentColor',
});

const Component = computed(() => {
  const pascalName = props.name
    .split('-')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join('');
  return (icons as Record<string, unknown>)[pascalName] ?? icons.HelpCircle;
});
</script>

<template>
  <component
    :is="Component"
    :size="size"
    :stroke-width="strokeWidth"
    :color="color"
    style="display: inline-flex; vertical-align: middle;"
  />
</template>
