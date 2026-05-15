# Web 管理后台 — 设计文档

- **作者**: elainecloud001@outlook.com
- **日期**: 2026-05-06
- **状态**: Draft（待评审）
- **范围**: MCPsys 管理后台前端 UI（MVP 阶段）
- **关联 spec**: `docs/specs/2026-04-30-mcp-management-system-design.md` §2.2、§6 MVP

> **2026-05-15 部分被取代**：本文中关于「DashboardPage 嵌入 Grafana iframe」（§FE-AD-6、§7.3、§§ 仪表盘相关）已在 v1-d
> 中替换为前端原生 ECharts 可视化。详见 `docs/specs/2026-05-12-v1d-native-visualization-design.md`。其余前端架构（路由、布局、
> 表单约定、列表 + 详情模式）仍然生效。

---

## 1. 背景与目标

### 1.1 背景

MCPsys 后端 MVP 已经在 2026-05-06 完成部署验收：control-plane / gateway / postgres / redis / grafana / nginx 全栈起栈，冒烟脚本端到端通过，关键鉴权边界已落实。当前所有管理操作（建 application、签 API Key、查调用日志）只能通过 curl 完成，无法交付给运维同事和管理员日常使用。

### 1.2 目标

按重要性排序：

1. **替代 curl**：把 spec §6 MVP 的全部管理操作（认证、应用 / 服务 / API Key / 调用日志 / 用户）变成可点击的页面
2. **嵌入 Grafana 仪表盘**：在站内呈现 "MCP Overview"，避免运维在两套站点间来回跳转
3. **视觉品质**：达到企业内部工具中"明显高于平均水准"的美观度，不是默认主题套个 logo 就交付
4. **为 v1 留扩展位**：权限管理、配置中心、审计事件、服务版本管理 4 个 v1 模块在导航中保留占位但灰色化，不影响 MVP 体验

### 1.3 非目标

- 不做对外用户界面（系统本身只对内）
- 不做移动端响应式（运维同事都用桌面端，最低支持 1280×720）
- 不做实时调用流（spec §2.2 提的 WebSocket 推迟到 v1）
- 不做暗色主题（产品定位决定永久只支持亮色；样式系统不为暗色留模板，避免无谓复杂度）
- 不做国际化双语（中文为主，文案落地用 vue-i18n 但只装一份中文资源）
- 不做 SSR（站内工具，CSR 即可）

### 1.4 约束

| 维度 | 约束 |
|---|---|
| 框架 | Vue 3.4+ + Vite 5+ + TypeScript |
| 组件库 | Element Plus 2.7+（中后台事实标准，组件齐） |
| 图标 | Lucide（开源、风格统一），不用 Element Plus 自带或 emoji |
| 部署形态 | 独立容器 `services/web/`，nginx 反代 `/` 到该容器 |
| 主题 | CSS Variables 驱动，永久亮色单主题，不预留暗色切换 |
| 浏览器 | Chrome/Edge 最新两版、Safari 17+；不兼容 IE |
| 包管理 | pnpm（lockfile 体积友好；workspace 兼容性好） |
| 后端契约 | OpenAPI 暴露在 `/api/v1/openapi.json`，前端用代码生成不强制；MVP 手写 axios 包装 |

---

## 2. 整体架构

### 2.1 在 compose 拓扑中的位置

```
                                    ┌────────────────────────┐
                              ┌────►│  web (nginx:alpine)    │
                              │     │  serves dist/* on :80  │
┌──────────┐   :8088     ┌────┴──┐  └────────────────────────┘
│  浏览器  │────────────►│ nginx │
└──────────┘             │  反代 │  ┌────────────────────────┐
                         │       │─►│  control-plane :8000   │
                         │       │  └────────────────────────┘
                         │       │  ┌────────────────────────┐
                         │       │─►│  gateway :8080         │
                         │       │  └────────────────────────┘
                         │       │  ┌────────────────────────┐
                         │       │─►│  grafana :3000         │
                         └───────┘  └────────────────────────┘
```

nginx 路由表（更新后）：

| location | 转发到 | 备注 |
|---|---|---|
| `/`（兜底） | `web:80` | **新增**，SPA 静态资源 + history fallback |
| `/api/` | `control-plane:8000` | 不变 |
| `/mcp/` | `gateway:8080` | 不变 |
| `/healthz` | `control-plane:8000/healthz` | 不变 |
| `/gw/healthz` | `gateway:8080/healthz` | 不变 |
| `/grafana/` | `grafana:3000`（不剥前缀） | 不变 |

### 2.2 dev / prod 模式

| 模式 | 前端服务 | API 来源 | 启动命令 |
|---|---|---|---|
| **dev**（推荐日常开发） | Vite dev server :5173，HMR | Vite proxy 转发 `/api`、`/mcp`、`/grafana`、`/healthz` 到 `http://localhost:8088` | `cd services/web && pnpm dev` |
| **prod**（compose 起栈） | web 容器内 nginx 服务 dist | 浏览器直接走 host:8088 的 nginx | `docker compose up -d --build web` |

