<script setup lang="ts" generic="T">
import EmptyState from './EmptyState.vue';

defineProps<{
  data: T[];
  loading?: boolean;
  total?: number;
  page?: number;
  pageSize?: number;
  emptyTitle?: string;
}>();

defineEmits<{
  'update:page': [page: number];
  'update:pageSize': [size: number];
}>();
</script>

<template>
  <div class="data-table">
    <el-table
      v-loading="loading"
      :data="data"
      stripe
      :empty-text="''"
      :row-style="{ height: '44px' }"
    >
      <slot />
      <template #empty>
        <EmptyState :title="emptyTitle ?? '暂无数据'" />
      </template>
    </el-table>
    <div v-if="total != null && total > 0" class="data-table__pager">
      <el-pagination
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, sizes, prev, pager, next"
        :page-sizes="[20, 50, 100]"
        @update:current-page="$emit('update:page', $event)"
        @update:page-size="$emit('update:pageSize', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.data-table { background: var(--color-surface); border-radius: var(--radius-base); }
.data-table__pager {
  display: flex;
  justify-content: flex-end;
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--color-gray-200);
}
</style>
