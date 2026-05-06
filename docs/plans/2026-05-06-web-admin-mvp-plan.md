# Web 管理后台 MVP 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 MCPsys 加一个独立容器化的 Vue 3 + Element Plus 管理后台，覆盖 spec §6 MVP 全部范围，部署在 `services/web/`，通过 nginx 反代到 `http://<host>:8088/`。

**Architecture:** 独立 SPA（Vue 3 + Vite + TypeScript），构建产物用 nginx:alpine 容器服务静态资源，主 nginx 反代 `/` 到该容器。复用现有 `/api/`、`/mcp/`、`/grafana/` 路由，无需调整后端。

**Tech Stack:** Vue 3.4 / Vite 5 / TypeScript / Element Plus 2.7 / Lucide / Pinia / Axios / vue-i18n / SCSS / Vitest

**Spec:** `/dataspace/kqspace/MCPsys/docs/specs/2026-05-06-web-admin-design.md`

---

## 文件结构总览

```
/dataspace/kqspace/MCPsys/services/web/
├── Dockerfile                # T18：multi-stage
├── nginx.conf                # T18：SPA fallback + gzip
├── package.json              # T1
├── pnpm-lock.yaml            # T1（pnpm install 自动生成）
├── tsconfig.json             # T1
├── tsconfig.node.json        # T1
├── vite.config.ts            # T1
├── .eslintrc.cjs             # T1
├── .prettierrc.json          # T1
├── .gitignore                # T1
├── index.html                # T1
├── public/favicon.svg        # T2
├── tests/setup.ts            # T1（Vitest 全局 mock）
├── src/
│   ├── main.ts               # T1
│   ├── App.vue               # T1
│   ├── env.d.ts              # T1
│   ├── styles/
│   │   ├── tokens.scss       # T2
│   │   ├── reset.scss        # T2
│   │   ├── element-overrides.scss  # T2
│   │   └── main.scss         # T2
│   ├── i18n/
│   │   ├── index.ts          # T3
│   │   └── locales/zh-CN.ts  # T3
│   ├── utils/
│   │   ├── format.ts         # T3
│   │   ├── permissions.ts    # T3
│   │   └── constants.ts      # T3
│   ├── api/
│   │   ├── client.ts         # T4
│   │   ├── types.ts          # T4
│   │   ├── auth.ts           # T4
│   │   ├── users.ts          # T16（推迟，与 UserList 一起）
│   │   ├── applications.ts   # T13
│   │   ├── services.ts       # T12
│   │   ├── api-keys.ts       # T14
│   │   └── call-logs.ts      # T15
│   ├── stores/
│   │   ├── auth.ts           # T5
│   │   └── ui.ts             # T5
│   ├── router/
│   │   ├── index.ts          # T6
│   │   └── guards.ts         # T6
│   ├── components/
│   │   ├── icons/Icon.vue    # T7
│   │   ├── common/
│   │   │   ├── PageHeader.vue       # T7
│   │   │   ├── EmptyState.vue       # T7
│   │   │   ├── StatusTag.vue        # T7
│   │   │   ├── RelativeTime.vue     # T7
│   │   │   ├── CopyButton.vue       # T7
│   │   │   └── DataTable.vue        # T7
│   │   ├── nav/
│   │   │   ├── SideBar.vue          # T10
│   │   │   ├── TopBar.vue           # T10
│   │   │   └── UserMenu.vue         # T10
│   │   └── feature/
│   │       ├── ApiKeyIssueModal.vue # T14
│   │       └── HealthDot.vue        # T8
│   ├── layouts/
│   │   ├── AppLayout.vue            # T10
│   │   └── AuthLayout.vue           # T9
│   └── views/
│       ├── login/LoginPage.vue              # T9
│       ├── dashboard/DashboardPage.vue      # T11
│       ├── services/ServiceListPage.vue     # T12
│       ├── services/ServiceDetailPage.vue   # T12
│       ├── applications/ApplicationListPage.vue   # T13
│       ├── applications/ApplicationDetailPage.vue # T13
│       ├── api-keys/ApiKeyListPage.vue      # T14
│       ├── call-logs/CallLogListPage.vue    # T15
│       ├── users/UserListPage.vue           # T16
│       ├── users/UserDetailPage.vue         # T16
│       ├── profile/ProfilePage.vue          # T17
│       └── error/ForbiddenPage.vue          # T17
│       └── error/NotFoundPage.vue           # T17
```

修改：

- `/dataspace/kqspace/MCPsys/compose.yaml` — T19、T20
- `/dataspace/kqspace/MCPsys/nginx/nginx.conf` — T19
- `/dataspace/kqspace/MCPsys/grafana/provisioning/dashboards/mcp-overview.json` — T20
- `/dataspace/kqspace/MCPsys/README.md` — T22
- `/dataspace/kqspace/MCPsys/docs/deployment.md` — T22

---

## 阶段一：脚手架与样式系统（T1–T3）

### Task 1: 创建 Vue 3 + Vite + TypeScript 项目骨架

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/web/package.json`
- Create: `/dataspace/kqspace/MCPsys/services/web/tsconfig.json`
- Create: `/dataspace/kqspace/MCPsys/services/web/tsconfig.node.json`
- Create: `/dataspace/kqspace/MCPsys/services/web/vite.config.ts`
- Create: `/dataspace/kqspace/MCPsys/services/web/.eslintrc.cjs`
- Create: `/dataspace/kqspace/MCPsys/services/web/.prettierrc.json`
- Create: `/dataspace/kqspace/MCPsys/services/web/.gitignore`
- Create: `/dataspace/kqspace/MCPsys/services/web/index.html`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/main.ts`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/App.vue`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/env.d.ts`
- Create: `/dataspace/kqspace/MCPsys/services/web/tests/setup.ts`

- [ ] **Step 1: 创建目录与 package.json**

```bash
mkdir -p /dataspace/kqspace/MCPsys/services/web/{src,tests,public}
cd /dataspace/kqspace/MCPsys/services/web
```

`package.json`:

```json
{
  "name": "@mcpsys/web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0",
    "build": "vue-tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "eslint src --ext .ts,.vue",
    "typecheck": "vue-tsc --noEmit"
  },
  "dependencies": {
    "vue": "^3.4.27",
    "vue-router": "^4.3.0",
    "pinia": "^2.1.7",
    "element-plus": "^2.7.0",
    "lucide-vue-next": "^0.400.0",
    "axios": "^1.7.0",
    "@vueuse/core": "^10.10.0",
    "dayjs": "^1.11.11",
    "vue-i18n": "^9.13.0"
  },
  "devDependencies": {
    "@types/node": "^20.12.0",
    "@vitejs/plugin-vue": "^5.0.4",
    "@vue/eslint-config-typescript": "^13.0.0",
    "@vue/test-utils": "^2.4.6",
    "eslint": "^8.57.0",
    "eslint-plugin-vue": "^9.25.0",
    "jsdom": "^24.0.0",
    "prettier": "^3.2.5",
    "sass": "^1.77.0",
    "typescript": "^5.4.5",
    "unplugin-auto-import": "^0.17.5",
    "unplugin-vue-components": "^0.27.0",
    "vite": "^5.2.0",
    "vitest": "^1.6.0",
    "vue-tsc": "^2.0.16"
  },
  "engines": {
    "node": ">=20"
  },
  "packageManager": "pnpm@9.0.0"
}
```

- [ ] **Step 2: tsconfig.json + tsconfig.node.json**

`tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "jsx": "preserve",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    },
    "types": ["vite/client", "node"]
  },
  "include": ["src/**/*.ts", "src/**/*.tsx", "src/**/*.vue", "tests/**/*.ts"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

`tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "types": ["node"]
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 3: vite.config.ts（含 Element Plus 自动导入 + dev proxy）**

```ts
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
      '/grafana': { target: 'http://localhost:8088', changeOrigin: true },
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
  },
});
```

- [ ] **Step 4: ESLint + Prettier + .gitignore**

`.eslintrc.cjs`:

```js
module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  extends: [
    'plugin:vue/vue3-recommended',
    '@vue/eslint-config-typescript',
    'prettier',
  ],
  rules: {
    'vue/multi-word-component-names': 'off',
    'vue/no-multiple-template-root': 'off',
  },
};
```

`.prettierrc.json`:

```json
{
  "semi": true,
  "singleQuote": true,
  "trailingComma": "all",
  "printWidth": 100,
  "tabWidth": 2,
  "vueIndentScriptAndStyle": true
}
```

`.gitignore`:

```
node_modules
dist
.vscode
.idea
*.local
.DS_Store
src/auto-imports.d.ts
src/components.d.ts
coverage
```

- [ ] **Step 5: index.html + 入口文件**

`index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>MCPsys 管理后台</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

`src/main.ts`（占位，T6/T9 会补全）:

```ts
import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import './styles/main.scss';

const app = createApp(App);
app.use(createPinia());
app.mount('#app');
```

`src/App.vue`（占位）:

```vue
<template>
  <div class="app-root">
    <h1>MCPsys 管理后台 — bootstrap OK</h1>
  </div>
</template>
```

`src/env.d.ts`:

```ts
/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent<object, object, any>;
  export default component;
}
```

`tests/setup.ts`:

```ts
import { vi } from 'vitest';

vi.stubGlobal('localStorage', {
  store: {} as Record<string, string>,
  getItem(key: string) { return this.store[key] ?? null; },
  setItem(key: string, val: string) { this.store[key] = val; },
  removeItem(key: string) { delete this.store[key]; },
  clear() { this.store = {}; },
});
```

- [ ] **Step 6: 安装依赖**

```bash
cd /dataspace/kqspace/MCPsys/services/web
corepack enable
pnpm install
```

期望：`pnpm-lock.yaml` 生成，`node_modules/` 出现，无错误。

- [ ] **Step 7: 验证 dev server 起得来**

```bash
pnpm dev
```

期望：终端打印 `Local: http://localhost:5173/`；浏览器访问该地址，看到"MCPsys 管理后台 — bootstrap OK"。Ctrl+C 停止。

- [ ] **Step 8: 验证 typecheck + build**

```bash
pnpm typecheck
pnpm build
```

期望：两个命令都退出码 0；`dist/` 出现且含 `index.html`。

- [ ] **Step 9: 提交**

```bash
cd /dataspace/kqspace/MCPsys
git add services/web/
git commit -m "feat(web): scaffold vue 3 + vite + ts skeleton"
```

---

### Task 2: 设计 tokens、全局样式、Element Plus 主题覆盖

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/web/src/styles/tokens.scss`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/styles/reset.scss`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/styles/element-overrides.scss`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/styles/main.scss`
- Create: `/dataspace/kqspace/MCPsys/services/web/public/favicon.svg`

- [ ] **Step 1: tokens.scss（暴露 spec §4.1–4.4 的所有 token 为 CSS Variables）**

```scss
// /dataspace/kqspace/MCPsys/services/web/src/styles/tokens.scss

:root {
  // ─── 主色 ──────────────────────────────
  --color-primary-50:  #EFF6FF;
  --color-primary-100: #DBEAFE;
  --color-primary-500: #3B82F6;
  --color-primary-600: #2563EB;
  --color-primary-700: #1D4ED8;

  // ─── 灰阶 ──────────────────────────────
  --color-gray-50:  #F8FAFC;
  --color-gray-100: #F1F5F9;
  --color-gray-200: #E2E8F0;
  --color-gray-300: #CBD5E1;
  --color-gray-400: #94A3B8;
  --color-gray-500: #64748B;
  --color-gray-600: #475569;
  --color-gray-700: #334155;
  --color-gray-800: #1E293B;
  --color-gray-900: #0F172A;

  // ─── 状态色 ────────────────────────────
  --color-success:    #10B981;
  --color-success-bg: #ECFDF5;
  --color-warning:    #F59E0B;
  --color-warning-bg: #FFFBEB;
  --color-error:      #EF4444;
  --color-error-bg:   #FEF2F2;
  --color-info:       #6366F1;
  --color-info-bg:    #EEF2FF;

  // ─── 表面 ──────────────────────────────
  --color-surface:       #FFFFFF;
  --color-surface-hover: #F8FAFC;
  --color-overlay:       rgba(15, 23, 42, 0.5);

  // ─── 字体 ──────────────────────────────
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI",
               "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB",
               system-ui, sans-serif;
  --font-mono: "SF Mono", "JetBrains Mono", "Cascadia Code",
               Monaco, Menlo, Consolas, monospace;

  // ─── 字号 ──────────────────────────────
  --text-xs:   12px;
  --text-sm:   13px;
  --text-base: 14px;
  --text-md:   16px;
  --text-lg:   18px;
  --text-xl:   20px;
  --text-2xl:  24px;
  --text-3xl:  30px;

  --leading-tight:  1.3;
  --leading-snug:   1.5;
  --leading-normal: 1.6;

  --font-weight-regular: 400;
  --font-weight-medium:  500;
  --font-weight-semibold:600;
  --font-weight-bold:    700;

  // ─── 间距（4px 基础栅格） ──────────────
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;

  // ─── 圆角 ──────────────────────────────
  --radius-sm:   4px;
  --radius-base: 6px;
  --radius-md:   8px;
  --radius-full: 9999px;

  // ─── 阴影 ──────────────────────────────
  --shadow-xs: 0 1px 2px rgba(15, 23, 42, 0.04);
  --shadow-sm: 0 2px 4px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04);
  --shadow-md: 0 4px 8px rgba(15, 23, 42, 0.08), 0 2px 4px rgba(15, 23, 42, 0.05);
  --shadow-lg: 0 12px 24px rgba(15, 23, 42, 0.10), 0 4px 8px rgba(15, 23, 42, 0.06);

  // ─── 布局尺寸 ───────────────────────────
  --layout-sidebar-width:           240px;
  --layout-sidebar-width-collapsed: 64px;
  --layout-topbar-height:           56px;

  // ─── 过渡 ──────────────────────────────
  --transition-base: all 150ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-slow: all 250ms cubic-bezier(0.4, 0, 0.2, 1);
}
```

- [ ] **Step 2: reset.scss（盒模型、基础排版、滚动条）**

```scss
// /dataspace/kqspace/MCPsys/services/web/src/styles/reset.scss

*, *::before, *::after { box-sizing: border-box; }

html, body, #app {
  height: 100%;
  margin: 0;
  padding: 0;
}

body {
  font-family: var(--font-sans);
  font-size: var(--text-base);
  line-height: var(--leading-normal);
  color: var(--color-gray-700);
  background-color: var(--color-gray-50);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

h1, h2, h3, h4, h5, h6 {
  margin: 0;
  font-weight: var(--font-weight-semibold);
  color: var(--color-gray-900);
  line-height: var(--leading-tight);
}

p { margin: 0; }

a {
  color: var(--color-primary-500);
  text-decoration: none;
  transition: var(--transition-base);
  &:hover { color: var(--color-primary-600); }
}

button { font-family: inherit; }

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: var(--color-gray-300);
  border-radius: 4px;
  &:hover { background: var(--color-gray-400); }
}

code, pre, .mono { font-family: var(--font-mono); }
```

- [ ] **Step 3: element-overrides.scss（覆盖 Element Plus 主色 / 圆角 / 字号）**