dev 模式下后端 stack 仍然是 compose 跑着的，只把"前端"这一层切到本机 Vite——开发体验最好。

### 2.3 关键架构决策

| # | 决策 | 理由 |
|---|---|---|
| FE-AD-1 | 新增独立 `web` 容器，不烤进现有 nginx | 前后端构建解耦；前端改一个字不需要重 build nginx；spec §8 拓扑就是这么画的 |
| FE-AD-2 | TypeScript 而非 JS | Element Plus 类型完整；调用日志、API Key 等数据结构复杂，手动维护类型成本高 |
| FE-AD-3 | Pinia 而非 Vuex 或纯 composable | 官方推荐；TS 体验好；对 MVP 量级足够 |
| FE-AD-4 | axios + 全局 interceptor 而非 fetch | 401/403 拦截、token 注入、错误统一处理需要；fetch 自己包一层等于重复造轮子 |
| FE-AD-5 | JWT 存 `localStorage` 而非 httpOnly cookie | 内部工具，XSS 风险可接受；cookie 方案要 CSRF 防御，对 MVP 过度 |
| FE-AD-6 | Grafana 用 iframe 内嵌而非接口取数自渲染 | 复用 spec §2.2 决定（"复用 Grafana，不自研图表"）；iframe 是最直接做法 |
| FE-AD-7 | 不做接口自动生成（不接 openapi-typescript-codegen） | MVP 接口数量约 20 个，手写一层薄 axios 封装 < 1 天工作量；自动生成在小规模下徒增构建复杂度 |

---

## 3. 技术栈

### 3.1 运行时依赖

| 依赖 | 版本 | 用途 |
|---|---|---|
| vue | ^3.4 | 框架 |
| vue-router | ^4.3 | 路由 |
| pinia | ^2.1 | 状态管理（auth user、UI 偏好） |
| element-plus | ^2.7 | UI 组件库 |
| lucide-vue-next | ^0.400 | 图标 |
| axios | ^1.7 | HTTP 客户端 |
| @vueuse/core | ^10.10 | 通用 composable（useStorage, useDark 等） |
| dayjs | ^1.11 | 时间格式化（call_logs 列表） |
| vue-i18n | ^9.13 | 文案管理（即使只有中文也走 i18n，便于未来加英文） |

### 3.2 开发依赖

| 依赖 | 用途 |
|---|---|
| vite | 构建工具 |
| @vitejs/plugin-vue | Vue 单文件支持 |
| vue-tsc | 类型检查 |
| typescript | TS 编译器 |
| eslint + @vue/eslint-config-typescript | lint |
| prettier | 格式化 |
| sass | CSS 预处理（element-plus 主题覆盖需要） |
| unplugin-auto-import + unplugin-vue-components | Element Plus 按需引入 |
| vitest + @vue/test-utils | 单元测试 |

### 3.3 不引入的常见库（明确划掉）

- ❌ Tailwind CSS — 与 Element Plus 双方都要管 spacing/color，会冲突；用原子类不如直接 SFC `<style scoped>` + CSS 变量
- ❌ TanStack Query — 数据接口不复杂，简单 axios + Pinia 缓存够用；引入 vue-query 心智负担大于收益
- ❌ ECharts — Grafana 已经处理图表
- ❌ Sentry / 监控 SDK — MVP 不做前端监控，错误打 console + Element Plus message 即可

---

## 4. 视觉设计系统

> 风格定位：**Linear 极简骨架 + Supabase 状态色彩 + 中文优化**。整体克制、信息密度中等偏高、状态有色彩区分但不杂乱。

### 4.1 色板（亮色 token）

```css
/* 主色——沉稳蓝灰，做按钮、链接、聚焦环 */
--color-primary-50:  #EFF6FF;
--color-primary-100: #DBEAFE;
--color-primary-500: #3B82F6;   /* 主按钮、链接 */
--color-primary-600: #2563EB;   /* hover */
--color-primary-700: #1D4ED8;   /* active */

/* 灰阶——文字、边框、背景 */
--color-gray-50:  #F8FAFC;       /* 页面底色 */
--color-gray-100: #F1F5F9;       /* hover、divider */
--color-gray-200: #E2E8F0;       /* border */
--color-gray-300: #CBD5E1;
--color-gray-400: #94A3B8;       /* 占位、第三级文字 */
--color-gray-500: #64748B;       /* 第二级文字 */
--color-gray-600: #475569;
--color-gray-700: #334155;       /* 正文 */
--color-gray-800: #1E293B;
--color-gray-900: #0F172A;       /* 标题、强调 */

/* 状态色——Supabase 风 */
--color-success: #10B981;
--color-success-bg: #ECFDF5;
--color-warning: #F59E0B;
--color-warning-bg: #FFFBEB;
--color-error: #EF4444;
--color-error-bg: #FEF2F2;
--color-info: #6366F1;           /* 用于"提示性"消息，与主色区分 */
--color-info-bg: #EEF2FF;

/* 表面色 */
--color-surface: #FFFFFF;        /* 卡片底色 */
--color-surface-hover: #F8FAFC;
--color-overlay: rgba(15, 23, 42, 0.5);   /* 遮罩 */
```

