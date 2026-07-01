# MCPsys 系统架构

> 本文档梳理 MCPsys 的整体架构、组件职责、关键链路与设计决策，作为新成员理解系统、维护者排障的总览入口。
>
> 配套文档：系统设计 `docs/specs/2026-04-30-mcp-management-system-design.md`、部署运维手册 `docs/deployment.md`、各版本设计/计划 `docs/specs/`、`docs/plans/`。

---

## 1. 系统定位

MCPsys 是面向内部的 **MCP（Model Context Protocol）服务管理系统**，把分散的自建 MCP 服务统一收口，集中提供：

- **服务注册**：MCP 服务以 `slug → 内网地址` 登记到控制面（支持容器自注册）。
- **凭据与鉴权**：签发 / 吊销 API Key，按应用授权可访问哪些服务（默认拒绝白名单）。
- **流量代理**：Agent 经网关统一入口调用 MCP 服务，网关负责鉴权、限流、转发。
- **可观测**：调用日志、审计事件、可视化统计看板。

设计目标量级为 MVP（≤100 QPS），单网关实例即可承载。

---

## 2. 总体架构

对外只暴露一个 nginx（宿主 `:8088`），反代到三个应用容器，外加 Postgres 与 Redis 两个基础设施容器；自建 MCP 服务作为额外容器接入同一 docker 工程、走内网直连。

```
                            ┌─────────────── nginx (:8088 对外) ───────────────┐
 浏览器 / Agent  ─────────▶ │  /                  → web（Vue3 管理后台 SPA）   │
                            │  /api/              → control-plane（管理 API）  │
                            │  /healthz           → control-plane 健康         │
                            │  /mcp/{slug}        → gateway（MCP 流量代理）     │
                            │  /gw/healthz        → gateway 健康               │
                            │  /mcp-files/{slug}/ → 对应 MCP 服务（文件下载）  │
                            └──────┬───────────────┬───────────────┬───────────┘
                                   ▼               ▼               ▼
                            control-plane       gateway          web (静态)
                                   │  ╲           │  ╱                
                          ┌────────┘   ╲         │ ╱                  
                          ▼             ▼         ▼                    
                       Postgres ◀────────────── Redis                 
                    （主数据/日志/审计）   （鉴权/限流/统计缓存/失效广播）
                          ▲                                            
                          │  内网直连 http://mcp-<slug>:8000/mcp        
                   ┌──────┴──────────────────────────────┐            
                   │  mcp-<slug> 容器（自建 MCP 服务）      │            
                   │  启动时 register.py 自注册到 control-plane          
                   └──────────────────────────────────────┘            
```

### 组件一览

| 组件 | 技术 | 对外端口 | 职责 |
|---|---|---|---|
| **nginx** | nginx 1.27-alpine | `8088`（唯一对外） | 反向代理 / 路由分发 / SPA 静态托管 / 文件下载运行时上游解析 |
| **web** | Vue 3 + Element Plus + ECharts | 容器内 :80 | 管理后台 SPA，构建后由内置 nginx 托管静态文件 |
| **control-plane** | FastAPI + SQLAlchemy(async) | 容器内 :8000 | 管理 API（JWT 鉴权）+ 两个后台 worker（健康检查、日志保留） |
| **gateway** | FastAPI + httpx | 容器内 :8080 | MCP 流量入口（API Key 鉴权）→ 鉴权 → 限流 → 转发 → 异步落日志 |
| **postgres** | postgres 16-alpine | 容器内 :5432 | 主数据、调用日志、审计事件 |
| **redis** | redis 7-alpine | 容器内 :6379 | API Key/服务/策略缓存、限流令牌桶、统计缓存、缓存失效 pub/sub |
| **mcp-\<slug\>** | FastMCP (streamable-http) | 不暴露宿主端口 | 自建 MCP 服务，内网名 `mcp-<slug>:8000`，启动自注册 |

### 代码组织（uv workspace + pnpm）

```
packages/mcpsys_shared/      # 后端共享：SQLAlchemy models / db engine / SharedSettings
services/control_plane/      # 控制面 FastAPI + alembic 迁移
services/gateway/            # 网关 FastAPI
services/web/                # Vue3 前端（pnpm，独立于 uv workspace）
mcp-services/_template/      # 新 MCP 服务脚手架模板
mcp-services/aftersales-search/  # 已接入的真实 MCP 服务
compose.yaml                 # 核心栈编排
compose.mcp.yaml             # MCP 服务编排（与 compose.yaml 合并使用）
nginx/nginx.conf             # 入口路由
scripts/                     # seed_admin / seed_user / smoke / verify_service 等
```