```scss
// /dataspace/kqspace/MCPsys/services/web/src/styles/element-overrides.scss

@forward 'element-plus/theme-chalk/src/common/var.scss' with (
  $colors: (
    'primary': ('base': #3B82F6),
    'success': ('base': #10B981),
    'warning': ('base': #F59E0B),
    'danger':  ('base': #EF4444),
    'info':    ('base': #6366F1),
  ),
  $border-radius: (
    'base':  6px,
    'small': 4px,
    'round': 9999px,
  ),
  $font-size: (
    'extra-large': 20px,
    'large':       18px,
    'medium':      16px,
    'base':        14px,
    'small':       13px,
    'extra-small': 12px,
  ),
);
```

- [ ] **Step 4: main.scss（汇总 + Element Plus 全量 + 自定义工具类）**

```scss
// /dataspace/kqspace/MCPsys/services/web/src/styles/main.scss

@use './tokens';
@use './reset';
@use 'element-plus/theme-chalk/src/index' as *;

// 工具类
.text-secondary { color: var(--color-gray-500); }
.text-tertiary  { color: var(--color-gray-400); }
.mono           { font-family: var(--font-mono); }

.flex-row    { display: flex; flex-direction: row; align-items: center; gap: var(--space-2); }
.flex-col    { display: flex; flex-direction: column; gap: var(--space-2); }
.flex-grow   { flex: 1 1 auto; }

.card-base {
  background: var(--color-surface);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-base);
  padding: var(--space-5);
}

// Element Plus 微调
.el-button {
  font-weight: var(--font-weight-medium);
}
.el-table {
  --el-table-border-color: var(--color-gray-200);
  --el-table-row-hover-bg-color: var(--color-gray-50);
}
.el-card {
  border-radius: var(--radius-base);
  border-color: var(--color-gray-200);
}
```

- [ ] **Step 5: 简易 favicon.svg（Lucide network 图标，主色蓝）**

```xml
<!-- /dataspace/kqspace/MCPsys/services/web/public/favicon.svg -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="#3B82F6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="16" y="16" width="6" height="6" rx="1"/>
  <rect x="2" y="16" width="6" height="6" rx="1"/>
  <rect x="9" y="2" width="6" height="6" rx="1"/>
  <path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3"/>
  <path d="M12 12V8"/>
</svg>
```

- [ ] **Step 6: App.vue 升级，验证主色生效**

```vue
<!-- /dataspace/kqspace/MCPsys/services/web/src/App.vue -->
<template>
  <div style="padding: 24px;">
    <h1 style="margin-bottom: 16px;">MCPsys 管理后台</h1>
    <el-button type="primary">主色按钮</el-button>
    <el-button type="success">成功</el-button>
    <el-button type="warning">警告</el-button>
    <el-button type="danger">错误</el-button>
    <el-button type="info">信息</el-button>
  </div>
</template>
```

- [ ] **Step 7: 验证 dev 视觉**

```bash
pnpm dev
```

打开 http://localhost:5173，**验证**：
1. "主色按钮" 是 `#3B82F6`（明亮蓝），不是 Element Plus 默认的紫色
2. "成功" 按钮是绿色 `#10B981`
3. 整页背景是淡灰 `#F8FAFC`（不是纯白）
4. 字体是 PingFang SC / 微软雅黑 / 苹方（不是 Times New Roman）

任一不符 → 检查 main.scss 引用顺序、tokens.scss 是否被加载、SCSS 编译是否报错。

- [ ] **Step 8: 提交**

```bash
cd /dataspace/kqspace/MCPsys
git add services/web/src/styles/ services/web/public/ services/web/src/App.vue
git commit -m "feat(web): design tokens, scss base, element-plus theme override"
```

---

### Task 3: i18n 配置 + 工具函数（含单元测试）

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/web/src/i18n/index.ts`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/i18n/locales/zh-CN.ts`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/utils/format.ts`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/utils/permissions.ts`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/utils/constants.ts`
- Create: `/dataspace/kqspace/MCPsys/services/web/tests/unit/format.test.ts`
- Create: `/dataspace/kqspace/MCPsys/services/web/tests/unit/permissions.test.ts`

- [ ] **Step 1: 写 format.ts 测试（先失败）**

```ts
// /dataspace/kqspace/MCPsys/services/web/tests/unit/format.test.ts
import { describe, it, expect } from 'vitest';
import { formatBytes, formatDuration, formatDateTime, formatRelative } from '@/utils/format';

describe('formatBytes', () => {
  it('returns "0 B" for 0', () => {
    expect(formatBytes(0)).toBe('0 B');
  });
  it('formats KB', () => {
    expect(formatBytes(2048)).toBe('2.00 KB');
  });
  it('formats MB', () => {
    expect(formatBytes(1024 * 1024 * 3.5)).toBe('3.50 MB');
  });
});

describe('formatDuration', () => {
  it('shows ms for < 1s', () => {
    expect(formatDuration(450)).toBe('450ms');
  });
  it('shows seconds for >= 1s', () => {
    expect(formatDuration(1500)).toBe('1.50s');
  });
});

describe('formatDateTime', () => {
  it('formats ISO to YYYY-MM-DD HH:mm:ss', () => {
    expect(formatDateTime('2026-05-06T03:14:25Z')).toMatch(/2026-05-0\d \d{2}:14:25/);
  });
});

describe('formatRelative', () => {
  it('returns "刚刚" for now', () => {
    expect(formatRelative(new Date().toISOString())).toMatch(/刚刚|秒前/);
  });
});
```

- [ ] **Step 2: 跑测试（应失败）**

```bash
cd /dataspace/kqspace/MCPsys/services/web
pnpm test tests/unit/format.test.ts
```

期望：FAIL，报 `Cannot find module '@/utils/format'`。

- [ ] **Step 3: 实现 format.ts**

```ts
// /dataspace/kqspace/MCPsys/services/web/src/utils/format.ts
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${units[i]}`;
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

export function formatDateTime(iso: string | Date | null | undefined): string {
  if (!iso) return '-';
  return dayjs(iso).format('YYYY-MM-DD HH:mm:ss');
}

export function formatRelative(iso: string | Date | null | undefined): string {
  if (!iso) return '-';
  return dayjs(iso).fromNow();
}
```

- [ ] **Step 4: 跑测试（应通过）**

```bash
pnpm test tests/unit/format.test.ts
```

期望：4 个 describe 全 PASS。

- [ ] **Step 5: 写 permissions.ts 测试 + 实现**

`tests/unit/permissions.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { hasRole, type Role } from '@/utils/permissions';

describe('hasRole', () => {
  it('returns true when user role is in allowed', () => {
    expect(hasRole('admin', ['admin', 'operator'])).toBe(true);
    expect(hasRole('operator', ['admin', 'operator'])).toBe(true);
  });
  it('returns false when user role is not in allowed', () => {
    expect(hasRole('viewer', ['admin', 'operator'])).toBe(false);
  });
  it('returns false for null role', () => {
    expect(hasRole(null, ['admin'])).toBe(false);
  });
  it('returns true for empty allowed list (no restriction)', () => {
    expect(hasRole('viewer', [])).toBe(true);
  });
});
```

`src/utils/permissions.ts`:

```ts
export type Role = 'admin' | 'operator' | 'viewer';

export function hasRole(userRole: Role | null | undefined, allowed: Role[]): boolean {
  if (allowed.length === 0) return true;
  if (!userRole) return false;
  return allowed.includes(userRole);
}
```

跑：`pnpm test tests/unit/permissions.test.ts` → PASS。

- [ ] **Step 6: constants.ts**

```ts
// /dataspace/kqspace/MCPsys/services/web/src/utils/constants.ts
export const STORAGE_KEY_TOKEN = 'mcpsys_token';
export const STORAGE_KEY_UI = 'mcpsys_ui';

export const ROLE_LABELS: Record<string, string> = {
  admin:    '管理员',
  operator: '运维',
  viewer:   '只读',
};

export const STATUS_LABELS: Record<string, string> = {
  active:    '启用',
  disabled:  '禁用',
  revoked:   '已吊销',
  healthy:   '健康',
  unhealthy: '异常',
  unknown:   '未知',
};
```

- [ ] **Step 7: i18n 设置**

`src/i18n/index.ts`:

```ts
import { createI18n } from 'vue-i18n';
import zhCN from './locales/zh-CN';

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  fallbackLocale: 'zh-CN',
  messages: { 'zh-CN': zhCN },
});

export default i18n;
```

`src/i18n/locales/zh-CN.ts`（先放骨架，后续 task 增量补充）:

```ts
export default {
  app: {
    name: 'MCPsys 管理后台',
    version: 'v0.1.0',
  },
  common: {
    confirm: '确认',
    cancel: '取消',
    save: '保存',
    edit: '编辑',
    delete: '删除',
    create: '新建',
    search: '搜索',
    refresh: '刷新',
    copy: '复制',
    copied: '已复制',
    loading: '加载中...',
    empty: '暂无数据',
    yes: '是',
    no: '否',
    actions: '操作',
    detail: '详情',
    back: '返回',
  },
  auth: {
    login: {
      title: '登录',
      username: '用户名',
      password: '密码',
      submit: '登 录',
      submitting: '登录中...',
      error: {
        invalid: '用户名或密码错误',
        network: '网络异常，请稍后重试',
      },
    },
    logout: '退出登录',
  },
  nav: {
    dashboard: '仪表盘',
    services: '服务管理',
    serviceList: '服务目录',
    callLogs: '调用日志',
    onboarding: '接入管理',
    applications: '应用',
    apiKeys: 'API Key',
    system: '系统管理',
    users: '用户',
    upcoming: 'v1 即将上线',
    permissions: '权限管理',
    config: '配置中心',
    audit: '审计事件',
    versions: '服务版本',
    profile: '个人资料',
  },
  error: {
    forbidden: { title: '无权访问', description: '您当前的角色没有访问该页面的权限' },
    notFound:  { title: '页面不存在', description: '您访问的页面不存在或已被移除' },
    server:    '服务端错误，请稍后重试',
    network:   '网络异常',
    permissionDenied: '权限不足',
  },
};
```

- [ ] **Step 8: main.ts 装配 i18n**

```ts
// /dataspace/kqspace/MCPsys/services/web/src/main.ts
import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import i18n from './i18n';
import './styles/main.scss';

const app = createApp(App);
app.use(createPinia());
app.use(i18n);
app.mount('#app');
```

- [ ] **Step 9: 跑全量测试 + typecheck + 提交**

```bash
pnpm test
pnpm typecheck
```

两者 PASS：

```bash
cd /dataspace/kqspace/MCPsys
git add services/web/src/utils/ services/web/src/i18n/ services/web/tests/ services/web/src/main.ts
git commit -m "feat(web): i18n + utils with unit tests"
```

---

## 阶段二：数据层（T4–T6）

### Task 4: API client（axios + 拦截器）+ 类型 + auth 接口

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/web/src/api/client.ts`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/api/types.ts`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/api/auth.ts`
- Create: `/dataspace/kqspace/MCPsys/services/web/tests/unit/client.test.ts`

- [ ] **Step 1: types.ts**

```ts
// /dataspace/kqspace/MCPsys/services/web/src/api/types.ts
export type Role = 'admin' | 'operator' | 'viewer';
export type UserStatus = 'active' | 'disabled';

export interface User {
  id: number;
  username: string;
  role: Role;
  status: UserStatus;
  last_login_at: string | null;
  created_at: string;
}

export interface PaginatedList<T> {
  items: T[];
  total: number;
}

export interface ApiError {
  detail?: string | { msg: string }[];
}
```

- [ ] **Step 2: 写 client 拦截器测试**

```ts
// /dataspace/kqspace/MCPsys/services/web/tests/unit/client.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import MockAdapter from 'axios-mock-adapter';
import { client } from '@/api/client';
import { useAuthStore } from '@/stores/auth';

describe('axios client', () => {
  let mock: MockAdapter;

  beforeEach(() => {
    setActivePinia(createPinia());
    mock = new MockAdapter(client);
  });

  it('attaches Bearer token when set', async () => {
    const auth = useAuthStore();
    auth.token = 'TEST_TOKEN';
    mock.onGet('/api/v1/foo').reply((config) => {
      expect(config.headers?.Authorization).toBe('Bearer TEST_TOKEN');
      return [200, { ok: true }];
    });
    await client.get('/api/v1/foo');
  });

  it('does not attach Authorization when token empty', async () => {
    mock.onGet('/api/v1/foo').reply((config) => {
      expect(config.headers?.Authorization).toBeUndefined();
      return [200, { ok: true }];
    });
    await client.get('/api/v1/foo');
  });

  it('clears token and rejects on 401', async () => {
    const auth = useAuthStore();
    auth.token = 'TOKEN';
    mock.onGet('/api/v1/foo').reply(401);
    await expect(client.get('/api/v1/foo')).rejects.toThrow();
    expect(auth.token).toBe('');
  });
});
```

- [ ] **Step 3: 安装测试依赖 + 跑（应失败）**

```bash
pnpm add -D axios-mock-adapter
pnpm test tests/unit/client.test.ts
```

期望：FAIL（store/client 还没写）。

- [ ] **Step 4: 实现 client.ts（拦截器骨架，store 在 T5 再补；先用懒导入避免循环依赖）**

```ts
// /dataspace/kqspace/MCPsys/services/web/src/api/client.ts
import axios, { type AxiosError } from 'axios';
import { ElMessage } from 'element-plus';

export const client = axios.create({
  baseURL: '/',
  timeout: 15_000,
});

