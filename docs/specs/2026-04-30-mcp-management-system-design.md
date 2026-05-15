# MCP 服务管理系统 — 设计文档

- **作者**: elainecloud001@outlook.com
- **日期**: 2026-04-30
- **状态**: Draft（待评审）
- **范围**: 企业内部 MCP 服务的注册、监控、访问控制、配置与生命周期管理

> **2026-05-15 部分被取代**：本文中关于「嵌入 Grafana 渲染调用统计」的内容已在 v1-d 中替换为前端原生 ECharts 可视化。详见
> `docs/specs/2026-05-12-v1d-native-visualization-design.md`。Grafana 容器、nginx `/grafana/` 反代、`grafana-data` volume 均已下线；
> `grafana/provisioning/` 目录暂留作参考，将在 v1-d PR6 单独清理。

---

## 1. 背景与目标

### 1.1 背景

公司内部正在推进 AI Agent 落地，越来越多业务团队基于 MCP（Model Context Protocol）协议开发服务，封装内部数据库、ERP、CRM、知识库等能力，供 AI Agent 调用。当前缺少统一的：

- 服务发现与目录
- 调用监控与可观测性
- 访问控制与审计
- 配置集中化管理
- 生命周期与健康状态可视化

需要一个面向企业内部、不对外的管理系统来收敛上述能力。

### 1.2 系统目标

按重要性排序：

1. **A — 服务注册中心**：维护所有自建 MCP 服务的目录，支持搜索、版本、状态查看
2. **B — 使用监控**：通过统一网关采集每一次调用的指标和日志，支持仪表盘与明细查询
3. **D — 访问控制 + 审计**：支持人/应用/团队多维度授权；管理动作与调用动作均可审计
4. **E — 配置管理**：集中存储、加密、热下发 MCP 服务侧需要的配置项
5. **C — 生命周期管理**：起步阶段以"健康检查 + 状态展示"形态存在，后期演进为编排

### 1.3 非目标（Non-goals）

- 不面向外部用户/客户开放
- 不做 MCP 服务自身的代码开发框架（仅提供接入规范）
- 起步阶段不做容器编排（不替代 K8s/Docker）；MCP 服务由各业务团队自行部署
- 不做 tool 级别的细粒度权限（v1 只到服务级；后期可扩展）

### 1.4 关键约束

| 维度 | 约束 |
|---|---|
| 部署 | Docker Compose（起步），后期可平滑迁移到 K8s |
| 后端语言 | Python |
| 规模 | 50 个服务（可增长）、百级用户 / Agent、QPS 10–100 |
| MCP 消费者 | AI Agent / 后端应用为主（server-to-server）|
| MCP 部署 | 业务团队自行部署，管理系统仅注册 URL 并代理 |
| MCP transport | 仅支持 Streamable HTTP |
| 认证（一期）| JWT + 本地账号；Agent 用 API Key |
| 认证（二期）| 接入企业 SSO（OIDC 等）|
| 数据保留 | 调用 metadata 永久；调用 body 30 天后置 NULL |

---

## 2. 整体架构

### 2.1 架构选型

采用 **网关 + 控制面分离** 的双服务结构：

- **Gateway Service**：纯转发 + 鉴权 + 限流 + 埋点；无状态、可独立横向扩展
- **Control Plane Service**：管理后台 API、注册中心、配置中心、审计查询、健康检查
- **共享存储**：Postgres（元数据 + 调用日志）+ Redis（缓存 + 限流 + 配置失效 pub/sub）
- **可视化**：Web 管理后台（前后端分离）+ Grafana（直连 Postgres 渲染监控图）

被否决的备选：单体方案（Gateway 与后台耦合，扩容粒度差）；Sidecar/Service Mesh（对当前规模过度设计）。

### 2.2 模块视图