后端是 uv workspace（`packages/*` + `services/*`，排除 web），三个 Python 包共享 `mcpsys_shared`。前端独立用 pnpm。

---

## 3. 两条核心链路

系统有两个独立的流量平面，鉴权方式不同：

### 3.1 管理面（control-plane，JWT）

浏览器 / 自注册脚本 → nginx `/api/` → control-plane。

1. `POST /api/v1/auth/login`：用户名 + 密码，校验 bcrypt `password_hash`，签发 HS256 JWT（默认 60min）。
   - JWT payload：`{sub: user_id, role, username, iat, exp}`。
2. 后续请求带 `Authorization: Bearer <jwt>`；`deps.py` 解析 token、加载用户、`require_role(*roles)` 做角色校验。
3. 所有状态变更写审计事件（与主写入在**同一事务**内，原子）。

### 3.2 数据面（gateway，API Key）

Agent 客户端 → nginx `/mcp/{slug}` → gateway → 上游 MCP 服务。

完整管线（`services/gateway/src/gateway/routers/mcp.py`）：

```
POST /mcp/{slug}  (Authorization: Bearer mcpk_...)
  │
  1. 解析 header / body / 生成 request_id / 取 client_ip
  │
  2. 鉴权  auth.validate_api_key()
  │      ├─ Redis 命中 gw:apikey:{prefix} → 常数时间 HMAC-SHA256 比对（μs 级）
  │      └─ 未命中 → Postgres 按 key_prefix 查 → bcrypt 校验 → 回写 Redis（含 SHA-256 摘要）
  │      失败 → 401
  │
  3. 解析服务  resolver.resolve(slug)
  │      ├─ 进程内 TTL 缓存（60s）
  │      └─ 未命中 → Postgres 查 McpService（须 status=active）→ 回写缓存
  │      失败 → 404
  │
  4. 鉴权策略  policy.is_allowed(application_id, service_id)
  │      ├─ user 持有的 key（无 application_id）直接拒绝
  │      ├─ 进程内 TTL 缓存（30s）service_id → 允许的 app 集合
  │      └─ 未命中 → Postgres 查 ServicePermission（默认拒绝白名单）
  │      失败 → 403（写 denied 调用日志）
  │
  5. 限流  ratelimit.check() × 2（令牌桶，Redis Lua 原子）
  │      ├─ rl:k:{api_key_id}   按 API Key 限流
  │      └─ rl:s:{service_id}   按服务限流
  │      失败 → 429 + Retry-After（写 throttled 调用日志）；Redis 不可用则 fail-open
  │
  6. 转发  proxy.forward()
  │      ├─ 剥离 hop-by-hop header，注入 x-request-id / x-mcpsys-application / x-mcpsys-user
  │      └─ httpx POST → svc.endpoint_url（默认 30s 超时；超时→504，连接失败→502）
  │
  7. 落日志  telemetry.enqueue()  （非阻塞）
         └─ 入内存 asyncio.Queue → 后台批量 flush（100 条 / 1s）→ Postgres 批插 call_logs
```

**关键性能设计**：

- 鉴权热路径用 Redis 缓存的 SHA-256 摘要做常数时间比对，避开每次请求 ~250ms 的 bcrypt；bcrypt 仅在缓存未命中时执行一次。吊销/过期通过缓存 TT（60s）+ 每次命中也校验 `expires_at` 兜底。
- 调用日志走「内存队列 + 后台批量落库」，不阻塞请求路径；硬崩溃时有少量丢失风险（设计已接受）。

---

## 4. 数据模型

定义于 `packages/mcpsys_shared/src/mcpsys_shared/models.py`，由 control-plane 的 alembic 管理迁移（容器启动自动 `alembic upgrade head`）。