client.interceptors.request.use(async (config) => {
  const { useAuthStore } = await import('@/stores/auth');
  const auth = useAuthStore();
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`;
  }
  return config;
});

client.interceptors.response.use(
  (resp) => resp,
  async (err: AxiosError<{ detail?: string }>) => {
    const { useAuthStore } = await import('@/stores/auth');
    const auth = useAuthStore();
    const status = err.response?.status;
    const detail = err.response?.data?.detail;
    const msg = typeof detail === 'string' ? detail : '';

    if (status === 401) {
      auth.clear();
      const { default: router } = await import('@/router');
      const current = router.currentRoute.value;
      if (current.name !== 'Login') {
        router.push({ name: 'Login', query: { redirect: current.fullPath } });
      }
    } else if (status === 403) {
      ElMessage.warning('权限不足');
    } else if (status && status >= 500) {
      ElMessage.error('服务端错误，请稍后重试');
      console.error('[5xx]', err);
    } else if (status && status >= 400 && status !== 404) {
      ElMessage.error(msg || `请求失败 (${status})`);
    } else if (!status) {
      ElMessage.error('网络异常');
    }
    return Promise.reject(err);
  },
);
```

> **注意**：T5、T6 把 `stores/auth.ts` 和 `router/index.ts` 写出来后，本文件的懒 import 才不会运行时报错；在那之前 client 单测里手动 setActivePinia 即可工作。

- [ ] **Step 5: auth.ts API 包装**

```ts
// /dataspace/kqspace/MCPsys/services/web/src/api/auth.ts
import { client } from './client';
import type { User } from './types';

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const params = new URLSearchParams();
  params.append('username', username);
  params.append('password', password);
  const { data } = await client.post<LoginResponse>('/api/v1/auth/login', params, {
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
  });
  return data;
}

export async function getMe(): Promise<User> {
  const { data } = await client.get<User>('/api/v1/auth/me');
  return data;
}
```

- [ ] **Step 6: typecheck + 提交（测试要等 T5 写完 store 才能完整跑）**

```bash
pnpm typecheck
cd /dataspace/kqspace/MCPsys
git add services/web/src/api/ services/web/tests/unit/client.test.ts
git commit -m "feat(web): axios client with auth interceptors + auth api wrappers"
```

---

### Task 5: Pinia auth store + ui store（含测试）

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/web/src/stores/auth.ts`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/stores/ui.ts`
- Create: `/dataspace/kqspace/MCPsys/services/web/tests/unit/auth-store.test.ts`

- [ ] **Step 1: 写 auth store 测试**

```ts
// /dataspace/kqspace/MCPsys/services/web/tests/unit/auth-store.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useAuthStore } from '@/stores/auth';
import * as authApi from '@/api/auth';

vi.mock('@/api/auth');

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    vi.resetAllMocks();
  });

  it('login sets token and fetches user', async () => {
    vi.mocked(authApi.login).mockResolvedValue({ access_token: 'T', token_type: 'bearer' });
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: 1, username: 'admin', role: 'admin', status: 'active',
      last_login_at: null, created_at: '2026-05-06T00:00:00Z',
    });

    const auth = useAuthStore();
    await auth.login('admin', 'admin123');

    expect(auth.token).toBe('T');
    expect(auth.user?.username).toBe('admin');
    expect(auth.isAuthenticated).toBe(true);
  });

  it('hasRole respects role list', () => {
    const auth = useAuthStore();
    auth.user = { id: 1, username: 'u', role: 'operator', status: 'active', last_login_at: null, created_at: '' };
    expect(auth.hasRole('admin', 'operator')).toBe(true);
    expect(auth.hasRole('admin')).toBe(false);
  });

  it('clear wipes token and user', () => {
    const auth = useAuthStore();
    auth.token = 'X';
    auth.user = { id: 1, username: 'u', role: 'admin', status: 'active', last_login_at: null, created_at: '' };
    auth.clear();
    expect(auth.token).toBe('');
    expect(auth.user).toBeNull();
  });
});
```

- [ ] **Step 2: 跑（应失败）**

```bash
pnpm test tests/unit/auth-store.test.ts
```

期望：FAIL（store 还没写）。

- [ ] **Step 3: 实现 auth store**

```ts
// /dataspace/kqspace/MCPsys/services/web/src/stores/auth.ts
import { defineStore } from 'pinia';
import { useStorage } from '@vueuse/core';
import { computed, ref } from 'vue';
import { login as apiLogin, getMe } from '@/api/auth';
import { STORAGE_KEY_TOKEN } from '@/utils/constants';
import type { Role, User } from '@/api/types';

export const useAuthStore = defineStore('auth', () => {
  const token = useStorage<string>(STORAGE_KEY_TOKEN, '');
  const user = ref<User | null>(null);
  const loading = ref(false);

  const isAuthenticated = computed(() => !!token.value);

  function hasRole(...roles: Role[]): boolean {
    if (roles.length === 0) return true;
    if (!user.value) return false;
    return roles.includes(user.value.role);
  }

  async function login(username: string, password: string): Promise<void> {
    loading.value = true;
    try {
      const resp = await apiLogin(username, password);
      token.value = resp.access_token;
      user.value = await getMe();
    } finally {
      loading.value = false;
    }
  }

  async function fetchMe(): Promise<void> {
    if (!token.value) return;
    user.value = await getMe();
  }

  function clear(): void {
    token.value = '';
    user.value = null;
  }

  return { token, user, loading, isAuthenticated, hasRole, login, fetchMe, clear };
});
```

- [ ] **Step 4: 跑测试（应通过）**

```bash
pnpm test tests/unit/auth-store.test.ts tests/unit/client.test.ts
```

期望：两个 test 文件全 PASS。

- [ ] **Step 5: 实现 ui store**

```ts
// /dataspace/kqspace/MCPsys/services/web/src/stores/ui.ts
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
```

- [ ] **Step 6: 提交**

```bash
pnpm test
cd /dataspace/kqspace/MCPsys
git add services/web/src/stores/ services/web/tests/unit/auth-store.test.ts
git commit -m "feat(web): pinia auth + ui stores"
```

---

### Task 6: Vue Router + 路由守卫

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/web/src/router/index.ts`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/router/guards.ts`

- [ ] **Step 1: router/index.ts（13 条路由，组件用 lazy import；error 页和详情页占位 stub）**

```ts
// /dataspace/kqspace/MCPsys/services/web/src/router/index.ts
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';
import type { Role } from '@/api/types';
import { setupGuards } from './guards';

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean;
    roles?: Role[];
    layout?: 'app' | 'auth';
    title?: string;
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/LoginPage.vue'),
    meta: { requiresAuth: false, layout: 'auth', title: 'auth.login.title' },
  },
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('@/views/dashboard/DashboardPage.vue'),
    meta: { requiresAuth: true, layout: 'app', title: 'nav.dashboard' },
  },
  {
    path: '/services',
    name: 'ServiceList',
    component: () => import('@/views/services/ServiceListPage.vue'),
    meta: { requiresAuth: true, layout: 'app', title: 'nav.serviceList' },
  },
  {
    path: '/services/:id',
    name: 'ServiceDetail',
    component: () => import('@/views/services/ServiceDetailPage.vue'),
    meta: { requiresAuth: true, layout: 'app' },
  },
  {
    path: '/applications',
    name: 'ApplicationList',
    component: () => import('@/views/applications/ApplicationListPage.vue'),
    meta: { requiresAuth: true, roles: ['admin', 'operator'], layout: 'app', title: 'nav.applications' },
  },
  {
    path: '/applications/:id',
    name: 'ApplicationDetail',
    component: () => import('@/views/applications/ApplicationDetailPage.vue'),
    meta: { requiresAuth: true, roles: ['admin', 'operator'], layout: 'app' },
  },
  {
    path: '/api-keys',
    name: 'ApiKeyList',
    component: () => import('@/views/api-keys/ApiKeyListPage.vue'),
    meta: { requiresAuth: true, roles: ['admin', 'operator'], layout: 'app', title: 'nav.apiKeys' },
  },
  {
    path: '/call-logs',
    name: 'CallLogList',
    component: () => import('@/views/call-logs/CallLogListPage.vue'),
    meta: { requiresAuth: true, roles: ['admin', 'operator'], layout: 'app', title: 'nav.callLogs' },
  },
  {
    path: '/users',
    name: 'UserList',
    component: () => import('@/views/users/UserListPage.vue'),
    meta: { requiresAuth: true, roles: ['admin'], layout: 'app', title: 'nav.users' },
  },
  {
    path: '/users/:id',
    name: 'UserDetail',
    component: () => import('@/views/users/UserDetailPage.vue'),
    meta: { requiresAuth: true, roles: ['admin'], layout: 'app' },
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('@/views/profile/ProfilePage.vue'),
    meta: { requiresAuth: true, layout: 'app', title: 'nav.profile' },
  },
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('@/views/error/ForbiddenPage.vue'),
    meta: { requiresAuth: false, layout: 'app', title: 'error.forbidden.title' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/error/NotFoundPage.vue'),
    meta: { requiresAuth: false, layout: 'app', title: 'error.notFound.title' },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

setupGuards(router);

export default router;
```

- [ ] **Step 2: router/guards.ts**

```ts
// /dataspace/kqspace/MCPsys/services/web/src/router/guards.ts
import type { Router } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

export function setupGuards(router: Router): void {
  router.beforeEach(async (to) => {
    const auth = useAuthStore();

    if (to.meta.requiresAuth === false) {
      return true;
    }

    if (!auth.token) {
      return { name: 'Login', query: { redirect: to.fullPath } };
    }

    if (!auth.user) {
      try {
        await auth.fetchMe();
      } catch {
        auth.clear();
        return { name: 'Login', query: { redirect: to.fullPath } };
      }
    }

    if (to.meta.roles && to.meta.roles.length > 0) {
      if (!auth.hasRole(...to.meta.roles)) {
        return { name: 'Forbidden' };
      }
    }

    return true;
  });
}
```

- [ ] **Step 3: 创建所有路由的 stub 页面（保证 lazy import 不报错）**

为每个 view 创建空白 stub：

```bash
mkdir -p /dataspace/kqspace/MCPsys/services/web/src/views/{login,dashboard,services,applications,api-keys,call-logs,users,profile,error}
```

每个 stub 内容（替换 `<PageName>` 即可）:

```vue
<!-- 例：services/web/src/views/dashboard/DashboardPage.vue -->
<template>
  <div style="padding: 24px;">
    <h2>Dashboard (stub)</h2>
  </div>
</template>
```

需要创建的 stub 列表（每个文件复制上面模板，替换标题）：

```
src/views/login/LoginPage.vue
src/views/dashboard/DashboardPage.vue
src/views/services/ServiceListPage.vue
src/views/services/ServiceDetailPage.vue
src/views/applications/ApplicationListPage.vue
src/views/applications/ApplicationDetailPage.vue
src/views/api-keys/ApiKeyListPage.vue
src/views/call-logs/CallLogListPage.vue
src/views/users/UserListPage.vue
src/views/users/UserDetailPage.vue
src/views/profile/ProfilePage.vue
src/views/error/ForbiddenPage.vue
src/views/error/NotFoundPage.vue
```

- [ ] **Step 4: main.ts 装配 router + App.vue 切到 RouterView**

```ts
// /dataspace/kqspace/MCPsys/services/web/src/main.ts
import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import router from './router';
import i18n from './i18n';
import './styles/main.scss';

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.use(i18n);
app.mount('#app');
```

```vue
<!-- /dataspace/kqspace/MCPsys/services/web/src/App.vue -->
<template>
  <RouterView />
</template>
```

- [ ] **Step 5: dev 验证路由跳转**

```bash
pnpm dev
```

打开 http://localhost:5173/ → 应该被守卫挡到 `/login?redirect=/`，stub 页面显示 "Login (stub)"。
打开 http://localhost:5173/services → 同样跳 `/login`。
直接访问 `/login` → 显示 stub。

- [ ] **Step 6: typecheck + 提交**

```bash
pnpm typecheck
cd /dataspace/kqspace/MCPsys
git add services/web/src/router/ services/web/src/views/ services/web/src/main.ts services/web/src/App.vue
git commit -m "feat(web): vue-router with auth guards + page stubs"
```

---

## 阶段三：通用组件（T7–T8）

### Task 7: 通用组件套件（Icon、StatusTag、RelativeTime、CopyButton、EmptyState、PageHeader、DataTable）

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/web/src/components/icons/Icon.vue`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/components/common/PageHeader.vue`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/components/common/EmptyState.vue`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/components/common/StatusTag.vue`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/components/common/RelativeTime.vue`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/components/common/CopyButton.vue`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/components/common/DataTable.vue`

- [ ] **Step 1: Icon.vue（Lucide 包装）**

```vue
<!-- src/components/icons/Icon.vue -->
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
```

> 用法：`<Icon name="user" />`、`<Icon name="chevron-right" :size="20" />`。

- [ ] **Step 2: PageHeader.vue**

```vue
<!-- src/components/common/PageHeader.vue -->
<script setup lang="ts">
defineProps<{
  title: string;
  description?: string;
}>();
</script>

<template>
  <div class="page-header">
    <div class="page-header__main">
      <h1 class="page-header__title">{{ title }}</h1>
      <p v-if="description" class="page-header__desc">{{ description }}</p>
    </div>
    <div class="page-header__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  padding: var(--space-6) 0 var(--space-4);
  border-bottom: 1px solid var(--color-gray-200);
  margin-bottom: var(--space-6);
}
.page-header__title {
  font-size: var(--text-xl);
  font-weight: var(--font-weight-semibold);
}
.page-header__desc {
  margin-top: var(--space-1);
  color: var(--color-gray-500);
  font-size: var(--text-sm);
}
.page-header__actions {
  display: flex;
  gap: var(--space-2);
}
</style>
```

- [ ] **Step 3: EmptyState.vue**

```vue
<!-- src/components/common/EmptyState.vue -->
<script setup lang="ts">
import Icon from '@/components/icons/Icon.vue';
withDefaults(defineProps<{
  icon?: string;
  title?: string;
  description?: string;
}>(), {
  icon: 'inbox',
  title: '暂无数据',
  description: '',
});
</script>

<template>
  <div class="empty-state">
    <Icon :name="icon" :size="48" :stroke-width="1.5" color="var(--color-gray-400)" />
    <h3 class="empty-state__title">{{ title }}</h3>
    <p v-if="description" class="empty-state__desc">{{ description }}</p>
    <div class="empty-state__action"><slot /></div>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-12) var(--space-6);
  text-align: center;
}
.empty-state__title {
  margin-top: var(--space-3);
  font-size: var(--text-md);
  color: var(--color-gray-700);
}
.empty-state__desc {
  margin-top: var(--space-1);
  color: var(--color-gray-500);
  font-size: var(--text-sm);
}
.empty-state__action { margin-top: var(--space-4); }
</style>
```

- [ ] **Step 4: StatusTag.vue**

```vue
<!-- src/components/common/StatusTag.vue -->
<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  status: string;
  label?: string;
}>();

const TYPE_MAP: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
  active: 'success', healthy: 'success',
  disabled: 'info',  unknown: 'info',
  unhealthy: 'danger', revoked: 'danger', error: 'danger',
  warning: 'warning',
};

const LABEL_MAP: Record<string, string> = {
  active: '启用', disabled: '禁用',
  healthy: '健康', unhealthy: '异常', unknown: '未知',
  revoked: '已吊销', error: '错误', success: '成功',
};

const tagType = computed(() => TYPE_MAP[props.status] ?? 'info');
const tagLabel = computed(() => props.label ?? LABEL_MAP[props.status] ?? props.status);
</script>

<template>
  <el-tag :type="tagType" size="small" effect="light">{{ tagLabel }}</el-tag>
</template>
```

- [ ] **Step 5: RelativeTime.vue**

```vue
<!-- src/components/common/RelativeTime.vue -->
<script setup lang="ts">
import { formatDateTime, formatRelative } from '@/utils/format';

const props = defineProps<{
  value: string | null | undefined;
}>();
</script>

<template>
  <el-tooltip v-if="props.value" :content="formatDateTime(props.value)" placement="top">
    <span class="text-secondary">{{ formatRelative(props.value) }}</span>
  </el-tooltip>
  <span v-else class="text-tertiary">—</span>
</template>
```

- [ ] **Step 6: CopyButton.vue**

```vue
<!-- src/components/common/CopyButton.vue -->
<script setup lang="ts">
import { useClipboard } from '@vueuse/core';
import { ElMessage } from 'element-plus';
import Icon from '@/components/icons/Icon.vue';

const props = defineProps<{
  text: string;
  size?: 'small' | 'default';
}>();

const { copy } = useClipboard({ source: () => props.text });

async function handleCopy() {
  await copy(props.text);
  ElMessage.success('已复制');
}
</script>

<template>
  <el-button :size="size ?? 'small'" link @click="handleCopy">
    <Icon name="copy" :size="14" />
  </el-button>
</template>
```

- [ ] **Step 7: DataTable.vue（ElTable 薄封装：统一 loading / empty / 分页）**

```vue
<!-- src/components/common/DataTable.vue -->
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
```

- [ ] **Step 8: typecheck + 提交**

```bash
pnpm typecheck
cd /dataspace/kqspace/MCPsys
git add services/web/src/components/
git commit -m "feat(web): common components (icon, page header, empty state, status tag, relative time, copy, data table)"
```

---

### Task 8: 业务级共享组件 HealthDot

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/web/src/components/feature/HealthDot.vue`

