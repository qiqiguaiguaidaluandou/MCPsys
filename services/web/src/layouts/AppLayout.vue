<script setup lang="ts">
import SideBar from '@/components/nav/SideBar.vue';
import TopBar from '@/components/nav/TopBar.vue';
</script>

<template>
  <div class="app-layout">
    <SideBar />
    <div class="app-layout__main">
      <TopBar />
      <main class="app-layout__content">
        <slot />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}
.app-layout__main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.app-layout__content {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-6) var(--space-8);
  background: var(--color-gray-50);
}
</style>