| 表 | 用途 | 关键字段 / 说明 |
|---|---|---|
| `users` | 平台用户 | `role`(admin/operator/viewer)、`status`、bcrypt `password_hash` |
| `applications` | 应用（API Key 与授权的归属主体） | `owner_user_id`、`team`、`description` |
| `api_keys` | API Key | `key_prefix`(索引) + bcrypt `key_hash`、`owner_type`(user/application)、`rate_limit_qps`、`revoked_at`/`expires_at`、`scopes`(预留) |
| `mcp_services` | MCP 服务注册表 | `slug`(唯一)、`endpoint_url`、`status`、`health_status`、`rate_limit_qps` |
| `service_permissions` | 应用×服务白名单 | 唯一约束 `(application_id, service_id)`；**有行即允许，默认拒绝**；仅从应用侧维护 |
| `call_logs` | 网关逐请求日志（高频追加） | UUID 主键；`status`(success/error/timeout/denied/throttled)、`duration_ms`、`request_body`/`response_body`(可被清理置 NULL)；**caller/service 列无外键**，独立于实体删除；多个 `ts` 复合索引 + 未清理 body 的部分索引 |
| `audit_events` | 管理操作审计 | `action`、`target_type/id`、`before`/`after`(JSONB，已脱敏)、`actor_user_id`、`ip` |

**枚举**：`UserRole`、`UserStatus`、`ApiKeyOwnerType`、`ServiceStatus`、`HealthStatus`、`TransportType`(目前仅 streamable_http)、`CallStatus`。

**保留策略（call_logs）**：metadata 永久保留、行永不删除；`request_body`/`response_body` 在超过 `CALL_LOG_BODY_RETENTION_DAYS`（默认 30 天）后被保留 worker 置 NULL。`ix_call_logs_body_unpurged` 部分索引让清理扫描只覆盖未清理的积压行。

---

## 5. 组件详解

### 5.1 control-plane（管理 API + 后台 worker）

FastAPI 应用，`src/control_plane/`。9 个路由器：

| 路由器 | 前缀 | 职责 | 角色 |
|---|---|---|---|
| `auth` | `/api/v1/auth` | `login` 签发 JWT、`me` 当前用户 | 公开 / 登录态 |
| `users` | `/api/v1/users` | 用户 CRUD、改密、角色/状态 | 创建/删除限 admin |
| `applications` | `/api/v1/applications` | 应用 CRUD + 维护 `service_permissions` 白名单 | admin/operator |
| `services` | `/api/v1/services` | 服务注册/更新/归档、健康历史、详情 | 写限 admin/operator；读放开 |
| `api_keys` | `/api/v1/api-keys` | 签发（明文只显示一次）/吊销/更新 QPS/删除 | admin/operator |
| `permissions` | `.../permissions` | 从应用侧与服务侧两个只读视角看白名单 | 各角色只读 |
| `audit_events` | `/api/v1/audit-events` | 审计查询（多维过滤、分页） | admin |
| `call_logs` | `/api/v1/call-logs` | 调用日志列表/详情 | admin/operator |
| `stats` | `/api/v1/stats` | overview / timeseries / breakdown / latency-histogram | admin/operator |

**鉴权与权限**：JWT（HS256）+ `require_role(*roles)` 依赖工厂在端点层强制角色（`deps.py`）。三角色 admin/operator/viewer，无更细粒度的租户隔离（列为 v1 未来工作）。

**审计**（`audit.py`）：所有状态变更与主写入在**同一 DB 事务**内写入 `audit_events`，主写失败则审计不产生（原子）。`before`/`after` 快照通过敏感列黑名单（`password_hash`/`key_hash`/`value_encrypted`）+ 正则守卫脱敏。

**统计与缓存**（`stats.py` + `cache_stats.py`）：read-through Redis 缓存（15m 区间 TTL 10s，其余 30s），Redis 故障时静默回退实时计算；响应头 `X-Cache: hit|miss|bypass`。支持按 service/application/api_key 过滤，区间 15m/1h/24h/7d/30d/all 各有默认聚合粒度。

**两个后台 worker**（在 FastAPI lifespan 内以 asyncio 循环运行，无 APScheduler 依赖，单轮异常被吞、循环继续）：

1. **健康检查**（`health_checker.py`）：周期向所有 active 服务 `endpoint_url` 发 JSON-RPC `initialize`，2xx/4xx→healthy、5xx/超时/连接失败→unhealthy，写回 `mcp_services.health_status` + `last_health_check_at`；状态变化时记审计事件 `SERVICE_HEALTH_CHANGE`。默认 30s 一轮、并发 8、单探 3s 超时。
2. **日志保留**（`retention.py`）：默认每小时一轮，分批（5000 行/批）把超期 call_logs 的 body 列置 NULL，仅清 body、不删行，依赖部分索引避免全表扫描。