> ApiKeyIssueModal 在 T14 与 ApiKey 页一起做，因为它强依赖签发流程。

- [ ] **Step 1: HealthDot.vue**

```vue
<!-- src/components/feature/HealthDot.vue -->
<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  status: 'healthy' | 'unhealthy' | 'unknown';
}>();

const COLOR: Record<string, string> = {
  healthy:   'var(--color-success)',
  unhealthy: 'var(--color-error)',
  unknown:   'var(--color-gray-400)',
};
const LABEL: Record<string, string> = {
  healthy: '健康', unhealthy: '异常', unknown: '未知',
};

const color = computed(() => COLOR[props.status] ?? COLOR.unknown);
const label = computed(() => LABEL[props.status] ?? '未知');
</script>

<template>
  <span class="health-dot" :title="label">
    <span class="health-dot__pulse" :style="{ background: color }" />
    <span>{{ label }}</span>
  </span>
</template>

<style scoped>
.health-dot {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
}
.health-dot__pulse {
  width: 8px; height: 8px;
  border-radius: var(--radius-full);
  display: inline-block;
}
</style>
```

- [ ] **Step 2: 提交**

```bash
cd /dataspace/kqspace/MCPsys
git add services/web/src/components/feature/HealthDot.vue
git commit -m "feat(web): HealthDot component"
```

---

## 阶段四：布局与认证（T9–T10）

### Task 9: 登录页（视觉重头）+ AuthLayout

**Files:**
- Modify: `/dataspace/kqspace/MCPsys/services/web/src/views/login/LoginPage.vue`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/layouts/AuthLayout.vue`

- [ ] **Step 1: AuthLayout.vue**

```vue
<!-- src/layouts/AuthLayout.vue -->
<template>
  <div class="auth-layout">
    <slot />
  </div>
</template>

<style scoped>
.auth-layout {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #F8FAFC 0%, #EFF6FF 100%);
}
</style>
```

- [ ] **Step 2: LoginPage.vue（视觉规格见 spec §6.1）**

```vue
<!-- src/views/login/LoginPage.vue -->
<script setup lang="ts">
import { ref, reactive } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import Icon from '@/components/icons/Icon.vue';
import AuthLayout from '@/layouts/AuthLayout.vue';

const { t } = useI18n();
const router = useRouter();
const route = useRoute();
const auth = useAuthStore();

const form = reactive({ username: '', password: '' });
const errorMsg = ref('');
const submitting = ref(false);

async function onSubmit() {
  errorMsg.value = '';
  if (!form.username || !form.password) {
    errorMsg.value = '请输入用户名和密码';
    return;
  }
  submitting.value = true;
  try {
    await auth.login(form.username, form.password);
    const redirect = (route.query.redirect as string) ?? '/';
    router.push(redirect);
    ElMessage.success(`欢迎回来，${auth.user?.username}`);
  } catch (err: any) {
    const status = err.response?.status;
    if (status === 401) errorMsg.value = t('auth.login.error.invalid');
    else errorMsg.value = t('auth.login.error.network');
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <AuthLayout>
    <div class="login-card">
      <div class="login-card__brand">
        <Icon name="network" :size="40" color="var(--color-primary-500)" :stroke-width="1.75" />
        <h1>{{ t('app.name') }}</h1>
      </div>

      <el-form @submit.prevent="onSubmit" size="default" label-position="top">
        <el-form-item :label="t('auth.login.username')">
          <el-input v-model="form.username" placeholder="admin" autofocus autocomplete="username" />
        </el-form-item>
        <el-form-item :label="t('auth.login.password')">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            autocomplete="current-password"
            @keyup.enter="onSubmit"
          />
        </el-form-item>
        <p v-if="errorMsg" class="login-card__error">{{ errorMsg }}</p>
        <el-button
          type="primary"
          native-type="submit"
          :loading="submitting"
          style="width: 100%; margin-top: 8px;"
          @click="onSubmit"
        >
          {{ submitting ? t('auth.login.submitting') : t('auth.login.submit') }}
        </el-button>
      </el-form>

      <div class="login-card__footer">{{ t('app.version') }} · 内部使用</div>
    </div>
  </AuthLayout>
</template>

<style scoped>
.login-card {
  width: 480px;
  background: var(--color-surface);
  border-radius: 12px;
  box-shadow: var(--shadow-md);
  padding: var(--space-10);
}
.login-card__brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-8);
}
.login-card__brand h1 {
  font-size: var(--text-2xl);
  font-weight: var(--font-weight-semibold);
}
.login-card__error {
  color: var(--color-error);
  font-size: var(--text-sm);
  margin: var(--space-2) 0;
}
.login-card__footer {
  text-align: center;
  margin-top: var(--space-8);
  color: var(--color-gray-400);
  font-size: var(--text-xs);
}
</style>
```

- [ ] **Step 3: dev 视觉验证**

```bash
pnpm dev
```

访问 http://localhost:5173/login，**验证**：
1. 页面背景是浅渐变（左上偏白，右下偏蓝）
2. 卡片居中，宽 480px，圆角 12px
3. Logo 是蓝色 network 图标 + "MCPsys 管理后台" 标题
4. 输入框 32px 高度，圆角 6px
5. 登录按钮全宽，主色蓝
6. 故意输错密码 → 表单下方红色文字 "用户名或密码错误"，不弹 toast
7. 用 admin / admin123 登录 → 跳到 / （之后是 Dashboard stub）

任一不符 → 调样式直到符合 spec §6.1。

- [ ] **Step 4: 提交**

```bash
cd /dataspace/kqspace/MCPsys
git add services/web/src/views/login/ services/web/src/layouts/AuthLayout.vue
git commit -m "feat(web): login page + auth layout"
```

---

### Task 10: AppLayout + SideBar + TopBar + UserMenu

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/web/src/layouts/AppLayout.vue`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/components/nav/SideBar.vue`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/components/nav/TopBar.vue`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/components/nav/UserMenu.vue`
- Modify: `/dataspace/kqspace/MCPsys/services/web/src/App.vue`

- [ ] **Step 1: SideBar.vue（按 spec §5.3 的层级，按 role 显隐）**

```vue
<!-- src/components/nav/SideBar.vue -->
<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useUiStore } from '@/stores/ui';
import { useAuthStore } from '@/stores/auth';
import Icon from '@/components/icons/Icon.vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const ui = useUiStore();
const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

interface MenuItem {
  key: string;
  routeName?: string;
  icon: string;
  labelKey: string;
  roles?: ('admin' | 'operator' | 'viewer')[];
  children?: MenuItem[];
  disabled?: boolean;
}

const menu = computed<MenuItem[]>(() => [
  { key: 'dashboard', routeName: 'Dashboard', icon: 'layout-dashboard', labelKey: 'nav.dashboard' },
  {
    key: 'services-group', icon: 'boxes', labelKey: 'nav.services',
    children: [
      { key: 'service-list', routeName: 'ServiceList', icon: 'box', labelKey: 'nav.serviceList' },
      { key: 'call-logs', routeName: 'CallLogList', icon: 'scroll-text', labelKey: 'nav.callLogs', roles: ['admin', 'operator'] },
    ],
  },
  {
    key: 'onboarding-group', icon: 'plug', labelKey: 'nav.onboarding', roles: ['admin', 'operator'],
    children: [
      { key: 'apps', routeName: 'ApplicationList', icon: 'package', labelKey: 'nav.applications' },
      { key: 'keys', routeName: 'ApiKeyList', icon: 'key-round', labelKey: 'nav.apiKeys' },
    ],
  },
  {
    key: 'system-group', icon: 'settings', labelKey: 'nav.system', roles: ['admin'],
    children: [
      { key: 'users', routeName: 'UserList', icon: 'users', labelKey: 'nav.users' },
    ],
  },
  {
    key: 'upcoming-group', icon: 'sparkles', labelKey: 'nav.upcoming',
    children: [
      { key: 'permissions', icon: 'shield', labelKey: 'nav.permissions', disabled: true },
      { key: 'config',      icon: 'sliders', labelKey: 'nav.config',      disabled: true },
      { key: 'audit',       icon: 'clipboard-list', labelKey: 'nav.audit', disabled: true },
      { key: 'versions',    icon: 'git-branch', labelKey: 'nav.versions',  disabled: true },
    ],
  },
]);

const visibleMenu = computed(() =>
  menu.value
    .filter((g) => !g.roles || auth.hasRole(...g.roles))
    .map((g) => ({
      ...g,
      children: g.children?.filter((c) => !c.roles || auth.hasRole(...c.roles)),
    })),
);

const activeKey = computed(() => route.name as string);

function go(item: MenuItem) {
  if (item.disabled || !item.routeName) return;
  router.push({ name: item.routeName });
}
</script>

<template>
  <aside class="sidebar" :class="{ 'sidebar--collapsed': ui.state.sidebarCollapsed }">
    <div class="sidebar__brand">
      <Icon name="network" :size="22" color="var(--color-primary-500)" />
      <span v-if="!ui.state.sidebarCollapsed" class="sidebar__brand-text">MCPsys</span>
    </div>

    <nav class="sidebar__nav">
      <template v-for="group in visibleMenu" :key="group.key">
        <div v-if="group.children" class="sidebar__group">
          <div v-if="!ui.state.sidebarCollapsed" class="sidebar__group-title">
            {{ t(group.labelKey) }}
          </div>
          <button
            v-for="child in group.children"
            :key="child.key"
            class="sidebar__item"
            :class="{
              'sidebar__item--active': activeKey === child.routeName,
              'sidebar__item--disabled': child.disabled,
            }"
            :disabled="child.disabled"
            @click="go(child)"
          >
            <Icon :name="child.icon" :size="18" />
            <span v-if="!ui.state.sidebarCollapsed">{{ t(child.labelKey) }}</span>
          </button>
        </div>
        <button
          v-else
          class="sidebar__item sidebar__item--top"
          :class="{ 'sidebar__item--active': activeKey === group.routeName }"
          @click="go(group)"
        >
          <Icon :name="group.icon" :size="18" />
          <span v-if="!ui.state.sidebarCollapsed">{{ t(group.labelKey) }}</span>
        </button>
      </template>
    </nav>
  </aside>
</template>

<style scoped>
.sidebar {
  width: var(--layout-sidebar-width);
  background: var(--color-surface);
  border-right: 1px solid var(--color-gray-200);
  display: flex;
  flex-direction: column;
  transition: width 200ms ease;
  flex-shrink: 0;
}
.sidebar--collapsed { width: var(--layout-sidebar-width-collapsed); }
.sidebar__brand {
  height: var(--layout-topbar-height);
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0 var(--space-5);
  border-bottom: 1px solid var(--color-gray-200);
}
.sidebar__brand-text {
  font-size: var(--text-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-gray-900);
}
.sidebar__nav { flex: 1; padding: var(--space-3) var(--space-2); overflow-y: auto; }
.sidebar__group { margin-bottom: var(--space-3); }
.sidebar__group-title {
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-gray-400);
  font-weight: var(--font-weight-medium);
}
.sidebar__item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: none;
  cursor: pointer;
  border-radius: var(--radius-base);
  font-size: var(--text-sm);
  color: var(--color-gray-700);
  text-align: left;
  transition: var(--transition-base);
}
.sidebar__item:hover:not(:disabled) {
  background: var(--color-gray-100);
  color: var(--color-gray-900);
}
.sidebar__item--active {
  background: var(--color-primary-50);
  color: var(--color-primary-600);
  font-weight: var(--font-weight-medium);
}
.sidebar__item--disabled {
  color: var(--color-gray-400);
  cursor: not-allowed;
}
.sidebar__item--top { margin-bottom: var(--space-1); }
</style>
```

- [ ] **Step 2: UserMenu.vue**

```vue
<!-- src/components/nav/UserMenu.vue -->
<script setup lang="ts">
import { useAuthStore } from '@/stores/auth';
import { useRouter } from 'vue-router';
import { ROLE_LABELS } from '@/utils/constants';
import Icon from '@/components/icons/Icon.vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();

function handleCommand(cmd: string) {
  if (cmd === 'profile') router.push({ name: 'Profile' });
  if (cmd === 'logout') {
    auth.clear();
    router.push({ name: 'Login' });
  }
}
</script>

<template>
  <el-dropdown trigger="click" @command="handleCommand">
    <span class="user-menu">
      <span class="user-menu__avatar">
        <Icon name="user" :size="14" />
      </span>
      <span class="user-menu__name">{{ auth.user?.username }}</span>
      <el-tag size="small" type="info" effect="plain">
        {{ ROLE_LABELS[auth.user?.role ?? ''] ?? auth.user?.role }}
      </el-tag>
      <Icon name="chevron-down" :size="14" />
    </span>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item command="profile">
          <Icon name="user-circle" :size="14" /> {{ t('nav.profile') }}
        </el-dropdown-item>
        <el-dropdown-item divided command="logout">
          <Icon name="log-out" :size="14" /> {{ t('auth.logout') }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style scoped>
.user-menu {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-base);
  transition: var(--transition-base);
}
.user-menu:hover { background: var(--color-gray-100); }
.user-menu__avatar {
  width: 28px; height: 28px;
  border-radius: var(--radius-full);
  background: var(--color-primary-100);
  color: var(--color-primary-600);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.user-menu__name {
  font-size: var(--text-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-gray-700);
}
</style>
```

- [ ] **Step 3: TopBar.vue**

```vue
<!-- src/components/nav/TopBar.vue -->
<script setup lang="ts">
import { useUiStore } from '@/stores/ui';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { computed } from 'vue';
import Icon from '@/components/icons/Icon.vue';
import UserMenu from './UserMenu.vue';

const { t } = useI18n();
const ui = useUiStore();
const route = useRoute();

const pageTitle = computed(() => {
  const key = route.meta.title as string | undefined;
  return key ? t(key) : '';
});
</script>

<template>
  <header class="topbar">
    <button class="topbar__toggle" @click="ui.toggleSidebar">
      <Icon :name="ui.state.sidebarCollapsed ? 'panel-left-open' : 'panel-left-close'" :size="18" />
    </button>
    <h2 class="topbar__title">{{ pageTitle }}</h2>
    <div style="flex: 1" />
    <UserMenu />
  </header>
</template>

<style scoped>
.topbar {
  height: var(--layout-topbar-height);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-gray-200);
  padding: 0 var(--space-5);
  display: flex;
  align-items: center;
  gap: var(--space-4);
}
.topbar__toggle {
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-gray-600);
  padding: var(--space-2);
  border-radius: var(--radius-base);
  display: inline-flex;
  align-items: center;
}
.topbar__toggle:hover { background: var(--color-gray-100); }
.topbar__title {
  font-size: var(--text-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-gray-900);
}
</style>
```

- [ ] **Step 4: AppLayout.vue**

```vue
<!-- src/layouts/AppLayout.vue -->
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
```

- [ ] **Step 5: App.vue 根据 layout meta 切壳**

```vue
<!-- src/App.vue -->
<script setup lang="ts">
import { useRoute } from 'vue-router';
import { computed } from 'vue';
import AppLayout from '@/layouts/AppLayout.vue';
</script>

<template>
  <RouterView v-slot="{ Component, route }">
    <AppLayout v-if="route.meta.layout !== 'auth'">
      <component :is="Component" />
    </AppLayout>
    <component :is="Component" v-else />
  </RouterView>