```
┌─────────────────────────────────────────────────────────────┐
│  前端 (Web Admin)        Vue 3 / Next.js                     │
│  - 服务目录浏览/搜索      - 监控仪表盘 (嵌 Grafana)            │
│  - 服务/凭证/权限管理     - 调用审计查询                       │
└──────────────────┬──────────────────────────────────────────┘
                   │  REST + WebSocket(实时调用流)
┌──────────────────┴──────────────────────────────────────────┐
│  Control Plane Service   FastAPI                            │
│  ├─ auth         JWT 登录、API Key 签发与吊销                │
│  ├─ registry     MCP 服务注册、版本、Tag、健康状态            │
│  ├─ rbac         角色/权限、服务-用户绑定                     │
│  ├─ config       MCP 配置项加密存储、热下发到 gateway         │
│  ├─ audit        调用日志查询、导出                          │
│  └─ healthcheck  定时探活各 MCP 服务，写状态                  │
└──────────────────┬──────────────────────────────────────────┘
                   │
              Postgres ◄────┐                    Redis
                            │                    ├─ API Key 鉴权缓存
                            │                    ├─ 限流计数器
                            │                    └─ 配置变更 pub/sub
                            │
┌───────────────────────────┴─────────────────────────────────┐
│  Gateway Service         FastAPI + httpx (异步)              │
│  ├─ authn        校验 API Key (Redis 缓存, 1s 内生效)         │
│  ├─ authz        查询调用方对目标 MCP 是否有权限              │
│  ├─ ratelimit    Token Bucket (按 API Key + 服务维度)         │
│  ├─ router       根据服务名解析后端 URL，转发 Streamable HTTP │
│  ├─ telemetry    异步写调用日志 (metadata + 截断 body)        │
│  └─ resilience   超时、重试、熔断（基础版）                    │
└──────────────────┬──────────────────────────────────────────┘
                   │  HTTP/SSE 流式转发
                   ↓
            真实 MCP Server 池（业务方自部署）
```

### 2.3 关键架构决策

| # | 决策 | 理由 |
|---|---|---|
| AD-1 | Gateway 与 Control Plane 分两个进程 | 流量与管理隔离；Gateway 横向扩展不影响后台发布 |
| AD-2 | Monorepo + 共享 `models/`、`schemas/` Python 包 | 避免类型分裂；同时减少跨服务接口维护成本 |
| AD-3 | 调用日志直接放 Postgres + 月度分区 | QPS 量级足够；少一个组件（不引入 ClickHouse）|
| AD-4 | 健康检查只在 Control Plane 做（非 Gateway） | Gateway 多实例无状态；避免重复探活 |
| AD-5 | 配置/权限热更新走"失效 → 重新拉取"，不推送新值 | 避免推送丢失导致脏数据 |
| AD-6 | 监控可视化复用 Grafana，不自研图表 | 降低前端工作量；Postgres 直连即可 |

---

## 3. 数据模型

### 3.1 身份与权限

```
users
  id, username, email, password_hash, role(admin/operator/viewer),
  status, created_at, last_login_at
  -- 阶段二接 SSO 时增加 sso_subject 字段；password_hash 可空

api_keys
  id, key_prefix(明文前 8 位), key_hash(bcrypt),
  owner_type(user/application), owner_id,
  name, scopes(json), expires_at, last_used_at, revoked_at

applications        -- "应用"作为 Agent 的归属主体
  id, name, owner_user_id, team, description, created_at
```

### 3.2 服务注册中心

```
mcp_services
  id, slug(URL 中的服务名), display_name, description,
  owner_team, tags(json),
  endpoint_url,            -- 后端真实地址
  transport(streamable_http),
  status(active/disabled),
  health_status(healthy/unhealthy/unknown), last_health_check_at,
  created_at, updated_at

mcp_service_versions   -- 版本/变更历史，便于回溯
  id, service_id, version, endpoint_url, manifest(json, 记录 tools 列表),
  is_current, created_at, created_by
```

### 3.3 访问控制

```
service_permissions   -- 谁能调用哪个服务
  id, service_id,
  subject_type(user/application/team/role), subject_id,
  granted_by, granted_at, expires_at

rate_limit_policies   -- 限流策略，可绑到服务或 API Key
  id, name, qps, daily_quota, scope(per_key/per_service)
```