不写暗色 token、不留 `data-theme` 选择器（产品永久亮色，§1.3）。

### 4.2 字体与字号

```css
--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI",
             "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB",
             system-ui, sans-serif;
--font-mono: "SF Mono", "JetBrains Mono", "Cascadia Code",
             Monaco, Menlo, Consolas, monospace;

--text-xs:   12px / 1.5;       /* 辅助说明、表格次要列 */
--text-sm:   13px / 1.55;      /* 表单 label、按钮 */
--text-base: 14px / 1.6;       /* 正文 */
--text-md:   16px / 1.6;       /* 卡片标题 */
--text-lg:   18px / 1.5;       /* 页面副标题 */
--text-xl:   20px / 1.4;       /* 页面主标题 */
--text-2xl:  24px / 1.3;       /* 仪表盘大数字 */
--text-3xl:  30px / 1.2;       /* 登录页品牌字 */

--font-weight-regular: 400;
--font-weight-medium:  500;    /* UI label 默认 */
--font-weight-semibold:600;    /* 标题 */
--font-weight-bold:    700;    /* 强调 */
```

中文字体调优：
- 行高比英文宽 5–10%（中文字符方块更高）
- 字号普遍上调 1px（14px 中文阅读舒适度 ≈ 13px 英文）
- letter-spacing: 0；中文不加间距

### 4.3 间距与密度

4px 基础栅格：

```css
--space-0: 0;
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
```

常见组件密度：

| 元素 | 高度 | 说明 |
|---|---|---|
| 输入框 / 按钮（默认） | 32px | Element Plus `size="default"` |
| 表格行 | 44px | 比 Element Plus 默认 40px 略宽，中文易读 |
| 顶部导航条 | 56px | |
| 侧边栏宽度 | 240px（展开）/ 64px（折叠） | |
| 卡片 padding | 20px | |
| 模态框宽度 | 480px（小）/ 640px（中）/ 800px（大） | |

### 4.4 圆角与阴影

```css
--radius-sm: 4px;     /* tag、徽章 */
--radius-base: 6px;   /* 输入框、按钮、卡片 */
--radius-md: 8px;     /* 模态框、大卡片 */
--radius-full: 9999px;

--shadow-xs: 0 1px 2px rgba(15, 23, 42, 0.04);
--shadow-sm: 0 2px 4px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04);
--shadow-md: 0 4px 8px rgba(15, 23, 42, 0.08), 0 2px 4px rgba(15, 23, 42, 0.05);
--shadow-lg: 0 12px 24px rgba(15, 23, 42, 0.10), 0 4px 8px rgba(15, 23, 42, 0.06);
```

阴影克制：列表卡片不带阴影只带 1px border；hover 升一档；模态框用 `--shadow-lg`。

### 4.5 图标使用规则

- 库：`lucide-vue-next`，所有图标统一用它
- 默认尺寸 16px（行内）/ 18px（按钮内）/ 20px（导航）/ 24px（空状态插图）
- 默认 `stroke-width: 2`；标题/强调位置用 1.75；超大装饰位置用 1.5
- 颜色继承 `currentColor`；不写死颜色
- 命名约定：`<Icon name="user" />` 包装组件（src/components/icons/Icon.vue），通过 prop 切图标；不在每个 SFC 里写 `import { User } from 'lucide-vue-next'`

### 4.6 Element Plus 主题覆盖

通过 `src/styles/element-overrides.scss` 用 SCSS 函数覆盖：

```scss
@forward 'element-plus/theme-chalk/src/common/var.scss' with (
  $colors: (
    'primary': ('base': #3B82F6),
    'success': ('base': #10B981),
    'warning': ('base': #F59E0B),
    'danger':  ('base': #EF4444),
    'info':    ('base': #6366F1),
  ),
  $border-radius: ('base': 6px, 'small': 4px, 'round': 9999px),
);
```

覆盖范围：主色、状态色、圆角、字号基线、表格 border 颜色。不动 Element Plus 组件结构、不重写组件。

### 4.7 动效

- 默认过渡：`transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1)`
- 模态/抽屉：250ms
- 不做装饰性动画（无炫技 hover 效果）；动效只用于"状态变化"
- 列表加载：用 Element Plus 的 `<el-skeleton>`，不用 spinner

---

## 5. 路由与导航

### 5.1 路由表