</template>
```

- [ ] **Step 6: dev 视觉验证**

```bash
pnpm dev
```

登录后 → AppLayout 出现：
1. 左侧 240px 侧栏，顶部 Logo + "MCPsys"
2. 侧栏分组：仪表盘 / 服务管理 / 接入管理 / 系统管理 / v1 即将上线
3. v1 分组下 4 项灰色不可点击
4. 顶部 56px topbar，左有折叠按钮，右有用户下拉
5. 点折叠按钮 → 侧栏宽度 64px，文字隐藏，图标保留
6. 角色 viewer 登录 → "接入管理"、"系统管理"、"调用日志" 不可见
7. 点用户菜单 → 看到"个人资料 / 退出登录"，点退出回到 /login

任一不符 → 调样式或菜单显隐逻辑。

- [ ] **Step 7: 提交**

```bash
cd /dataspace/kqspace/MCPsys
git add services/web/src/layouts/AppLayout.vue services/web/src/components/nav/ services/web/src/App.vue
git commit -m "feat(web): app layout with sidebar/topbar/user menu"
```

---

## 阶段五：业务页面（T11–T17）

### Task 11: Dashboard 页（KPI 卡 + Grafana iframe）

**Files:**
- Modify: `/dataspace/kqspace/MCPsys/services/web/src/views/dashboard/DashboardPage.vue`

> **依赖**：T20 必须先把 Grafana dashboard `uid` 设为 `mcpsys-overview` 且配匿名 viewer，否则 iframe 显示登录页。本任务先把页面写完，T20 完成后才能完整验证 iframe。

- [ ] **Step 1: DashboardPage.vue（KPI 卡片暂用静态数据，后续与后端 stats 接口接入；spec MVP 没有专门的 stats 接口，先用 services/applications 列表算）**

```vue
<!-- src/views/dashboard/DashboardPage.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { client } from '@/api/client';
import { useAuthStore } from '@/stores/auth';
import PageHeader from '@/components/common/PageHeader.vue';
import Icon from '@/components/icons/Icon.vue';
import { ROLE_LABELS } from '@/utils/constants';
import { formatRelative } from '@/utils/format';

const auth = useAuthStore();

const stats = ref({
  serviceCount: 0,
  callsLast24h: 0,
  errorRateLast24h: 0,
  loading: true,
});

async function loadStats() {
  stats.value.loading = true;
  try {
    const [services, logs] = await Promise.all([
      client.get('/api/v1/services').then((r) => r.data),
      client.get('/api/v1/call-logs?limit=1000').then((r) => r.data),
    ]);
    stats.value.serviceCount = services.total ?? services.items?.length ?? 0;
    const items = logs.items ?? [];
    const cutoff = Date.now() - 24 * 3600 * 1000;
    const recent = items.filter((l: { ts: string }) => new Date(l.ts).getTime() >= cutoff);
    stats.value.callsLast24h = recent.length;
    const errors = recent.filter((l: { status: string }) => l.status !== 'success').length;
    stats.value.errorRateLast24h = recent.length > 0 ? (errors / recent.length) * 100 : 0;
  } finally {
    stats.value.loading = false;
  }
}

onMounted(loadStats);
</script>

<template>
  <PageHeader title="仪表盘" description="MCP 系统总体概况" />

  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-card__icon" style="background: var(--color-info-bg); color: var(--color-info);">
        <Icon name="boxes" :size="20" />
      </div>
      <div class="kpi-card__main">
        <div class="kpi-card__label">注册服务数</div>
        <div class="kpi-card__value">{{ stats.loading ? '—' : stats.serviceCount }}</div>
      </div>
    </div>

    <div class="kpi-card">
      <div class="kpi-card__icon" style="background: var(--color-primary-50); color: var(--color-primary-500);">
        <Icon name="activity" :size="20" />
      </div>
      <div class="kpi-card__main">
        <div class="kpi-card__label">24h 调用次数</div>
        <div class="kpi-card__value">{{ stats.loading ? '—' : stats.callsLast24h.toLocaleString() }}</div>
      </div>
    </div>

    <div class="kpi-card">
      <div class="kpi-card__icon" style="background: var(--color-warning-bg); color: var(--color-warning);">
        <Icon name="trending-up" :size="20" />
      </div>
      <div class="kpi-card__main">
        <div class="kpi-card__label">24h 错误率</div>
        <div class="kpi-card__value">{{ stats.loading ? '—' : stats.errorRateLast24h.toFixed(1) + ' %' }}</div>
      </div>
    </div>

    <div class="kpi-card">
      <div class="kpi-card__icon" style="background: var(--color-success-bg); color: var(--color-success);">
        <Icon name="user-circle" :size="20" />
      </div>
      <div class="kpi-card__main">
        <div class="kpi-card__label">我的角色</div>
        <div class="kpi-card__value">{{ ROLE_LABELS[auth.user?.role ?? ''] ?? '—' }}</div>
        <div class="kpi-card__sub">上次登录 {{ formatRelative(auth.user?.last_login_at) }}</div>
      </div>
    </div>
  </div>

  <div class="dashboard-iframe-wrap">
    <iframe
      class="dashboard-iframe"
      src="/grafana/d/mcpsys-overview/mcp-overview?theme=light&kiosk=tv"
      title="MCP Overview"
    />
  </div>
</template>

<style scoped>
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}
.kpi-card {
  display: flex;
  gap: var(--space-3);
  background: var(--color-surface);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-base);
  padding: var(--space-5);
}
.kpi-card__icon {
  width: 40px; height: 40px;
  border-radius: var(--radius-base);
  display: inline-flex;
  align-items: center;
  justify-content: center;
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
.dashboard-iframe-wrap {
  background: var(--color-surface);
  border-radius: var(--radius-base);
  border: 1px solid var(--color-gray-200);
  overflow: hidden;
}
.dashboard-iframe {
  width: 100%;
  height: 720px;
  border: none;
}
</style>
```

- [ ] **Step 2: dev 视觉验证（iframe 暂时会显示 Grafana 登录页，T20 后才正常）**

```bash
pnpm dev
```

访问 / → 4 个 KPI 卡渲染（数据可能是 0），iframe 区域有底色和边框；iframe 内容可能是 Grafana 登录页（T20 修复）。

- [ ] **Step 3: 提交**

```bash
cd /dataspace/kqspace/MCPsys
git add services/web/src/views/dashboard/
git commit -m "feat(web): dashboard with KPI cards + grafana iframe"
```

---

### Task 12: 服务列表 + 详情页

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/web/src/api/services.ts`
- Modify: `/dataspace/kqspace/MCPsys/services/web/src/views/services/ServiceListPage.vue`
- Modify: `/dataspace/kqspace/MCPsys/services/web/src/views/services/ServiceDetailPage.vue`

- [ ] **Step 1: api/services.ts**

```ts
// /dataspace/kqspace/MCPsys/services/web/src/api/services.ts
import { client } from './client';
import type { PaginatedList } from './types';

export type Transport = 'streamable_http';
export type ServiceStatus = 'active' | 'disabled';
export type HealthStatus = 'healthy' | 'unhealthy' | 'unknown';

export interface McpService {
  id: number;
  slug: string;
  display_name: string;
  description: string | null;
  owner_team: string | null;
  tags: string[] | null;
  endpoint_url: string;
  transport: Transport;
  status: ServiceStatus;
  health_status: HealthStatus;
  last_health_check_at: string | null;
  created_at: string;
  updated_at: string;
}

export function listServices(): Promise<PaginatedList<McpService>> {
  return client.get('/api/v1/services').then((r) => r.data);
}

export function getService(id: number): Promise<McpService> {
  return client.get(`/api/v1/services/${id}`).then((r) => r.data);
}

export interface CreateServicePayload {
  slug: string;
  display_name: string;
  endpoint_url: string;
  description?: string;
  owner_team?: string;
}

export function createService(payload: CreateServicePayload): Promise<McpService> {
  return client.post('/api/v1/services', payload).then((r) => r.data);
}

export function disableService(id: number): Promise<void> {
  return client.delete(`/api/v1/services/${id}`).then(() => undefined);
}
```

- [ ] **Step 2: ServiceListPage.vue**

```vue
<!-- src/views/services/ServiceListPage.vue -->
<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import { listServices, type McpService } from '@/api/services';
import { useAuthStore } from '@/stores/auth';
import PageHeader from '@/components/common/PageHeader.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import HealthDot from '@/components/feature/HealthDot.vue';
import DataTable from '@/components/common/DataTable.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import Icon from '@/components/icons/Icon.vue';

const router = useRouter();
const auth = useAuthStore();

const items = ref<McpService[]>([]);
const loading = ref(false);
const search = ref('');
const filterStatus = ref<string>('');
const filterHealth = ref<string>('');

async function load() {
  loading.value = true;
  try {
    const resp = await listServices();
    items.value = resp.items;
  } finally {
    loading.value = false;
  }
}

const filtered = computed(() => {
  return items.value.filter((s) => {
    if (filterStatus.value && s.status !== filterStatus.value) return false;
    if (filterHealth.value && s.health_status !== filterHealth.value) return false;
    if (search.value) {
      const q = search.value.toLowerCase();
      return (
        s.slug.toLowerCase().includes(q) ||
        s.display_name.toLowerCase().includes(q) ||
        (s.owner_team ?? '').toLowerCase().includes(q)
      );
    }
    return true;
  });
});

onMounted(load);
</script>

<template>
  <PageHeader title="服务目录" description="所有已注册的 MCP 服务">
    <template #actions>
      <el-button v-if="auth.hasRole('admin', 'operator')" type="primary" @click="router.push('/services?new=1')">
        <Icon name="plus" :size="14" /> 注册新服务
      </el-button>
    </template>
  </PageHeader>

  <div class="filter-bar">
    <el-input v-model="search" placeholder="搜索 slug / 名称 / 团队" style="width: 280px;" clearable>
      <template #prefix><Icon name="search" :size="14" /></template>
    </el-input>
    <el-select v-model="filterStatus" placeholder="状态" clearable style="width: 120px;">
      <el-option label="启用" value="active" />
      <el-option label="禁用" value="disabled" />
    </el-select>
    <el-select v-model="filterHealth" placeholder="健康" clearable style="width: 120px;">
      <el-option label="健康" value="healthy" />
      <el-option label="异常" value="unhealthy" />
      <el-option label="未知" value="unknown" />
    </el-select>
    <div style="flex: 1" />
    <el-button @click="load">
      <Icon name="refresh-cw" :size="14" /> 刷新
    </el-button>
  </div>

  <DataTable :data="filtered" :loading="loading">
    <el-table-column prop="slug" label="Slug" width="200">
      <template #default="{ row }: { row: McpService }">
        <span class="mono"><router-link :to="`/services/${row.id}`">{{ row.slug }}</router-link></span>
      </template>
    </el-table-column>
    <el-table-column prop="display_name" label="显示名" width="240" />
    <el-table-column prop="owner_team" label="团队" width="120">
      <template #default="{ row }">{{ row.owner_team || '—' }}</template>
    </el-table-column>
    <el-table-column label="健康" width="100">
      <template #default="{ row }: { row: McpService }">
        <HealthDot :status="row.health_status" />
      </template>
    </el-table-column>
    <el-table-column label="状态" width="80">
      <template #default="{ row }: { row: McpService }">
        <StatusTag :status="row.status" />
      </template>
    </el-table-column>
    <el-table-column prop="endpoint_url" label="端点" min-width="240" show-overflow-tooltip />
    <el-table-column label="最近检查" width="140">
      <template #default="{ row }: { row: McpService }">
        <RelativeTime :value="row.last_health_check_at" />
      </template>
    </el-table-column>
    <el-table-column label="操作" width="80" fixed="right">
      <template #default="{ row }: { row: McpService }">
        <el-button link type="primary" @click="router.push(`/services/${row.id}`)">详情</el-button>
      </template>
    </el-table-column>
  </DataTable>
</template>

<style scoped>
.filter-bar {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-4);
}
</style>
```

- [ ] **Step 3: ServiceDetailPage.vue（spec §6.4）**

```vue
<!-- src/views/services/ServiceDetailPage.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getService, type McpService } from '@/api/services';
import PageHeader from '@/components/common/PageHeader.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import HealthDot from '@/components/feature/HealthDot.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import CopyButton from '@/components/common/CopyButton.vue';
import Icon from '@/components/icons/Icon.vue';
import { formatDateTime } from '@/utils/format';

const route = useRoute();
const router = useRouter();
const service = ref<McpService | null>(null);
const loading = ref(false);
const tab = ref('overview');

async function load() {
  loading.value = true;
  try {
    service.value = await getService(Number(route.params.id));
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <el-button link @click="router.back()" style="margin-bottom: 12px;">
    <Icon name="chevron-left" :size="14" /> 返回
  </el-button>

  <div v-if="service">
    <PageHeader :title="service.slug" :description="service.display_name">
      <template #actions>
        <HealthDot :status="service.health_status" />
        <StatusTag :status="service.status" />
      </template>
    </PageHeader>

    <el-tabs v-model="tab">
      <el-tab-pane label="概览" name="overview">
        <div class="overview">
          <div class="overview__row">
            <div class="overview__label">端点 URL</div>
            <div class="overview__value mono">
              {{ service.endpoint_url }}
              <CopyButton :text="service.endpoint_url" />
            </div>
          </div>
          <div class="overview__row">
            <div class="overview__label">Transport</div>
            <div class="overview__value">{{ service.transport }}</div>
          </div>
          <div class="overview__row">
            <div class="overview__label">显示名</div>
            <div class="overview__value">{{ service.display_name }}</div>
          </div>
          <div class="overview__row">
            <div class="overview__label">所属团队</div>
            <div class="overview__value">{{ service.owner_team || '—' }}</div>
          </div>
          <div class="overview__row">
            <div class="overview__label">描述</div>
            <div class="overview__value">{{ service.description || '—' }}</div>
          </div>
          <div class="overview__row">
            <div class="overview__label">注册时间</div>
            <div class="overview__value">{{ formatDateTime(service.created_at) }}</div>
          </div>
          <div class="overview__row">
            <div class="overview__label">最近修改</div>
            <div class="overview__value">{{ formatDateTime(service.updated_at) }}</div>
          </div>
          <div class="overview__row">
            <div class="overview__label">最近健康检查</div>
            <div class="overview__value"><RelativeTime :value="service.last_health_check_at" /></div>
          </div>
        </div>
      </el-tab-pane>
      <el-tab-pane label="调用统计" name="stats">
        <div class="text-secondary" style="padding: 16px;">
          调用统计图表将在本服务接入 Grafana 子面板后显示（v1）。
        </div>
      </el-tab-pane>
      <el-tab-pane label="健康历史" name="health">
        <div class="text-secondary" style="padding: 16px;">健康检查历史（v1）。</div>
      </el-tab-pane>
      <el-tab-pane label="版本（v1）" name="versions" disabled />
    </el-tabs>
  </div>
</template>

<style scoped>
.overview {
  background: var(--color-surface);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-base);
}
.overview__row {
  display: flex;
  padding: var(--space-3) var(--space-5);
  border-bottom: 1px solid var(--color-gray-100);
}
.overview__row:last-child { border-bottom: none; }
.overview__label {
  width: 160px;
  color: var(--color-gray-500);
  font-size: var(--text-sm);
}
.overview__value {
  flex: 1;
  color: var(--color-gray-800);
  font-size: var(--text-sm);
}
</style>
```

- [ ] **Step 4: dev 验证**

```bash
pnpm dev
```

登录 → 点 "服务目录"：列表渲染 smoke 留下的 `smoke-svc`。点 slug → 详情页有概览 tab。

- [ ] **Step 5: 提交**

```bash
cd /dataspace/kqspace/MCPsys
git add services/web/src/api/services.ts services/web/src/views/services/
git commit -m "feat(web): service list + detail pages"
```

---

### Task 13: 应用列表 + 详情页

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/web/src/api/applications.ts`
- Modify: `/dataspace/kqspace/MCPsys/services/web/src/views/applications/ApplicationListPage.vue`
- Modify: `/dataspace/kqspace/MCPsys/services/web/src/views/applications/ApplicationDetailPage.vue`

- [ ] **Step 1: api/applications.ts**

```ts
// /dataspace/kqspace/MCPsys/services/web/src/api/applications.ts
import { client } from './client';
import type { PaginatedList } from './types';

export interface Application {
  id: number;
  name: string;
  team: string | null;
  description: string | null;
  owner_user_id: number;
  created_at?: string;
}

export function listApplications(): Promise<PaginatedList<Application>> {
  return client.get('/api/v1/applications').then((r) => r.data);
}

export function getApplication(id: number): Promise<Application> {
  return client.get(`/api/v1/applications/${id}`).then((r) => r.data);
}

export interface CreateApplicationPayload {
  name: string;
  team?: string;
  description?: string;
}

export function createApplication(payload: CreateApplicationPayload): Promise<Application> {
  return client.post('/api/v1/applications', payload).then((r) => r.data);
}
```

- [ ] **Step 2: ApplicationListPage.vue**

```vue
<!-- src/views/applications/ApplicationListPage.vue -->
<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { listApplications, createApplication, type Application } from '@/api/applications';
import PageHeader from '@/components/common/PageHeader.vue';
import DataTable from '@/components/common/DataTable.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import Icon from '@/components/icons/Icon.vue';
import { ElMessage, ElMessageBox } from 'element-plus';

const router = useRouter();
const items = ref<Application[]>([]);
const loading = ref(false);

const newDialog = reactive({
  visible: false,
  form: { name: '', team: '', description: '' },
  submitting: false,
});

async function load() {
  loading.value = true;
  try {
    items.value = (await listApplications()).items;
  } finally {
    loading.value = false;
  }
}

async function onCreate() {
  if (!newDialog.form.name) {
    ElMessage.warning('请输入应用名');
    return;
  }
  newDialog.submitting = true;
  try {
    await createApplication({
      name: newDialog.form.name,
      team: newDialog.form.team || undefined,
      description: newDialog.form.description || undefined,
    });
    ElMessage.success('应用创建成功');
    newDialog.visible = false;
    newDialog.form = { name: '', team: '', description: '' };
    await load();
  } finally {
    newDialog.submitting = false;
  }
}

onMounted(load);
</script>

<template>
  <PageHeader title="应用" description="Agent 在系统中的归属主体；一个应用可以拥有多个 API Key">
    <template #actions>
      <el-button type="primary" @click="newDialog.visible = true">
        <Icon name="plus" :size="14" /> 新建应用
      </el-button>
    </template>
  </PageHeader>

  <DataTable :data="items" :loading="loading">
    <el-table-column prop="name" label="应用名" width="220">
      <template #default="{ row }: { row: Application }">
        <router-link :to="`/applications/${row.id}`" class="mono">{{ row.name }}</router-link>
      </template>
    </el-table-column>
    <el-table-column prop="team" label="团队" width="160">
      <template #default="{ row }">{{ row.team || '—' }}</template>
    </el-table-column>
    <el-table-column prop="owner_user_id" label="创建人 ID" width="120" />
    <el-table-column label="描述" min-width="240" show-overflow-tooltip>
      <template #default="{ row }">{{ row.description || '—' }}</template>
    </el-table-column>
    <el-table-column label="创建时间" width="160">
      <template #default="{ row }: { row: Application }"><RelativeTime :value="row.created_at" /></template>
    </el-table-column>
    <el-table-column label="操作" width="100" fixed="right">
      <template #default="{ row }: { row: Application }">
        <el-button link type="primary" @click="router.push(`/applications/${row.id}`)">详情</el-button>
      </template>
    </el-table-column>
  </DataTable>

  <el-dialog v-model="newDialog.visible" title="新建应用" width="480">
    <el-form label-position="top">
      <el-form-item label="应用名" required>
        <el-input v-model="newDialog.form.name" placeholder="例如：team-foo-agent" />
      </el-form-item>
      <el-form-item label="所属团队">
        <el-input v-model="newDialog.form.team" placeholder="例如：foo" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="newDialog.form.description" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="newDialog.visible = false">取消</el-button>
      <el-button type="primary" :loading="newDialog.submitting" @click="onCreate">创建</el-button>
    </template>
  </el-dialog>
</template>
```

- [ ] **Step 3: ApplicationDetailPage.vue**

```vue
<!-- src/views/applications/ApplicationDetailPage.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getApplication, type Application } from '@/api/applications';
import PageHeader from '@/components/common/PageHeader.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import Icon from '@/components/icons/Icon.vue';