### 3.4 配置管理

```
service_configs       -- MCP 服务侧需要的配置（注入到调用 header 或转发给后端）
  id, service_id, key, value_encrypted, is_secret,
  updated_at, updated_by
```

### 3.5 监控与审计

```
call_logs             -- 每次调用一条；body 30 天后清空
  id (uuid),
  ts,
  api_key_id, application_id, user_id,           -- 调用方
  service_id, service_version, tool_name,        -- 被调方
  request_id,                                    -- MCP JSON-RPC id
  status(success/error/timeout),
  http_status, error_code, error_message,
  duration_ms, request_bytes, response_bytes,
  request_body, response_body,                   -- 30 天后置 NULL
  client_ip
  -- 索引: (ts), (service_id, ts), (api_key_id, ts), (status, ts)
  -- 分区: 按月分区 (declarative partitioning)，过期月份直接 detach

audit_events          -- 管理动作审计（注册服务、改配置、授权）
  id, ts, actor_user_id, action, target_type, target_id,
  before(json), after(json), ip
```

### 3.6 数据存储决策细节

- **`call_logs` 用 Postgres 月度分区**：QPS 上限按 100 算，每天最多 ~860 万行，单表分区可承载
- **配置加密**：`value_encrypted` 用 Fernet（AES-128-CBC + HMAC），主密钥从环境变量读
- **API Key**：明文只在签发时返回一次；库里存 `bcrypt(key)` + `key_prefix` 用于展示
- **权限粒度**：仅服务级；不支持 tool 级别（YAGNI；后期可加 `tool_pattern` 字段）

---

## 4. 关键流程

### 4.1 流程 A — Agent 调用 MCP 工具（端到端）

```
Agent ──POST /mcp/{service_slug}──→ Gateway
       Header: Authorization: Bearer <api_key>
       Body:   {jsonrpc:"2.0", method:"tools/call", params:..., id:42}
                                        │
                                        ▼
        ┌───────────────────────────────────────────────────────┐
        │ 1. authn:  解析 API Key → Redis 查 hash               │
        │            未命中→Postgres查→bcrypt比对→回填Redis      │
        │            返回 owner(application/user) + scopes      │
        │                                                       │
        │ 2. resolve: service_slug → service_id, endpoint_url   │
        │             (内存 LRU 缓存 + Redis pub/sub 失效通知)    │
        │                                                       │
        │ 3. authz:  service_permissions 查 (subject, service)  │
        │            (启动时全量加载到内存，配置变更增量刷新)     │
        │                                                       │
        │ 4. ratelimit: Token Bucket via Redis (Lua 原子脚本)    │
        │            按 (api_key_id, service_id) 维度            │
        │                                                       │
        │ 5. proxy:  httpx.AsyncClient 透传请求到后端            │
        │            支持流式响应 (Streamable HTTP)              │
        │            注入 X-Request-Id / X-Calling-App headers   │
        │                                                       │
        │ 6. telemetry: 异步任务（asyncio.create_task）          │
        │            写一行 call_logs（不阻塞响应）              │
        │            request_body / response_body 截断到 64KB    │
        └───────────────────────────────────────────────────────┘
                                        │
                                        ▼
                            真实 MCP Server
```

**失败语义：**

| 阶段 | 失败 → 返回 |
|---|---|
| 1 authn 失败 | 401 Unauthorized |
| 2 resolve 找不到服务 | 404 Not Found |
| 3 authz 拒绝 | 403 Forbidden |
| 4 ratelimit 触发 | 429 Too Many Requests |
| 5 proxy 超时 | 504 Gateway Timeout |
| 5 后端 5xx | 透传后端状态码与错误体 |

**telemetry 异步写策略**：内存队列 + 后台批量 flush（每 1s 或攒满 100 条做一次批量 INSERT）；失败重试 3 次仍失败则丢弃并打点告警。可接受小概率丢日志以换取主路径性能。