| path | name | 组件 | meta |
|---|---|---|---|
| `/login` | Login | views/login/LoginPage.vue | layout: 'auth', requiresAuth: false |
| `/` | Dashboard | views/dashboard/DashboardPage.vue | requiresAuth: true |
| `/services` | ServiceList | views/services/ServiceListPage.vue | requiresAuth: true |
| `/services/:id` | ServiceDetail | views/services/ServiceDetailPage.vue | requiresAuth: true |
| `/applications` | ApplicationList | views/applications/ApplicationListPage.vue | requiresAuth: true, roles: ['admin','operator'] |
| `/applications/:id` | ApplicationDetail | views/applications/ApplicationDetailPage.vue | 同上 |
| `/api-keys` | ApiKeyList | views/api-keys/ApiKeyListPage.vue | 同上 |
| `/call-logs` | CallLogList | views/call-logs/CallLogListPage.vue | 同上 |
| `/users` | UserList | views/users/UserListPage.vue | requiresAuth: true, roles: ['admin'] |
| `/users/:id` | UserDetail | views/users/UserDetailPage.vue | 同上 |
| `/profile` | Profile | views/profile/ProfilePage.vue | requiresAuth: true |
| `/403` | Forbidden | views/error/ForbiddenPage.vue | 显示无权限 |
| `/:pathMatch(.*)*` | NotFound | views/error/NotFoundPage.vue | 404 兜底 |

### 5.2 路由守卫（src/router/guards.ts）

```
beforeEach:
  1. 如果 to.meta.requiresAuth === false → next()
  2. 如果没 token → next({ name: 'Login', query: { redirect: to.fullPath } })
  3. 没 user 信息 → 调 /api/v1/auth/me 拉取，失败则清 token + 跳 Login
  4. 角色不匹配 to.meta.roles → next({ name: 'Forbidden' })
  5. 通过
```

### 5.3 导航视图

侧边栏（`AppLayout.vue` 内）：

```
┌─ Logo + "MCPsys" ──────────────┐
│                                │
│  📊 仪表盘                      │
│                                │
│  服务管理                       │
│   ├ 🧩 服务目录                 │
│   └ 📜 调用日志                 │  [admin/operator]
│                                │
│  接入管理                       │  [admin/operator]
│   ├ 📦 应用                     │
│   └ 🔑 API Key                 │
│                                │
│  系统管理                       │  [admin]
│   └ 👥 用户                     │
│                                │
│  v1 即将上线（灰色不可点）       │
│   ├ 🛡 权限管理                  │
│   ├ ⚙ 配置中心                  │
│   ├ 📋 审计事件                 │
│   └ 🔄 服务版本                 │
│                                │
└────────────────────────────────┘
```

侧边栏可折叠（顶部按钮），折叠时只显示图标 + tooltip。

顶部条：

```
[≡折叠] 服务管理 / 服务目录              🔔 通知预留  👤 admin ▼
                                                       ├ 个人资料
                                                       └ 退出登录
```

---

## 6. 各页面要点

### 6.1 Login（视觉重头）

```
                  ┌────────────────────────┐
                  │      [Logo]            │
                  │   MCPsys 管理后台       │
                  │                        │
                  │  用户名                │
                  │  ┌──────────────────┐  │
                  │  │  admin           │  │
                  │  └──────────────────┘  │
                  │                        │
                  │  密码                  │
                  │  ┌──────────────────┐  │
                  │  │  ••••••••        │  │
                  │  └──────────────────┘  │
                  │                        │
                  │  ┌──────────────────┐  │
                  │  │     登 录        │  │
                  │  └──────────────────┘  │
                  │                        │
                  │  v0.1.0 · 内部使用     │
                  └────────────────────────┘
```

- 整页背景：`linear-gradient(135deg, #F8FAFC 0%, #EFF6FF 100%)` 极淡渐变
- 卡片：480×480 居中，`--shadow-md`，圆角 12px（比常规大）
- 失败提示：表单下方 inline 红色文字，不弹 toast
- 不要"记住我"、"忘记密码"——MVP 不做

### 6.2 Dashboard

顶部 4 个 KPI 卡片：

```
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ 注册服务数    │ │ 24h 调用次数  │ │ 24h 错误率    │ │ 我的角色      │
│              │ │              │ │              │ │              │
│  12          │ │  1,420       │ │  0.7 %       │ │  admin       │
│  +2 本周     │ │  ▲ 15%       │ │  ▼ 0.3pp     │ │  上次登录…   │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

下方 iframe 嵌入 Grafana "MCP Overview"：

```html
<iframe
  src="/grafana/d/mcpsys-overview/mcp-overview?theme=light&kiosk=tv"
  style="width: 100%; height: 720px; border: none; border-radius: 8px;"