### 5.2 gateway（MCP 流量代理）

FastAPI 应用，`src/gateway/`。核心模块与职责见 §3.2 管线。补充关键机制：

- **限流算法**：令牌桶，单条 Redis Lua 脚本原子完成「取桶 → 按 elapsed 补充 → 扣 1 令牌」。桶容量 `2×qps`（突发），Redis 键 `rl:k:{api_key_id}` / `rl:s:{service_id}`，60s 过期。服务桶拒绝时不回滚 Key 桶令牌（设计取舍）。Redis 不可用时 fail-open（放行）。
- **服务解析缓存**：进程内 `dict[slug] → (expiry, ResolvedService)`，TTL 60s。
- **策略缓存**：进程内 `dict[service_id] → frozenset(允许的 application_id)`，TTL 30s，默认拒绝。

### 5.3 缓存失效（control-plane → gateway，Redis Pub/Sub）

为兼顾「网关缓存提速」与「后台改动及时生效」，control-plane 在写入提交后向 Redis 频道发布失效消息，gateway 订阅后清理对应进程内缓存。

| 频道 | 触发点（control-plane） | gateway 动作 |
|---|---|---|
| `service:invalidate` | 服务更新 / 归档（payload=slug） | `ServiceResolver` 清该 slug |
| `policy:invalidate` | 应用创建 / 更新授权（payload=service_id） | `PolicyCache` 清该 service_id |

不变式：**publish 永远在 DB commit 之后**；publish 失败仅告警、不影响 API 成功（Redis 宕机不阻塞管理操作）。空 payload 表示清全部。API Key 缓存无主动失效，靠 TTL（60s）+ 命中时校验过期/吊销兜底。

### 5.4 web（管理后台）

Vue 3.4 + Vite 5 + Element Plus 2.7 + Pinia + Vue Router 4 + ECharts 6 + vue-i18n（zh-CN）+ TypeScript，pnpm 管理。

- **路由与布局**：`createWebHistory` SPA；路由 meta 携带 `requiresAuth`/`roles`/`layout`；`AppLayout`（SideBar+TopBar）与 `AuthLayout`（登录）按 meta 切换。守卫 `beforeEach` 处理未登录重定向、首次进入拉取当前用户、角色不足跳 403。
- **主要页面**：登录、Dashboard（KPI/时序/分布图表）、服务列表/详情、应用列表/详情、API Key 列表/详情、调用日志列表/详情、用户管理（admin）、审计事件（admin）、个人资料、403/404。
- **API 层**（`src/api/client.ts`）：axios 实例 `baseURL: '/'`，请求拦截注入 `Bearer <token>`（token 存 localStorage，VueUse `useStorage`）；响应拦截统一处理 401（清 token 跳登录）、403（权限不足提示）、5xx/4xx（错误 toast）。
- **构建与托管**：多阶段 Docker —— `node:20-alpine` 跑 `vue-tsc --noEmit && vite build` 产出 `dist/`，再 `nginx:1.27-alpine` 托管静态文件，`try_files ... /index.html` 做 SPA 回退，hash 文件名长缓存、index.html 不缓存。

### 5.5 自建 MCP 服务（mcp-services/）

每个服务是独立 docker 镜像，基于 FastMCP（streamable-http transport），监听容器内 :8000、RPC 路径 `/mcp`。接入 MCPsys 同一 docker 工程（project `mcpsys`），共享内网 `mcpsys_default`，gateway 用服务名 `mcp-<slug>:8000/mcp` 直连，**不暴露宿主端口**。鉴权/限流/日志/健康检查由 MCPsys 统一负责，服务内不重复实现。

**容器自注册**（`entrypoint.sh` → `register.py`）：容器启动时读 `service.yaml`，用 `REGISTRAR_*`（operator 角色）账号登录 control-plane，按 slug `GET` 判断后 `POST`(新建) 或 `PATCH`(更新) 把自己 upsert 到注册表。endpoint_url 自动派生为 `http://mcp-<slug>:<port><path>`。失败只告警、退避重试（默认 10 次），**绝不阻塞 MCP 服务启动**。「重启即更新」——新增/改 tool 无需注册，重建容器即可；改 slug→地址 才算「服务」变更。