### 4.2 流程 B — 配置 / 权限热更新

```
管理员在前端改了某服务的 endpoint_url 或权限
    │
    ▼
Control Plane: 写 Postgres → Redis PUBLISH "config:invalidate" {service_id}
                                                 │
        ┌────────────────────────────────────────┴───────┐
        ▼                                                ▼
  Gateway 实例 1                                  Gateway 实例 N
  订阅 channel → 删本地 LRU 该 key
  下次请求重新查库 → 拿到新值
```

- 失效通知 < 1s 全网生效
- 走"失效 → 重拉"而非"推送新值"，避免推送丢失导致脏数据
- API Key 吊销同样使用此机制：channel `auth:revoke {api_key_id}`

### 4.3 流程 C — 健康检查

Control Plane 启动后台 scheduler（APScheduler），每 30s 对所有 `status=active` 的服务并发执行：

- 调用后端的 `GET /health`（约定）或 `POST /mcp` 发送 `initialize` 心跳
- 写回 `mcp_services.health_status` + `last_health_check_at`
- 状态变化时写一条 `audit_events`，便于排障"何时挂的"
- 不在 Gateway 做健康检查（Gateway 无状态多实例，重复探活浪费）

前端在服务列表实时展示状态色（绿 / 黄 / 灰）。

---

## 5. 接口设计要点

> 完整 OpenAPI 规范在实现阶段产出；本节只列关键端点。

### 5.1 Gateway 对外

| Method | Path | 用途 |
|---|---|---|
| POST | `/mcp/{service_slug}` | MCP JSON-RPC 转发入口 |
| GET | `/healthz` | Gateway 自身健康 |
| GET | `/metrics` | Prometheus 指标暴露 |

### 5.2 Control Plane（管理后台 API）

| 模块 | 端点示例 |
|---|---|
| auth | `POST /api/v1/auth/login`、`POST /api/v1/auth/logout` |
| 用户 | `GET/POST/PUT/DELETE /api/v1/users` |
| API Key | `POST /api/v1/api-keys`（仅此次返回明文）、`DELETE /api/v1/api-keys/{id}` |
| 应用 | `GET/POST /api/v1/applications` |
| 服务 | `GET/POST /api/v1/services`、`POST /api/v1/services/{id}/versions` |
| 权限 | `POST /api/v1/services/{id}/permissions`、`DELETE .../{permission_id}` |
| 配置 | `GET/PUT /api/v1/services/{id}/configs` |
| 调用日志 | `GET /api/v1/call-logs?service_id=&from=&to=&status=` |
| 审计 | `GET /api/v1/audit-events?actor=&action=&from=&to=` |

### 5.3 内部约定

- 所有管理后台 API 走 JWT；Gateway 流量走 API Key
- 所有写操作进 `audit_events`
- 错误响应统一格式：`{"error": {"code": "...", "message": "...", "request_id": "..."}}`

---

## 6. 分阶段交付

### MVP（4–6 周）— A 注册中心 + B 监控雏形 + 最小化 D

- 用户登录（JWT + 本地账号）
- 服务注册 / 列表 / 详情 / 编辑（CRUD）
- API Key 签发 / 吊销
- Gateway 代理转发 Streamable HTTP（authn + 简单 authz：API Key 是否启用）
- 调用日志写入 + 列表查询（Web 端简单表格）
- 仪表盘：总调用量、错误率、Top 服务（嵌 Grafana 一张图即可）
- Docker Compose 一键起栈

### v1（再 4 周）— 完整 D + E + 更深的 B

- 细粒度权限：`service_permissions` 表生效（按用户/应用/团队/角色授权）
- 限流：per-key + per-service 双维度
- 配置中心：`service_configs` 增删改 + Fernet 加密 + 热下发
- 审计事件 `audit_events` 全量记录 + 查询
- 监控仪表盘扩展：延迟分位（P50/P95/P99）、按调用方分布、按 tool 分布
- 调用日志详情页（含 request/response body 查看）
- 服务版本管理 `mcp_service_versions`

