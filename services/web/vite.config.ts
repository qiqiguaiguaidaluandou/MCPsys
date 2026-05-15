// /dataspace/kqspace/MCPsys/services/web/vite.config.ts
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import AutoImport from 'unplugin-auto-import/vite';
import Components from 'unplugin-vue-components/vite';
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      imports: ['vue', 'vue-router', 'pinia'],
      resolvers: [ElementPlusResolver({ importStyle: 'sass' })],
      dts: 'src/auto-imports.d.ts',
    }),
    Components({
      resolvers: [ElementPlusResolver({ importStyle: 'sass' })],
      dts: 'src/components.d.ts',
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        additionalData: `@use "@/styles/element-overrides.scss" as *;`,
      },
    },
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/api':     { target: 'http://localhost:8088', changeOrigin: true },
      '/mcp':     { target: 'http://localhost:8088', changeOrigin: true },
      '/healthz': { target: 'http://localhost:8088', changeOrigin: true },
    },
  },
  build: {
    sourcemap: false,
    target: 'es2020',
    chunkSizeWarningLimit: 1024,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    server: {
      // element-plus / vue-echarts 这些带 .scss / .css 副作用导入的包必须走
      // Vite transform，否则 Node 原生 ESM 报 "Unknown file extension .scss"。
      deps: { inline: ['element-plus', 'vue-echarts'] },
    },
  },
});