/>
```

- URL 格式 `/grafana/d/<uid>/<slug>?...`；当前 `grafana/provisioning/dashboards/mcp-overview.json` **没显式声明 `uid`** —— 实施阶段必须先在该 JSON 顶部加 `"uid": "mcpsys-overview"`，否则 Grafana 自动生成 uid 会导致 iframe URL 不可预测
- `kiosk=tv` 隐藏 Grafana 顶栏，无缝嵌入
- 用户已登录站点（同源），Grafana 跳过自身登录（前提：grafana 配 `auth.proxy` 或简单的 anonymous viewer；MVP 阶段先用 `GF_AUTH_ANONYMOUS_ENABLED=true` + viewer 角色，后续 v1 收紧）

### 6.3 服务目录（ServiceList）

| 列 | 内容 | 宽度 |
|---|---|---|
| Slug | `mono` 字体，可点击进详情 | 200 |
| 显示名 | | 240 |
| 团队 | | 120 |
| 健康 | 圆点 + 文字（绿/灰/红） | 80 |
| 状态 | tag（active / disabled） | 80 |
| 端点 | 截断显示，hover 全显 | flex |
| 操作 | "详情" 链接按钮 | 80 |

顶部：搜索框（按 slug/display_name/team 模糊）+ 筛选（health, status）+ "注册新服务" 按钮（admin/operator）。

### 6.4 服务详情（ServiceDetail）

```
┌─ 头部 ────────────────────────────────────────────────────┐
│  hr-bot                                  [编辑] [禁用]      │
│  HR Bot · 团队 hr · 🟢 healthy · last check 2分钟前        │
└──────────────────────────────────────────────────────────┘

[ 概览 ]  [ 调用统计 ]  [ 健康历史 ]  [ 版本(v1) ]

— 概览 tab —
  端点 URL          http://hr-bot.internal:8000/mcp     [复制]
  Transport         streamable_http
  Description       内部 HR 系统的 MCP 接口
  Tags              [hr] [internal]
  注册时间           2026-04-15 10:23
  最近修改           2026-05-01 14:50  by admin

— 调用统计 tab —
  最近 24h: 320 次 · 错误率 0.5% · P95 延迟 45ms
  [折线图——直接 iframe Grafana 子面板，按 service_id 过滤]
