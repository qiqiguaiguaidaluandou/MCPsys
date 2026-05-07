<script setup lang="ts">
import { useRouter } from 'vue-router';
import EmptyState from '@/components/common/EmptyState.vue';
import { useI18n } from 'vue-i18n';
const { t } = useI18n();
const router = useRouter();
</script>

<template>
  <div style="padding: 80px 24px;">
    <EmptyState icon="search-x" :title="t('error.notFound.title')" :description="t('error.notFound.description')">
      <el-button type="primary" @click="router.push('/')">回到首页</el-button>
    </EmptyState>
  </div>
</template>