const route = useRoute();
const router = useRouter();
const app = ref<Application | null>(null);

async function load() {
  app.value = await getApplication(Number(route.params.id));
}
onMounted(load);
</script>

<template>
  <el-button link @click="router.back()" style="margin-bottom: 12px;">
    <Icon name="chevron-left" :size="14" /> 返回
  </el-button>

  <div v-if="app">
    <PageHeader :title="app.name" :description="`团队：${app.team || '—'}`" />

    <div class="overview">
      <div class="overview__row">
        <div class="overview__label">应用 ID</div>
        <div class="overview__value mono">{{ app.id }}</div>
      </div>
      <div class="overview__row">
        <div class="overview__label">描述</div>
        <div class="overview__value">{{ app.description || '—' }}</div>
      </div>
      <div class="overview__row">
        <div class="overview__label">创建时间</div>
        <div class="overview__value"><RelativeTime :value="app.created_at" /></div>
      </div>
      <div class="overview__row">
        <div class="overview__label">创建人 ID</div>
        <div class="overview__value">{{ app.owner_user_id }}</div>
      </div>
    </div>

    <div style="margin-top: 24px;">
      <h3 style="margin-bottom: 12px;">API Keys</h3>
      <p class="text-secondary" style="font-size: 13px;">
        请到
        <router-link :to="{ name: 'ApiKeyList', query: { application_id: app.id } }">API Key 管理</router-link>
        查看本应用的密钥。
      </p>
    </div>

    <div style="margin-top: 24px;">
      <h3 style="margin-bottom: 12px;">服务权限</h3>
      <p class="text-secondary" style="font-size: 13px;">
        v1 上线后可在此为本应用授权可调用的服务。
      </p>
    </div>
  </div>
</template>

<style scoped>
.overview {
  background: var(--color-surface);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-base);
}
.overview__row {
  display: flex;
  padding: var(--space-3) var(--space-5);
  border-bottom: 1px solid var(--color-gray-100);
}
.overview__row:last-child { border-bottom: none; }
.overview__label {
  width: 160px;
  color: var(--color-gray-500);
  font-size: var(--text-sm);
}
.overview__value {
  flex: 1;
  font-size: var(--text-sm);
}
</style>
```

- [ ] **Step 4: dev 验证 + 提交**

```bash
pnpm dev
```

登录后点 "应用" → 看到 smoke 的 smoke-app；点详情 → 显示 metadata。新建应用 → 列表多一行。

```bash
cd /dataspace/kqspace/MCPsys
git add services/web/src/api/applications.ts services/web/src/views/applications/
git commit -m "feat(web): application list + detail pages"
```

---

### Task 14: API Key 列表 + 签发流程（含一次性明文模态框）

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/web/src/api/api-keys.ts`
- Create: `/dataspace/kqspace/MCPsys/services/web/src/components/feature/ApiKeyIssueModal.vue`
- Modify: `/dataspace/kqspace/MCPsys/services/web/src/views/api-keys/ApiKeyListPage.vue`

- [ ] **Step 1: api/api-keys.ts**

```ts
// /dataspace/kqspace/MCPsys/services/web/src/api/api-keys.ts
import { client } from './client';
import type { PaginatedList } from './types';

export type OwnerType = 'user' | 'application';

export interface ApiKey {
  id: number;
  key_prefix: string;
  name: string;
  owner_type: OwnerType;
  owner_id: number;
  scopes: Record<string, unknown> | null;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export function listApiKeys(params?: { owner_type?: OwnerType; owner_id?: number }): Promise<PaginatedList<ApiKey>> {
  return client.get('/api/v1/api-keys', { params }).then((r) => r.data);
}

export interface IssueApiKeyPayload {
  name: string;
  owner_type: OwnerType;
  owner_id: number;
  expires_at?: string;
}

export interface IssueApiKeyResponse extends ApiKey {
  plaintext: string;
}

export function issueApiKey(payload: IssueApiKeyPayload): Promise<IssueApiKeyResponse> {
  return client.post('/api/v1/api-keys', payload).then((r) => r.data);
}

export function revokeApiKey(id: number): Promise<void> {
  return client.delete(`/api/v1/api-keys/${id}`).then(() => undefined);
}
```

- [ ] **Step 2: ApiKeyIssueModal.vue（spec §6.7、§7.2 的关键交互）**

```vue
<!-- src/components/feature/ApiKeyIssueModal.vue -->
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
      <template #footer>
        <el-button @click="emit('update:modelValue', false)">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">签发</el-button>
      </template>
    </template>

    <template v-else>
      <div class="plaintext-warning">
        <Icon name="alert-triangle" :size="20" color="var(--color-warning)" />
        <div>
          <div class="plaintext-warning__title">此密钥只显示这一次</div>
          <div class="plaintext-warning__desc">请立即复制并妥善保存。关闭后无法再次查看，需要重新签发新密钥。</div>
        </div>
      </div>
      <div class="plaintext-box">
        <span class="mono">{{ result?.plaintext }}</span>
        <CopyButton :text="result?.plaintext ?? ''" size="default" />
      </div>
      <template #footer>
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
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--color-gray-50);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-base);
  font-size: var(--text-base);
  word-break: break-all;
}
</style>
```

- [ ] **Step 3: ApiKeyListPage.vue**

```vue
<!-- src/views/api-keys/ApiKeyListPage.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { listApiKeys, revokeApiKey, type ApiKey } from '@/api/api-keys';
import PageHeader from '@/components/common/PageHeader.vue';
import DataTable from '@/components/common/DataTable.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import CopyButton from '@/components/common/CopyButton.vue';
import ApiKeyIssueModal from '@/components/feature/ApiKeyIssueModal.vue';
import Icon from '@/components/icons/Icon.vue';
import { ElMessage, ElMessageBox } from 'element-plus';

const route = useRoute();
const items = ref<ApiKey[]>([]);
const loading = ref(false);
const issueOpen = ref(false);

async function load() {
  loading.value = true;
  try {
    items.value = (await listApiKeys()).items;
  } finally {
    loading.value = false;
  }
}

async function onRevoke(key: ApiKey) {
  await ElMessageBox.confirm(`确认吊销 "${key.name}" (${key.key_prefix}...)？此操作不可逆。`, '吊销 API Key', {
    type: 'warning',
    confirmButtonText: '吊销',
    cancelButtonText: '取消',
  });
  await revokeApiKey(key.id);
  ElMessage.success('已吊销');
  await load();
}

onMounted(load);
</script>

<template>
  <PageHeader title="API Key" description="所有签发的 API Key；密钥明文只在签发时显示一次">
    <template #actions>
      <el-button type="primary" @click="issueOpen = true">
        <Icon name="plus" :size="14" /> 签发新 Key
      </el-button>
    </template>
  </PageHeader>

  <DataTable :data="items" :loading="loading">
    <el-table-column label="Prefix" width="180">
      <template #default="{ row }: { row: ApiKey }">
        <span class="mono">{{ row.key_prefix }}...</span>
        <CopyButton :text="row.key_prefix" />
      </template>
    </el-table-column>
    <el-table-column prop="name" label="名称" width="200" />
    <el-table-column label="归属" width="160">
      <template #default="{ row }: { row: ApiKey }">
        {{ row.owner_type }} #{{ row.owner_id }}
      </template>
    </el-table-column>
    <el-table-column label="最近使用" width="140">
      <template #default="{ row }: { row: ApiKey }"><RelativeTime :value="row.last_used_at" /></template>
    </el-table-column>
    <el-table-column label="状态" width="100">
      <template #default="{ row }: { row: ApiKey }">
        <StatusTag :status="row.revoked_at ? 'revoked' : 'active'" />
      </template>
    </el-table-column>
    <el-table-column label="创建时间" width="140">
      <template #default="{ row }: { row: ApiKey }"><RelativeTime :value="row.created_at" /></template>
    </el-table-column>
    <el-table-column label="操作" width="100" fixed="right">
      <template #default="{ row }: { row: ApiKey }">
        <el-button v-if="!row.revoked_at" link type="danger" @click="onRevoke(row)">吊销</el-button>
        <span v-else class="text-tertiary">已吊销</span>
      </template>
    </el-table-column>
  </DataTable>

  <ApiKeyIssueModal
    v-model="issueOpen"
    :default-application-id="Number(route.query.application_id) || undefined"
    @issued="load"
  />
</template>
```

- [ ] **Step 4: dev 验证签发流程**

```bash
pnpm dev
```

操作：
1. 进入 API Key 页 → 列表显示 smoke 留下的 1-2 个
2. 点 "签发新 Key" → 表单，填名 "test-key"，选 application "smoke-app" → 签发
3. **验证关键交互**：弹出明文模态框，明文显示完整（`mcpk_xxxx...`），点遮罩或 ESC 不能关闭，只能点 "我已保存，关闭"
4. 关掉后再点哪个新 key，**找不到明文**（不能再次显示）
5. 点已有 key 的 "吊销" → 确认 → 状态变 "已吊销"

- [ ] **Step 5: 提交**

```bash
cd /dataspace/kqspace/MCPsys
git add services/web/src/api/api-keys.ts services/web/src/components/feature/ApiKeyIssueModal.vue services/web/src/views/api-keys/
git commit -m "feat(web): api key list + one-time plaintext issuance flow"
```

---

### Task 15: 调用日志列表（带筛选）

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/web/src/api/call-logs.ts`
- Modify: `/dataspace/kqspace/MCPsys/services/web/src/views/call-logs/CallLogListPage.vue`

- [ ] **Step 1: api/call-logs.ts**

```ts
// /dataspace/kqspace/MCPsys/services/web/src/api/call-logs.ts
import { client } from './client';
import type { PaginatedList } from './types';

export type CallStatus = 'success' | 'error' | 'timeout';

export interface CallLog {
  id: string;
  ts: string;
  api_key_id: number | null;
  application_id: number | null;
  user_id: number | null;
  service_id: number;
  service_slug?: string;
  service_version: string | null;
  tool_name: string | null;
  request_id: string | null;
  status: CallStatus;
  http_status: number | null;
  error_code: string | null;
  error_message: string | null;
  duration_ms: number;
  request_bytes: number;
  response_bytes: number;
  client_ip: string | null;
}

export interface CallLogQuery {
  service_id?: number;
  status?: CallStatus;
  api_key_id?: number;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}