```

### 6.5 应用（ApplicationList）

表格列：name / team / 创建人 / 创建时间 / API Key 数 / 操作。"新建应用"按钮 + 表单（name, team, description）。

### 6.6 应用详情（ApplicationDetail）

- 基本信息卡
- 该应用的 API Key 列表（直接复用 ApiKeyList 组件，过滤 owner_type=application & owner_id 当前 app）
- 服务权限（v1 范围，灰色占位 + 提示文案 "v1 上线后可在此授权"）

### 6.7 API Key（ApiKeyList）

表格列：

| 列 | 内容 |
|---|---|
| Prefix | mono 字体 + 复制按钮 |
| 名称 | |
| 归属 | application "smoke-app" 或 user "admin" |
| 最近使用 | 相对时间 "2 小时前"，hover 显示绝对 |
| 状态 | active / revoked tag |
| 创建时间 | |
| 操作 | "吊销"按钮（弹确认） |

"签发新 Key" 按钮 → 表单 → **成功后必须弹一次性明文模态框**：

```
┌─ ⚠ 此密钥只显示这一次 ─────────────────┐
│                                       │
│  请立即复制并妥善保存。关闭后无法再次  │
│  查看，需要重新签发新密钥。            │
│                                       │
│  ┌──────────────────────────┐ [复制]  │
│  │ mcpk_8W3v...0qLp         │         │
│  └──────────────────────────┘         │
│                                       │
│         [我已保存，关闭]               │
└──────────────────────────────────────┘
```

模态框：
- 不能点遮罩关闭
- 不能 ESC 关闭
- 关闭按钮文字明确"我已保存，关闭"
- 关闭后立即从 Pinia/内存抹除明文，不缓存

### 6.8 调用日志（CallLogList）

顶部 sticky 筛选条：

```
[时间范围: 最近 1 小时 ▼]  [服务: 全部 ▼]  [状态: 全部 ▼]  [API Key: 全部 ▼]   [刷新]
```

表格列：

| 列 | 内容 | 宽度 |
|---|---|---|
| 时间 | 2026-05-06 12:34:56 | 180 |
| 服务 | slug + display_name | 200 |
| 调用方 | api_key prefix + application | 200 |
| 状态 | success / error / timeout（带颜色） | 80 |
| HTTP | 200 / 401 / 504… | 60 |
| 耗时 | "45ms"，超阈值（>1s）红色 | 80 |
| 工具 | tool_name | 160 |
| 操作 | "详情"（v1 才有 body 详情，MVP 弹一个简版抽屉显示 metadata） | 60 |

### 6.9 用户管理（UserList，admin only）

- 列：username / role / status / 上次登录 / 创建时间 / 操作
- "新建用户" 按钮 → 表单（username, password, role, status）
- "编辑"按钮 → 改 role / status / 重置密码
- 不能删自己（前端禁用 + 后端兜底）

### 6.10 个人资料（Profile）

简单表单：用户名（只读）、role（只读）、邮箱（v1 字段，MVP 占位）、修改密码（旧/新/确认）。

---

## 7. 关键交互

### 7.1 认证流

```
登录                                登录后维持
────                                ──────────
1. 用户输入 username/password       1. 每个 API 请求 axios 拦截器加 Authorization header
2. POST /api/v1/auth/login          2. 收到 401 响应 → 拦截器清 token → 跳 /login?redirect=<原 URL>
3. 拿到 access_token                3. 收到 403 → 显示 toast "权限不足"，不跳转
4. 写 localStorage["mcpsys_token"]  4. 用户主动退出 → 清 token + 跳 /login
5. 调 /api/v1/auth/me 拿用户信息    5. 60 分钟 JWT 过期 → 下一次 401 触发流程 2
6. 写 Pinia auth store
7. 跳 query.redirect 或 /
```

无 refresh token：MVP 接受过期重登。v1 加 refresh 机制时预留接口。

### 7.2 API Key 明文一次性显示

见 §6.7。关键：明文不进 Pinia 持久化、不进 localStorage、不进路由 query；只在 issue 接口响应到关闭模态框这段生命周期内驻留 Vue 组件 ref。

### 7.3 Grafana 嵌入

- 默认：iframe + `kiosk=tv` 参数
- 同源（站点和 Grafana 都走 8088）→ 不需要 CORS
- 用户认证：MVP 用 Grafana 匿名 viewer 角色
  - 改 `compose.yaml` grafana 服务环境变量：
    ```yaml
    GF_AUTH_ANONYMOUS_ENABLED: "true"
    GF_AUTH_ANONYMOUS_ORG_ROLE: "Viewer"
    GF_SECURITY_ALLOW_EMBEDDING: "true"
    ```
  - admin 登录后台 Grafana 仍用 `admin / GRAFANA_ADMIN_PASSWORD`，不影响
- v1 收紧：接 Grafana 的 `auth.proxy` 模式，让 nginx 透传 user 信息，不再用匿名

### 7.4 错误处理

axios response interceptor 统一处理：

| 状态 | 行为 |
|---|---|
| 2xx | 直接返回 data |
| 401 | 清 token + 跳 login + 不弹 toast（避免重复噪音） |
| 403 | toast "权限不足"，原 promise reject |
| 404 | 让调用方决定（列表查询要静默，资源查询要弹错） |
| 4xx 其他 | toast 显示 server 返回的 detail，promise reject |
| 5xx | toast "服务端错误，请稍后重试 (5xx)"，并打 console.error 全错误 |
| 网络错误 / timeout | toast "网络异常" |

### 7.5 复制到剪贴板

统一用 `@vueuse/core` 的 `useClipboard()`，复制成功后 Element Plus message 提示 "已复制"。

---

## 8. 项目结构

```
services/web/
├── Dockerfile                # multi-stage
├── nginx.conf                # SPA fallback + gzip + cache headers
├── package.json
├── pnpm-lock.yaml
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
├── index.html
├── public/
│   └── favicon.svg
├── src/
│   ├── main.ts               # bootstrap
│   ├── App.vue               # root
│   ├── env.d.ts
│   ├── styles/
│   │   ├── tokens.scss       # design tokens (CSS variables)
│   │   ├── reset.scss        # box-sizing, base typography
│   │   ├── element-overrides.scss
│   │   └── main.scss         # 总入口
│   ├── api/
│   │   ├── client.ts         # axios instance + interceptors
│   │   ├── types.ts          # 共享类型
│   │   ├── auth.ts
│   │   ├── users.ts
│   │   ├── applications.ts
│   │   ├── services.ts
│   │   ├── api-keys.ts
│   │   └── call-logs.ts
│   ├── stores/
│   │   ├── auth.ts           # token, user, login/logout
│   │   └── ui.ts             # 侧边栏折叠状态等 UI 偏好
│   ├── router/
│   │   ├── index.ts
│   │   └── guards.ts
│   ├── i18n/
│   │   ├── index.ts
│   │   └── locales/
│   │       └── zh-CN.ts
│   ├── layouts/
│   │   ├── AppLayout.vue     # 侧栏 + 顶栏 shell
│   │   └── AuthLayout.vue    # 登录页空 layout
│   ├── components/
│   │   ├── common/
│   │   │   ├── PageHeader.vue
│   │   │   ├── EmptyState.vue
│   │   │   ├── DataTable.vue       # ElTable 的薄封装，统一 loading/empty/分页样式
│   │   │   ├── StatusTag.vue       # active/disabled/revoked/healthy 等
│   │   │   ├── RelativeTime.vue
│   │   │   └── CopyButton.vue
│   │   ├── icons/
│   │   │   └── Icon.vue            # Lucide 包装
│   │   ├── nav/
│   │   │   ├── SideBar.vue
│   │   │   ├── TopBar.vue
│   │   │   └── UserMenu.vue
│   │   └── feature/                # 跨页面但偏业务的组件
│   │       ├── ApiKeyIssueModal.vue
│   │       └── HealthDot.vue
│   ├── views/
│   │   ├── login/LoginPage.vue
│   │   ├── dashboard/DashboardPage.vue
│   │   ├── services/{ServiceListPage,ServiceDetailPage}.vue
│   │   ├── applications/{ApplicationListPage,ApplicationDetailPage}.vue
│   │   ├── api-keys/ApiKeyListPage.vue
│   │   ├── call-logs/CallLogListPage.vue
│   │   ├── users/{UserListPage,UserDetailPage}.vue
│   │   ├── profile/ProfilePage.vue
│   │   └── error/{ForbiddenPage,NotFoundPage}.vue
│   └── utils/
│       ├── format.ts          # bytes / duration / date
│       ├── permissions.ts     # role 判断 helper
│       └── constants.ts
└── tests/
    ├── unit/                  # composable + util 单测
    └── integration/           # 主要页面 vue-test-utils
