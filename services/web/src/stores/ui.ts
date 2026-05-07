import { defineStore } from 'pinia';
import { useStorage } from '@vueuse/core';
import { STORAGE_KEY_UI } from '@/utils/constants';

interface UiState {
  sidebarCollapsed: boolean;
}

export const useUiStore = defineStore('ui', () => {
  const state = useStorage<UiState>(STORAGE_KEY_UI, { sidebarCollapsed: false });

  function toggleSidebar(): void {
    state.value.sidebarCollapsed = !state.value.sidebarCollapsed;
  }

  return { state, toggleSidebar };
});