export function queryCallLogs(params: CallLogQuery): Promise<PaginatedList<CallLog>> {
  return client.get('/api/v1/call-logs', { params }).then((r) => r.data);
}
```

- [ ] **Step 2: CallLogListPage.vue**

```vue
<!-- src/views/call-logs/CallLogListPage.vue -->
<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { queryCallLogs, type CallLog, type CallStatus } from '@/api/call-logs';
import { listServices, type McpService } from '@/api/services';
import PageHeader from '@/components/common/PageHeader.vue';
import DataTable from '@/components/common/DataTable.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import Icon from '@/components/icons/Icon.vue';
import { formatDateTime, formatDuration } from '@/utils/format';
import dayjs from 'dayjs';

const items = ref<CallLog[]>([]);
const total = ref(0);
const loading = ref(false);
const services = ref<McpService[]>([]);

const filters = reactive<{
  range: '1h' | '24h' | '7d' | 'all';
  status: CallStatus | '';
  service_id: number | '';
  page: number;
  pageSize: number;
}>({
  range: '24h',
  status: '',
  service_id: '',
  page: 1,
  pageSize: 50,
});

async function load() {
  loading.value = true;
  try {
    const params: Record<string, unknown> = {
      limit: filters.pageSize,
      offset: (filters.page - 1) * filters.pageSize,
    };
    if (filters.status) params.status = filters.status;
    if (filters.service_id) params.service_id = filters.service_id;
    if (filters.range !== 'all') {
      const map = { '1h': 1, '24h': 24, '7d': 24 * 7 };
      params.from = dayjs().subtract(map[filters.range], 'hour').toISOString();
    }
    const resp = await queryCallLogs(params);
    items.value = resp.items;
    total.value = resp.total;
  } finally {
    loading.value = false;
  }
}

async function loadServices() {
  services.value = (await listServices()).items;
}

onMounted(async () => {
  await loadServices();
  await load();
});

function isSlowCall(ms: number) {
  return ms > 1000;
}

function getServiceSlug(id: number): string {
  return services.value.find((s) => s.id === id)?.slug ?? `#${id}`;
}
</script>