```

---

## 9. 状态管理 + API 层

### 9.1 Pinia stores

**`stores/auth.ts`**：
- state: `token`、`user`、`loading`
- actions: `login(username, password)`、`logout()`、`fetchMe()`、`hasRole(...roles)`
- token 用 `useStorage('mcpsys_token', '')` 自动同步 localStorage
- user 不做持久化（每次刷新重新调 /me，避免数据陈旧）

**`stores/ui.ts`**：
- state: `sidebarCollapsed`、`tableDensity`（预留）
- 用 `useStorage` 持久化偏好

不做 store-of-stores 风格的全局数据缓存（每页面自己管）。MVP 数据规模小，不做缓存复杂化。

### 9.2 API 层

`src/api/client.ts`：

```ts
const client = axios.create({
  baseURL: '/',          // 走相对路径，dev 时由 Vite proxy 转发，prod 时由 nginx
  timeout: 15_000,
});

client.interceptors.request.use((config) => {
  const auth = useAuthStore();
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`;
  }
  return config;
});

client.interceptors.response.use(
  (resp) => resp,
  (err) => {
    handleApiError(err);   // 见 §7.4
    return Promise.reject(err);
  }
);
```

每个资源一个文件，导出函数：

```ts
// src/api/applications.ts
export interface Application { id: number; name: string; team: string | null; ... }
export function listApplications(): Promise<{ items: Application[]; total: number }>;
export function createApplication(payload: { name: string; team?: string }): Promise<Application>;
export function getApplication(id: number): Promise<Application>;
```

类型从 OpenAPI 手抄；后端任何 schema 变更必须同步 PR 改前端 types。MVP 后期可考虑跑 `openapi-typescript` 生成类型校对。

---

## 10. 国际化

- 即使只有中文，所有可见文案走 `t('xxx')`，不写硬编码字符串
- 单一资源文件 `src/i18n/locales/zh-CN.ts`
- 命名约定：`<page>.<element>`，例如 `services.list.title`、`apiKeys.issue.warning`
- 不在 MVP 加英文资源；Pinia 不存 locale；vue-i18n `legacy: false` 模式（Composition API）

---

## 11. 构建与部署

### 11.1 services/web/Dockerfile

```dockerfile
# Stage 1: build
FROM node:20-alpine AS build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@latest --activate
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build       # 产出到 dist/

# Stage 2: runtime
FROM nginx:1.27-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

### 11.2 services/web/nginx.conf

```nginx
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

### 11.3 compose.yaml 改动

新增服务：
```yaml
  web:
    build:
      context: ./services/web
      dockerfile: Dockerfile
    depends_on:
      - control-plane
```

`nginx` 服务的 `depends_on` 加 `web`。

### 11.4 nginx/nginx.conf（项目根）改动

新增 `upstream` 和 `location /`：

```nginx
upstream web_upstream {
    server web:80;
}

# 在 server { ... } 块最末
location / {
    proxy_pass http://web_upstream;
    proxy_set_header Host $host;
}
```

注意 `location /` 必须放在最后，前面 `/api/` `/mcp/` `/grafana/` 等更具体的 location 优先匹配。

### 11.5 vite.config.ts dev proxy

```ts
export default defineConfig({
  plugins: [vue(), AutoImport({ resolvers: [ElementPlusResolver()] }), Components({ resolvers: [ElementPlusResolver()] })],
  server: {
    port: 5173,
    proxy: {
      '/api':     { target: 'http://localhost:8088', changeOrigin: true },
      '/mcp':     { target: 'http://localhost:8088', changeOrigin: true },
      '/grafana': { target: 'http://localhost:8088', changeOrigin: true },
      '/healthz': { target: 'http://localhost:8088', changeOrigin: true },
    },
  },
});
```

### 11.6 文档同步

完成后需要更新：

- `README.md`：Quick start 增加 `cd services/web && pnpm install && pnpm build`（compose build 时自动跑），Endpoints 表加一行 `http://<host>:8088/` → Web Admin
- `docs/deployment.md`：§7 故障排查加几条前端常见问题（白屏、404 fallback 不生效）；§13 关键文件速查加 `services/web/`

---

## 12. 验收标准

### 12.1 功能完成度

- [ ] 所有 12 个路由可达（含 403/404 兜底）
- [ ] 未登录访问受保护路由 → 跳 /login 并保留 redirect
- [ ] 401 拦截 → 自动跳 login，无重复 toast
- [ ] admin / operator / viewer 三种 role 看到的菜单项符合 §5.3 规则
- [ ] 服务、应用、API Key、用户的 CRUD 在 UI 上跑得通；操作后列表刷新
- [ ] API Key 签发后明文模态框只能点"我已保存，关闭"；关掉后再无法看到
- [ ] 调用日志列表筛选生效（时间 / 服务 / 状态）
- [ ] Dashboard 嵌入的 Grafana iframe 渲染出 4 个面板，无登录提示

### 12.2 视觉品质

- [ ] 没有任何 Element Plus 默认紫色按钮 / 默认蓝（必须是 §4.1 token 蓝）
- [ ] 所有图标来自 Lucide，无 emoji、无 Element Plus 内置图标残留
- [ ] 至少 5 个空状态有定制插图（不只是"暂无数据"）
- [ ] 登录页满足 §6.1 视觉描述（渐变底、卡片、品牌字）
- [ ] 1280×720 分辨率下所有页面无横向滚动

### 12.3 工程质量

- [ ] `pnpm build` 通过 + `pnpm vue-tsc --noEmit` 通过
- [ ] `pnpm test` 至少有 5 个核心 util / composable 单测
- [ ] `docker compose build web && docker compose up -d web` 起容器，浏览器访问 `http://<host>:8088/` 看到登录页
- [ ] dev 模式 `pnpm dev` 启动后访问 `http://localhost:5173` 可正常登录、跳转、调 API（依赖 compose 后端跑着）

### 12.4 安全 / 健壮

- [ ] localStorage 中除 `mcpsys_token` 和 UI 偏好外不存任何敏感数据
- [ ] API Key 明文不进任何持久化存储
- [ ] dev 模式不暴露 source maps 到 prod 镜像（vite.config 配 `build.sourcemap: false`）
- [ ] CSP header（nginx 加）：`default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-src 'self' http://localhost:8088 /grafana/`

---

## 13. 风险与对策

| 风险 | 对策 |
|---|---|
| Element Plus 默认风格挥之不去（即使 token 改了仍能看出"原汁原味"）| 主题覆盖采用 SCSS 入口而非运行时 CSS 变量；高频组件（Button、Table、Form）单独验证视觉效果；用截图比对盯紧 |
| Grafana iframe 同源策略导致 cookie 不通 | 已通过 nginx 同源解决；`X-Frame-Options` 必须不是 `DENY`，spec §7.3 提的 `GF_SECURITY_ALLOW_EMBEDDING=true` 必须设上 |
| Lucide 图标包过大拖累首屏 | Lucide 支持 tree-shaking，按需 import；首屏只用 < 20 个图标，gzip 后约 8KB |
| API Key 明文意外泄漏（截图、log） | 模态框样式有"水印感"提醒；明文不进 console；在错误捕获里过滤 `plaintext` 字段 |
| 后端 OpenAPI 改动前端不知道 | MVP 接受人工同步成本；v1 时引入 openapi-typescript 自动生成 + CI 校验 |
| iframe 高度自适应难调（Grafana 面板撑不开） | 用固定 720px 高度先跑；后续加 postMessage 协议让 iframe 主动汇报高度（v1） |

---

## 14. 待确认 / 后续工作

1. Grafana 匿名 viewer 是否符合公司安全规范？如果不允许匿名，MVP 直接走 Grafana auth.proxy（需要后端 nginx 配 X-WEBAUTH-USER header），实现量增加约 0.5 天
2. Logo 设计——MVP 用文字 logo `MCPsys` + 一个简单的 lucide `network` 图标占位即可，后续设计同事产出再替换
3. 是否需要"操作记录"导出 CSV？MVP 不做，记一笔
4. 是否要做"系统通知"（顶部条铃铛图标）？MVP 不做但 UI 留位
5. Pinia store 是否要做持久化 plugin 隔离？目前用 `useStorage` 单点持久，简单但分散；如果未来 store 多了再引入 `pinia-plugin-persistedstate`

---

## 附录 A — 命名约定

- 组件文件：`PascalCase.vue`
- 路由 name：`PascalCase`
- store 文件：`camelCase.ts`，store id 用 `camelCase`
- API 函数：`动词Resource`，如 `listApplications`、`createApiKey`、`revokeApiKey`
- CSS class：BEM-lite，`.page-services`、`.page-services__filter`、`.page-services--loading`
- i18n key：层级 `pageOrFeature.element`，如 `services.list.empty`、`auth.login.submit`