### v2（再 4 周）— C 生命周期 + SSO + 韧性增强

- 接 SSO（OIDC 或公司 IAM 协议，预留扩展点）
- 健康检查 + 状态历史 + 异常告警（webhook / 邮件）
- 熔断（连续失败 N 次自动降级）
- Body 30 天自动归档（pg_partman 或定时脚本 detach 旧分区）
- 服务上下线编排（标记 disabled，Gateway 立即拒绝；保留历史日志）

合计约 12–14 周，每阶段末为可演示的部署状态。

---

## 7. 非功能需求（NFR）

| 维度 | 目标 |
|---|---|
| 延迟 | Gateway 自身开销 P95 < 20ms（不含后端处理时间）|
| 吞吐 | 单 Gateway 实例 ≥ 200 QPS；横向扩展无锁竞争 |
| 可用性 | 内部系统，目标 99%（计划停机除外）；Postgres 单实例可接受，备份每日 |
| 数据保留 | 调用 metadata：永久；调用 body：30 天后置 NULL；audit_events：永久 |
| 安全 | 配置秘密 Fernet 加密；API Key 仅 bcrypt hash 入库；HTTPS 终结在反向代理（Nginx/Caddy）|
| 观测 | 应用日志结构化 JSON；Gateway/Control Plane 各自暴露 `/metrics`（Prometheus 格式）|
| 可恢复 | Postgres 每日 `pg_dump` 到独立卷；配置主密钥需备份到企业密码管理器 |

---

## 8. 部署拓扑（Docker Compose）

```
services:
  nginx          # 反向代理 + TLS 终结，路由 /mcp/* → gateway，其余 → control-plane / web
  gateway        # × 2 实例（compose scale）
  control-plane  # × 1
  web            # 静态前端（nginx:alpine 服务静态文件）
  postgres       # 持久化卷
  redis          # 持久化卷
  grafana        # 持久化卷
volumes:
  postgres-data, redis-data, grafana-data
```

- Gateway 多实例由 nginx upstream 轮询
- 配置主密钥从 host 环境变量传入，不写进镜像
- 每日 `pg_dump` 由独立 cron 容器执行，落到 backups 卷

---

## 9. 风险与对策

| 风险 | 对策 |
|---|---|
| Gateway 是单点，挂了全停 | Compose 阶段起 2 个 gateway 实例 + Nginx 上游负载均衡 |
| 调用日志写库压垮 Postgres | 内存队列 + 批量；监控写延迟，超阈值自动降级到只记 metadata |
| 配置主密钥丢失 → 历史秘密无法解密 | 启动时强制校验密钥能解密一条已知样本；密钥归档到企业密码管理器 |
| MCP server 的 transport 漂移（出现 SSE/stdio）| 注册时校验 transport 字段，仅放行白名单；非合规服务拒绝注册 |
| 前端能看到敏感 body | 调用日志详情页需 admin/operator 角色；body 中疑似秘密字段做正则脱敏 |
| Postgres 单点 | v2 前增加 standby + WAL 归档；运维 SOP 演练恢复流程 |

---

## 10. 待确认 / 后续工作

- 前端框架最终选型（Vue 3 vs Next.js）— 由前端同学根据团队现状决定
- 公司 SSO 协议细节（v2 期）
- 告警通道选型（飞书/钉钉/企业微信 webhook 还是邮件）
- 是否对外暴露只读的 OpenAPI 文档供业务方接入参考
- 是否需要为业务方提供"接入 SDK"（Python 起步），降低 Agent 接入成本

---

## 附录 A — 术语

- **MCP**：Model Context Protocol，AI Agent 与外部能力通信的协议
- **Gateway**：本系统中接收 Agent 请求并转发到真实 MCP server 的服务
- **Control Plane**：本系统中负责管理后台 API、注册、配置、审计的服务
- **Application**：Agent 在本系统中的归属主体；一个 Application 可拥有多个 API Key
- **Service slug**：MCP 服务的 URL 友好标识，作为 Gateway 路由 key