<template>
  <PageHeader title="调用日志" description="所有 MCP 调用的明细记录" />

  <div class="filter-bar">
    <el-select v-model="filters.range" style="width: 140px;" @change="load">
      <el-option label="最近 1 小时" value="1h" />
      <el-option label="最近 24 小时" value="24h" />
      <el-option label="最近 7 天" value="7d" />
      <el-option label="全部" value="all" />
    </el-select>
    <el-select v-model="filters.service_id" placeholder="服务" clearable style="width: 200px;" @change="load">
      <el-option v-for="s in services" :key="s.id" :value="s.id" :label="s.slug" />
    </el-select>
    <el-select v-model="filters.status" placeholder="状态" clearable style="width: 120px;" @change="load">
      <el-option label="success" value="success" />
      <el-option label="error" value="error" />
      <el-option label="timeout" value="timeout" />
    </el-select>
    <div style="flex: 1" />
    <el-button @click="load"><Icon name="refresh-cw" :size="14" /> 刷新</el-button>
  </div>

  <DataTable
    :data="items"
    :loading="loading"
    :total="total"
    :page="filters.page"
    :page-size="filters.pageSize"
    @update:page="(p: number) => { filters.page = p; load(); }"
    @update:page-size="(s: number) => { filters.pageSize = s; load(); }"
  >
    <el-table-column label="时间" width="180">
      <template #default="{ row }: { row: CallLog }">
        <span class="mono" style="font-size: 12px;">{{ formatDateTime(row.ts) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="服务" width="200">
      <template #default="{ row }: { row: CallLog }">
        <span class="mono">{{ getServiceSlug(row.service_id) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="API Key" width="140">
      <template #default="{ row }: { row: CallLog }">
        <span class="mono text-secondary">#{{ row.api_key_id ?? '—' }}</span>
      </template>
    </el-table-column>
    <el-table-column label="状态" width="100">
      <template #default="{ row }: { row: CallLog }"><StatusTag :status="row.status" /></template>
    </el-table-column>
    <el-table-column label="HTTP" width="80">
      <template #default="{ row }: { row: CallLog }">
        <span class="mono">{{ row.http_status ?? '—' }}</span>
      </template>
    </el-table-column>
    <el-table-column label="耗时" width="100">
      <template #default="{ row }: { row: CallLog }">
        <span :style="{ color: isSlowCall(row.duration_ms) ? 'var(--color-error)' : 'var(--color-gray-700)' }">
          {{ formatDuration(row.duration_ms) }}
        </span>
      </template>
    </el-table-column>
    <el-table-column label="工具" width="160">
      <template #default="{ row }: { row: CallLog }">{{ row.tool_name ?? '—' }}</template>
    </el-table-column>
    <el-table-column label="错误" min-width="200" show-overflow-tooltip>
      <template #default="{ row }: { row: CallLog }">
        <span v-if="row.error_message" class="text-secondary">{{ row.error_message }}</span>
        <span v-else>—</span>
      </template>
    </el-table-column>
  </DataTable>
</template>

<style scoped>
.filter-bar {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-4);
}
</style>
```

- [ ] **Step 3: dev 验证 + 提交**

```bash
pnpm dev
```

进入 "调用日志" → 列表渲染 smoke 留下的几条记录；切时间范围、按 service 过滤生效。

```bash
cd /dataspace/kqspace/MCPsys
git add services/web/src/api/call-logs.ts services/web/src/views/call-logs/
git commit -m "feat(web): call logs page with filters"
```

---

### Task 16: 用户管理（admin only）

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/web/src/api/users.ts`
- Modify: `/dataspace/kqspace/MCPsys/services/web/src/views/users/UserListPage.vue`
- Modify: `/dataspace/kqspace/MCPsys/services/web/src/views/users/UserDetailPage.vue`

- [ ] **Step 1: api/users.ts**

```ts
// /dataspace/kqspace/MCPsys/services/web/src/api/users.ts
import { client } from './client';
import type { PaginatedList, Role, User, UserStatus } from './types';

export function listUsers(): Promise<PaginatedList<User>> {
  return client.get('/api/v1/users').then((r) => r.data);
}

export function getUser(id: number): Promise<User> {
  return client.get(`/api/v1/users/${id}`).then((r) => r.data);
}

export interface CreateUserPayload {
  username: string;
  password: string;
  role: Role;
  status?: UserStatus;
}

export function createUser(payload: CreateUserPayload): Promise<User> {
  return client.post('/api/v1/users', payload).then((r) => r.data);
}

export interface UpdateUserPayload {
  role?: Role;
  status?: UserStatus;
  password?: string;
}

export function updateUser(id: number, payload: UpdateUserPayload): Promise<User> {
  return client.put(`/api/v1/users/${id}`, payload).then((r) => r.data);
}
```

- [ ] **Step 2: UserListPage.vue**

```vue
<!-- src/views/users/UserListPage.vue -->
<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { listUsers, createUser, type CreateUserPayload } from '@/api/users';
import type { User, Role } from '@/api/types';
import { useAuthStore } from '@/stores/auth';
import PageHeader from '@/components/common/PageHeader.vue';
import DataTable from '@/components/common/DataTable.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import Icon from '@/components/icons/Icon.vue';
import { ROLE_LABELS } from '@/utils/constants';
import { ElMessage } from 'element-plus';

const router = useRouter();
const auth = useAuthStore();
const items = ref<User[]>([]);
const loading = ref(false);

const newDialog = reactive({
  visible: false,
  submitting: false,
  form: { username: '', password: '', role: 'viewer' as Role, status: 'active' as 'active' | 'disabled' },
});

async function load() {
  loading.value = true;
  try {
    items.value = (await listUsers()).items;
  } finally {
    loading.value = false;
  }
}

async function onCreate() {
  if (!newDialog.form.username || !newDialog.form.password) {
    ElMessage.warning('请填写用户名和密码');
    return;
  }
  newDialog.submitting = true;
  try {
    await createUser(newDialog.form as CreateUserPayload);
    ElMessage.success('用户创建成功');
    newDialog.visible = false;
    newDialog.form = { username: '', password: '', role: 'viewer', status: 'active' };
    await load();
  } finally {
    newDialog.submitting = false;
  }
}

onMounted(load);
</script>

<template>
  <PageHeader title="用户" description="管理系统中的本地账号">
    <template #actions>
      <el-button type="primary" @click="newDialog.visible = true">
        <Icon name="plus" :size="14" /> 新建用户
      </el-button>
    </template>
  </PageHeader>

  <DataTable :data="items" :loading="loading">
    <el-table-column prop="username" label="用户名" width="200">
      <template #default="{ row }: { row: User }">
        <router-link :to="`/users/${row.id}`" class="mono">{{ row.username }}</router-link>
        <el-tag v-if="row.id === auth.user?.id" size="small" effect="plain" style="margin-left: 8px;">我自己</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="角色" width="120">
      <template #default="{ row }: { row: User }">{{ ROLE_LABELS[row.role] ?? row.role }}</template>
    </el-table-column>
    <el-table-column label="状态" width="100">
      <template #default="{ row }: { row: User }"><StatusTag :status="row.status" /></template>
    </el-table-column>
    <el-table-column label="上次登录" width="160">
      <template #default="{ row }: { row: User }"><RelativeTime :value="row.last_login_at" /></template>
    </el-table-column>
    <el-table-column label="创建时间" width="160">
      <template #default="{ row }: { row: User }"><RelativeTime :value="row.created_at" /></template>
    </el-table-column>
    <el-table-column label="操作" width="100" fixed="right">
      <template #default="{ row }: { row: User }">
        <el-button link type="primary" @click="router.push(`/users/${row.id}`)">编辑</el-button>
      </template>
    </el-table-column>
  </DataTable>

  <el-dialog v-model="newDialog.visible" title="新建用户" width="480">
    <el-form label-position="top">
      <el-form-item label="用户名" required>
        <el-input v-model="newDialog.form.username" autocomplete="off" />
      </el-form-item>
      <el-form-item label="初始密码" required>
        <el-input v-model="newDialog.form.password" type="password" show-password autocomplete="new-password" />
      </el-form-item>
      <el-form-item label="角色">
        <el-select v-model="newDialog.form.role" style="width: 100%;">
          <el-option label="管理员（admin）" value="admin" />
          <el-option label="运维（operator）" value="operator" />
          <el-option label="只读（viewer）" value="viewer" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="newDialog.visible = false">取消</el-button>
      <el-button type="primary" :loading="newDialog.submitting" @click="onCreate">创建</el-button>
    </template>
  </el-dialog>
</template>
```

- [ ] **Step 3: UserDetailPage.vue（编辑 role/status，重置密码；不能改自己）**

```vue
<!-- src/views/users/UserDetailPage.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getUser, updateUser } from '@/api/users';
import type { User, Role, UserStatus } from '@/api/types';
import { useAuthStore } from '@/stores/auth';
import PageHeader from '@/components/common/PageHeader.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import Icon from '@/components/icons/Icon.vue';
import { ROLE_LABELS } from '@/utils/constants';
import { ElMessage } from 'element-plus';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const user = ref<User | null>(null);
const editRole = ref<Role>('viewer');
const editStatus = ref<UserStatus>('active');
const newPassword = ref('');
const saving = ref(false);

async function load() {
  user.value = await getUser(Number(route.params.id));
  editRole.value = user.value.role;
  editStatus.value = user.value.status;
}

const isSelf = () => user.value?.id === auth.user?.id;

async function onSave() {
  if (!user.value) return;
  if (isSelf()) {
    ElMessage.warning('不能修改自己的角色或状态');
    return;
  }
  saving.value = true;
  try {
    await updateUser(user.value.id, {
      role: editRole.value,
      status: editStatus.value,
      password: newPassword.value || undefined,
    });
    ElMessage.success('已保存');
    newPassword.value = '';
    await load();
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <el-button link @click="router.back()" style="margin-bottom: 12px;">
    <Icon name="chevron-left" :size="14" /> 返回
  </el-button>
  <div v-if="user">
    <PageHeader :title="user.username" :description="`用户 ID: ${user.id}`">
      <template #actions>
        <StatusTag :status="user.status" />
      </template>
    </PageHeader>

    <div class="card-base" style="max-width: 560px;">
      <el-form label-position="top">
        <el-form-item label="角色">
          <el-select v-model="editRole" :disabled="isSelf()" style="width: 100%;">
            <el-option v-for="r in (['admin','operator','viewer'] as const)" :key="r" :value="r" :label="ROLE_LABELS[r]" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editStatus" :disabled="isSelf()" style="width: 100%;">
            <el-option label="启用" value="active" />
            <el-option label="禁用" value="disabled" />
          </el-select>
        </el-form-item>
        <el-form-item label="重置密码（留空不修改）">
          <el-input v-model="newPassword" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="上次登录">
          <RelativeTime :value="user.last_login_at" />
        </el-form-item>
        <el-form-item>
          <el-button v-if="isSelf()" disabled>不能修改自己</el-button>
          <el-button v-else type="primary" :loading="saving" @click="onSave">保存</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>
```

- [ ] **Step 4: dev 验证 + 提交**

```bash
pnpm dev
```

操作：用 admin 登录 → 进 "用户" → 看到自己 + 任何 seed 出来的；新建用户 viewer，登录验证看不到 admin 菜单；admin 编辑别人改 role 成功，编辑自己时按钮禁用。

```bash
cd /dataspace/kqspace/MCPsys
git add services/web/src/api/users.ts services/web/src/views/users/
git commit -m "feat(web): users management page (admin only)"
```

---

### Task 17: Profile + 错误页（403/404）

**Files:**
- Modify: `/dataspace/kqspace/MCPsys/services/web/src/views/profile/ProfilePage.vue`
- Modify: `/dataspace/kqspace/MCPsys/services/web/src/views/error/ForbiddenPage.vue`
- Modify: `/dataspace/kqspace/MCPsys/services/web/src/views/error/NotFoundPage.vue`

- [ ] **Step 1: ProfilePage.vue**

```vue
<!-- src/views/profile/ProfilePage.vue -->
<script setup lang="ts">
import { ref } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { updateUser } from '@/api/users';
import PageHeader from '@/components/common/PageHeader.vue';
import { ROLE_LABELS } from '@/utils/constants';
import { ElMessage } from 'element-plus';

const auth = useAuthStore();
const oldPassword = ref('');
const newPassword = ref('');
const confirmPassword = ref('');
const saving = ref(false);

async function changePassword() {
  if (!oldPassword.value || !newPassword.value) {
    ElMessage.warning('请输入旧密码和新密码');
    return;
  }
  if (newPassword.value !== confirmPassword.value) {
    ElMessage.warning('两次输入的新密码不一致');
    return;
  }
  if (!auth.user) return;
  saving.value = true;
  try {
    await updateUser(auth.user.id, { password: newPassword.value });
    ElMessage.success('密码修改成功，请重新登录');
    auth.clear();
    location.assign('/login');
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <PageHeader title="个人资料" />

  <div class="card-base" style="max-width: 560px;">
    <el-descriptions :column="1" border>
      <el-descriptions-item label="用户名">{{ auth.user?.username }}</el-descriptions-item>
      <el-descriptions-item label="角色">{{ ROLE_LABELS[auth.user?.role ?? ''] ?? auth.user?.role }}</el-descriptions-item>
      <el-descriptions-item label="状态">{{ auth.user?.status }}</el-descriptions-item>
    </el-descriptions>
  </div>

  <div class="card-base" style="max-width: 560px; margin-top: 24px;">
    <h3 style="margin-bottom: 16px;">修改密码</h3>
    <el-form label-position="top">
      <el-form-item label="旧密码">
        <el-input v-model="oldPassword" type="password" show-password autocomplete="current-password" />
      </el-form-item>
      <el-form-item label="新密码">
        <el-input v-model="newPassword" type="password" show-password autocomplete="new-password" />
      </el-form-item>
      <el-form-item label="确认新密码">
        <el-input v-model="confirmPassword" type="password" show-password autocomplete="new-password" />
      </el-form-item>
      <el-button type="primary" :loading="saving" @click="changePassword">修改密码</el-button>
    </el-form>
  </div>
</template>
```

> **注意**：MVP 阶段后端 `PUT /api/v1/users/{id}` 接受 password 字段直接更新（不验证旧密码）。如果 spec 要求验证旧密码，需在 control_plane 加一个 `POST /api/v1/auth/change-password` 端点；目前留这个 UI 占位，后端没该端点时按钮会触发 404 或 422，先记一笔，T22 文档同步标记。

- [ ] **Step 2: ForbiddenPage.vue + NotFoundPage.vue**

`ForbiddenPage.vue`:

```vue
<!-- src/views/error/ForbiddenPage.vue -->
<script setup lang="ts">
import { useRouter } from 'vue-router';
import EmptyState from '@/components/common/EmptyState.vue';
import { useI18n } from 'vue-i18n';
const { t } = useI18n();
const router = useRouter();
</script>

<template>
  <div style="padding: 80px 24px;">
    <EmptyState icon="lock" :title="t('error.forbidden.title')" :description="t('error.forbidden.description')">
      <el-button type="primary" @click="router.push('/')">回到首页</el-button>
    </EmptyState>
  </div>
</template>
```

`NotFoundPage.vue`:

```vue
<!-- src/views/error/NotFoundPage.vue -->
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
```

- [ ] **Step 3: dev 验证 + 提交**

```bash
pnpm dev
```

操作：
- 用 viewer 角色访问 `/applications` → 看到 ForbiddenPage
- 访问 `/totally-not-a-route` → 看到 NotFoundPage
- 访问 `/profile` → 看到自己资料 + 改密码表单

```bash
cd /dataspace/kqspace/MCPsys
git add services/web/src/views/profile/ services/web/src/views/error/
git commit -m "feat(web): profile + 403/404 pages"
```

---

## 阶段六：容器化与部署（T18–T20）

### Task 18: services/web/Dockerfile + 容器内 nginx.conf

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/web/Dockerfile`
- Create: `/dataspace/kqspace/MCPsys/services/web/nginx.conf`
- Modify: `/dataspace/kqspace/MCPsys/services/web/.gitignore`（确保 dist/ 被忽略）

- [ ] **Step 1: Dockerfile**

```dockerfile
# /dataspace/kqspace/MCPsys/services/web/Dockerfile

# Stage 1: build
FROM node:20-alpine AS build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@9.0.0 --activate

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# Stage 2: runtime
FROM nginx:1.27-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

- [ ] **Step 2: nginx.conf（容器内，spec §11.2）**

```nginx
# /dataspace/kqspace/MCPsys/services/web/nginx.conf
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 1024;

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 静态资源长缓存（hash 文件名保证更新）
    location ~* \.(js|css|woff2?|svg|png|jpg|jpeg|webp)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # index.html 短缓存
    location = /index.html {
        add_header Cache-Control "no-cache, must-revalidate";
    }
}
```

- [ ] **Step 3: 本地 build 验证**

```bash
cd /dataspace/kqspace/MCPsys
docker build -f services/web/Dockerfile -t mcpsys-web-test services/web/
```

期望：build 成功，无报错。

```bash
docker run --rm -p 8090:80 mcpsys-web-test
```

另一个终端：

```bash
curl -sI http://localhost:8090/
# 期望：HTTP/1.1 200 OK + Server: nginx
curl -sI http://localhost:8090/some/spa/path
# 期望：HTTP/1.1 200 OK（SPA fallback 生效）
```

Ctrl+C 停容器：`docker stop $(docker ps -q --filter ancestor=mcpsys-web-test)` 或直接 Ctrl+C。

- [ ] **Step 4: 提交**

```bash
git add services/web/Dockerfile services/web/nginx.conf
git commit -m "feat(web): multi-stage dockerfile + spa nginx config"
```

---

### Task 19: 项目根 compose.yaml + nginx.conf 接入 web 服务

**Files:**
- Modify: `/dataspace/kqspace/MCPsys/compose.yaml`
- Modify: `/dataspace/kqspace/MCPsys/nginx/nginx.conf`

- [ ] **Step 1: compose.yaml 加 web 服务**

读取当前 compose.yaml 内容，在 `nginx:` 服务**之前**插入 `web:` 服务定义；并把 nginx 的 `depends_on` 加 `web`。

修改后片段：

```yaml
  grafana:
    # ...（保持不变）

  web:
    build:
      context: ./services/web
      dockerfile: Dockerfile
    depends_on:
      - control-plane

  nginx:
    image: nginx:1.27-alpine
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    ports:
      - "8088:80"
    depends_on:
      - control-plane
      - gateway
      - grafana
      - web
```

- [ ] **Step 2: nginx/nginx.conf 加 web upstream + location 兜底**

打开 `/dataspace/kqspace/MCPsys/nginx/nginx.conf`，在 `upstream control_plane_upstream { ... }` 之后加：

```nginx
    upstream web_upstream {
        server web:80;
    }
```

并在 `server { ... }` 块的**最末尾**（在 `location /grafana/ { ... }` 之后）加：

```nginx
        # SPA 静态前端（必须放最后，以免抢前面更具体的 location）
        location / {
            proxy_pass http://web_upstream;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
```

- [ ] **Step 3: 重建并启动**

```bash
cd /dataspace/kqspace/MCPsys
docker compose up -d --build web nginx
docker compose ps web nginx
```

期望：两个服务都 `Up`。`docker compose logs web --tail=20` 应看到 nginx 启动。

- [ ] **Step 4: 端到端验证**

```bash
curl -sI http://localhost:8088/                | head -3   # 期望 200，HTML
curl -sI http://localhost:8088/api/v1/docs     | head -3   # 期望 200（control-plane）
curl -s  http://localhost:8088/healthz                     # 期望 {"status":"ok"}
curl -sI http://localhost:8088/grafana/login   | head -3   # 期望 200
curl -sI http://localhost:8088/random-route    | head -3   # 期望 200（SPA fallback）
```

浏览器：`http://<host>:8088/` → 看到登录页。

- [ ] **Step 5: 提交**

```bash
git add compose.yaml nginx/nginx.conf
git commit -m "feat(deploy): add web service to compose + nginx upstream"
```

---

### Task 20: Grafana dashboard uid 固定 + 匿名 viewer 配置

**Files:**
- Modify: `/dataspace/kqspace/MCPsys/grafana/provisioning/dashboards/mcp-overview.json`
- Modify: `/dataspace/kqspace/MCPsys/compose.yaml`

- [ ] **Step 1: dashboard JSON 加固定 uid**

打开 `grafana/provisioning/dashboards/mcp-overview.json`，在第 2 行 `"title": "MCP Overview"` **之前**加 `"uid": "mcpsys-overview"`：

```json
{
  "uid": "mcpsys-overview",
  "title": "MCP Overview",
  ...
}
```

- [ ] **Step 2: compose.yaml grafana 服务加匿名配置**

找到 `grafana:` 块的 `environment:`，加 3 行：

```yaml
  grafana:
    image: grafana/grafana:10.4.5
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD}
      GF_SERVER_ROOT_URL: "%(protocol)s://%(domain)s/grafana/"
      GF_SERVER_SERVE_FROM_SUB_PATH: "true"
      GF_AUTH_ANONYMOUS_ENABLED: "true"            # 新增
      GF_AUTH_ANONYMOUS_ORG_ROLE: "Viewer"         # 新增
      GF_SECURITY_ALLOW_EMBEDDING: "true"          # 新增
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    # ... 其余不变
```

- [ ] **Step 3: 重启 grafana**

```bash
cd /dataspace/kqspace/MCPsys
docker compose up -d grafana
docker compose logs grafana --tail=20
```

期望日志含 `dashboards provisioned` 且无 panic。

- [ ] **Step 4: 验证 iframe URL 可达**

```bash
# 不带 cookie 访问匿名 viewer，应该 200 不弹登录
curl -sI "http://localhost:8088/grafana/d/mcpsys-overview/mcp-overview?theme=light&kiosk=tv" | head -3
# 期望：HTTP/1.1 200 OK
```

- [ ] **Step 5: 浏览器验证 Dashboard 页 iframe**

```bash
docker compose ps web nginx
# 都健康
```

浏览器打开 `http://<host>:8088/`，登录后进 Dashboard：iframe 内容应该是 "MCP Overview" 4 个面板（不是 Grafana 登录页）。

- [ ] **Step 6: 提交**

```bash
git add grafana/provisioning/dashboards/mcp-overview.json compose.yaml
git commit -m "feat(grafana): pin dashboard uid + enable anonymous viewer for embed"
```

---

## 阶段七：验收与文档（T21–T22）

### Task 21: 端到端验收

**Files:**
- Create: `/dataspace/kqspace/MCPsys/scripts/web-smoke.sh`

- [ ] **Step 1: 写一个快速 web smoke 脚本**

```bash
# /dataspace/kqspace/MCPsys/scripts/web-smoke.sh
#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://localhost:8088}"

echo "[web-smoke] /"
curl -sI "$BASE/" | grep -q "200 OK"

echo "[web-smoke] /favicon.svg"
curl -sI "$BASE/favicon.svg" | grep -q "200 OK"

echo "[web-smoke] SPA fallback"
curl -sI "$BASE/services/some-deep-route" | grep -q "200 OK"

echo "[web-smoke] grafana embed 200"
curl -sI "$BASE/grafana/d/mcpsys-overview/mcp-overview" | grep -q "200 OK"

echo "[web-smoke] backend api still works"
curl -fsS "$BASE/healthz" | grep -q '"ok"'

echo "[web-smoke] OK"
```

```bash
chmod +x /dataspace/kqspace/MCPsys/scripts/web-smoke.sh
/dataspace/kqspace/MCPsys/scripts/web-smoke.sh
```

期望：以 `[web-smoke] OK` 结尾。

- [ ] **Step 2: 跑全量 web 单测 + typecheck + build**

```bash
cd /dataspace/kqspace/MCPsys/services/web
pnpm test
pnpm typecheck
pnpm build
```

期望三者全 PASS。

- [ ] **Step 3: 浏览器验收清单（手工）**

按 spec §12 逐项打勾，**任何一项不通过都算未完成**：

视觉：
- [ ] 没有任何 Element Plus 默认紫色按钮
- [ ] 所有图标来自 Lucide（用 devtools 看 svg 路径是 lucide）
- [ ] 登录页符合 spec §6.1（渐变底、卡片、品牌字、480px 宽、12px 圆角）
- [ ] 1280×720 分辨率所有页面无横向滚动

功能：
- [ ] 13 个路由可达
- [ ] 未登录访问 `/services` → 跳 `/login?redirect=/services`
- [ ] 401 拦截（手动用 devtools 改 token 为 'X' 后访问 /services）→ 自动跳 login，无重复 toast
- [ ] viewer 角色登录 → 看不到"接入管理"、"系统管理"、"调用日志"
- [ ] admin 创建 application → 列表多一行
- [ ] admin 签 API Key → 明文模态框出现，关掉后再无法看到明文
- [ ] admin 吊销 API Key → 状态变 "已吊销"
- [ ] Dashboard iframe 显示 4 个 Grafana 面板（不是登录页）
- [ ] 调用日志按时间 / 服务 / 状态过滤生效
- [ ] admin 编辑别人 role → 保存后列表刷新；编辑自己时按钮禁用

工程：
- [ ] `pnpm build` 通过 + `pnpm vue-tsc --noEmit` 通过
- [ ] `pnpm test` 通过（至少 5 个单测）
- [ ] `docker compose build web && docker compose up -d web` 起容器

- [ ] **Step 4: 提交脚本**

```bash
cd /dataspace/kqspace/MCPsys
git add scripts/web-smoke.sh
git commit -m "test(web): add web smoke script"
```

---

### Task 22: README + deployment.md 更新

**Files:**
- Modify: `/dataspace/kqspace/MCPsys/README.md`
- Modify: `/dataspace/kqspace/MCPsys/docs/deployment.md`

- [ ] **Step 1: README 更新**

在 `README.md` 的 Endpoints 表（第 27 行附近）加一行：

```md
| URL | Purpose |
|---|---|
| `http://localhost:8088/` | Web 管理后台 |             ← 新增（放表格首行）
| `http://localhost:8088/healthz` | Control-plane health |
| `http://localhost:8088/gw/healthz` | Gateway health |
| `http://localhost:8088/api/v1/...` | Management API (JWT) |
| `http://localhost:8088/api/v1/docs` | Swagger UI |       ← 新增
| `http://localhost:8088/mcp/{slug}` | MCP traffic gateway (API Key) |
| `http://localhost:8088/grafana/` | Monitoring dashboard |
```

在 Development 区块前加一段 Web 开发说明：

```md
### Web 前端开发

```bash
# 启动后端 stack（一次）
docker compose up -d

# dev 模式（HMR）
cd services/web
pnpm install
pnpm dev    # http://localhost:5173

# build + 类型检查 + 单测
pnpm build && pnpm typecheck && pnpm test
```
```

- [ ] **Step 2: deployment.md 更新**

在 `docs/deployment.md` §6"健康验证"那张验证 URL 表里加 Web 入口：

```md
| Web 管理后台 | `http://<host>:8088/` | 浏览器进站 |
```

在 §13 "关键文件速查" 加：

```
services/web/                         # Vue 3 管理后台
services/web/Dockerfile
services/web/src/
docs/specs/2026-05-06-web-admin-design.md   # 设计文档
```

- [ ] **Step 3: 提交**

```bash
cd /dataspace/kqspace/MCPsys
git add README.md docs/deployment.md
git commit -m "docs: add web admin endpoints + dev workflow"
```

---

## 验收清单（MVP 完成标准）

跑完所有 22 个 task 后，按 spec §12 全量打勾。整体 4 类验收：

- **功能完成度**：8 项（spec §12.1）
- **视觉品质**：5 项（spec §12.2）
- **工程质量**：4 项（spec §12.3）
- **安全 / 健壮**：4 项（spec §12.4）

总计 21 项，**任何 1 项不过都算未完成**。

跑完整冒烟（后端 + 前端）：

```bash
cd /dataspace/kqspace/MCPsys
PASSWORD='<你 seed 时的密码>' ./scripts/smoke.sh       # 后端
./scripts/web-smoke.sh                                  # 前端
```

---

## 后续（v1 工作，本计划不涉及）

- 细粒度权限管理 UI（service_permissions 表 + 授权对话框）
- 限流策略 UI（rate_limit_policies）
- 配置中心 UI（service_configs + Fernet 加密 + 热下发）
- 审计事件查询 UI
- 调用日志详情抽屉（含 request/response body 查看 + 脱敏）
- 监控面板扩展（P50/P95/P99、按调用方分布、按 tool 分布）
- 服务版本管理 UI
- 接入 Grafana auth.proxy 替代匿名（更安全）
- WebSocket 实时调用流（Dashboard 顶栏的 "live tail"）