> 注意：因容器会自注册，「只在后台删除但容器仍在跑」不是稳定下线方式——重启会复活。彻底下线须停/移除容器。

**示例 `aftersales-search`**：按 SN 查 CRM 售后 / MES 工序 / 设备档案 / FQC 报告。tool 模块化注册（`tools/sales_order|repair_process|device_profile|fqc_report`），FQC 报告文件经 nginx `/mcp-files/aftersales-search/` 单独下载（nginx 用变量做运行时上游解析，服务没起也不拖垮入口）。

---

## 6. 部署与运维拓扑

- **唯一对外端口 `8088`**（nginx 容器内 :80 映射）。TLS 默认由企业边缘/上层反代终结；nginx 仅监听 HTTP。
- **核心栈**：`docker compose up -d` 起 6 个服务（postgres/redis/control-plane/gateway/web/nginx）。control-plane 启动 entrypoint 先 `alembic upgrade head` 再起服务，**迁移自动**。
- **MCP 服务栈**：所有 MCP 相关 compose 操作带两个 `-f`：`docker compose -f compose.yaml -f compose.mcp.yaml <命令>`。
- **健康检查**：postgres/redis/control-plane/mcp 各有 healthcheck；gateway 依赖三者 healthy 后启动。
- **初始管理员**：`scripts/seed_admin.py`（幂等）。自注册账号用 `scripts/seed_user.py registrar <pw> operator`。
- **冒烟**：`scripts/smoke.sh` 打通「登录→建应用→注册服务→签 Key→经网关调用→落日志」全链路。
- **备份**：Postgres 用 `pg_dump`（建议每日 cron）；Redis 仅缓存，丢失无影响、重启回填。
- **扩容**：MVP 单网关实例足够（≤100 QPS）；多副本需给 nginx 上游加运行时 DNS resolver（v1 范围）。

配置入口 `.env`（见 `.env.example`）。生产**必改** `POSTGRES_PASSWORD` 与 `JWT_SECRET`（≥32 字节）。

---

## 7. 关键设计决策

1. **双平面分离**：管理面（JWT，给人/脚本）与数据面（API Key，给 Agent）物理上分到 control-plane 与 gateway 两个进程，鉴权方式与扩缩容诉求各自独立。
2. **默认拒绝白名单**：`service_permissions` 有行才允许，应用须显式授权可访问的服务；白名单只从应用侧维护、服务侧只读镜像。
3. **热路径避开 bcrypt**：API Key 鉴权用 Redis 缓存 SHA-256 摘要做常数时间比对，仅缓存未命中时算一次 bcrypt。
4. **缓存提速 + pub/sub 失效**：网关进程内缓存服务/策略、Redis 缓存 Key，control-plane 改动后经 Redis 频道广播失效；失效是 best-effort，TTL 兜底。
5. **审计与主写同事务**：强一致，无最终一致窗口；快照脱敏。
6. **日志非阻塞 + 可清理**：调用日志内存队列批量落库不阻塞请求；body 超期置 NULL、metadata 永久、行不删，兼顾排障与存储。
7. **服务归档而非删除**：删除走软归档（slug 改名 + 状态变更），保留 call_logs 历史、避免外键冲突。
8. **容器自注册**：MCP 服务自带注册逻辑，复用 control-plane 现有 API，不侵入控制面；重启即更新、免脚本免按钮。

---

## 8. 文档索引

- 系统设计与 v1 规划：`docs/specs/2026-04-30-mcp-management-system-design.md`
- 访问控制与限流：`docs/specs/2026-05-08-v1a-access-control-and-ratelimit-design.md`
- 审计事件：`docs/specs/2026-05-11-v1b-audit-events-design.md`
- 应用驱动授权：`docs/specs/2026-05-15-app-driven-authz-design.md`
- 原生可视化：`docs/specs/2026-05-12-v1d-native-visualization-design.md`
- 前端设计：`docs/specs/2026-05-06-web-admin-design.md`
- MCP 服务同栈托管方案：`docs/plans/2026-06-30-mcp-services-colocation-plan.md`
- 部署 / 运维手册：`docs/deployment.md`
- 变更记录：`docs/changes/`
