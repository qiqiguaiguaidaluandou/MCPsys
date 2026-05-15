<script setup lang="ts">
import { RANGE_OPTIONS, type Range } from '@/api/stats';

// 单选分段（15m / 1h / 24h / 7d）；spec §4.3 明确说不是日期 picker。
// 用法：<RangePicker v-model:range="range" />
const model = defineModel<Range>('range', { required: true });
</script>

<template>
  <el-radio-group v-model="model" size="small">
    <el-radio-button
      v-for="opt in RANGE_OPTIONS"
      :key="opt.value"
      :value="opt.value"
    >{{ opt.label }}</el-radio-button>
  </el-radio-group>
</template>
