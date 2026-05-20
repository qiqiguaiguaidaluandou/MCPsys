# MCPsys

内部 MCP（Model Context Protocol）服务管理系统：统一注册自建 MCP 服务、签发 / 鉴权 API Key、网关代理 Agent 流量、限流、调用日志与可视化看板。

- 系统设计：`docs/specs/2026-04-30-mcp-management-system-design.md`
- 完整运维手册（备份恢复 / 故障排查 / 日常操作）：`docs/deployment.md`

## 架构

一个 nginx 在 `:8088` 对外，反代到三个应用容器，外加 Postgres 与 Redis：

```
                         ┌──────────────── nginx (:8088 对外) ────────────────┐
浏览器 / Agent  ──────▶   │  /            → web（Vue 3 管理后台）              │
                         │  /api/        → control-plane（管理 API，JWT）     │
                         │  /mcp/{slug}  → gateway（MCP 流量代理，API Key）   │
                         └────────────────────┬───────────────┬──────────────┘
                                              ▼               ▼
                                          Postgres          Redis
                                       （主数据 / 日志）  （鉴权/限流/缓存）
```

- **control-plane**：管理 API（用户、应用、服务、API Key、授权、审计、统计），并跑两个后台 worker——服务健康检查、调用日志 body 保留清理。
- **gateway**：Agent 调用入口，校验 API Key → 鉴权 → 限流 → 转发到上游 MCP 服务 → 异步写调用日志。
- **web**：Vue 3 + Element Plus 管理后台（含原生可视化仪表盘）。

---

# 部署到新服务器

下文是把本项目（已托管在 GitHub）部署到一台全新 Linux 服务器的完整流程。更细的日常运维 / 故障排查见 `docs/deployment.md`。

## 1. 前置要求

| 组件 | 最低版本 | 检查命令 |
|---|---|---|
| Linux | 主流发行版（推荐 Ubuntu 22.04+） | `uname -a` |
| Docker Engine | 24.0+ | `docker --version` |
| Docker Compose | v2.20+（命令是 `docker compose`，不是 `docker-compose`） | `docker compose version` |
| Git | 任意版本 | `git --version` |
| 可用磁盘 | ≥ 20 GB | `df -h` |
| 可用内存 | ≥ 2 GB | `free -h` |
| 对外端口 | 仅 `8088`（其余均为容器内部通信） | `ss -tlnp \| grep :8088` |

没装 Docker 时（Ubuntu / Debian）：

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER     # 加完需重新登录使其生效
sudo systemctl enable --now docker
docker compose version            # 确认自带 compose v2
```

## 2. 拉取代码

```bash
git clone https://github.com/qiqiguaiguaidaluandou/MCPsys.git
cd MCPsys
```

> 后续命令都假设你在仓库根目录（即有 `compose.yaml` 的这一层）。如果用私有仓库或需要凭据，自行配置好 SSH key 或 token 再 clone。

## 3. 配置 `.env`

```bash
cp .env.example .env
```

打开 `.env`，**生产环境必须修改这两个值**：

```dotenv
POSTGRES_PASSWORD=<强密码>
JWT_SECRET=<≥32 字节随机串>
```

生成随机值（任选其一）：

```bash
# 用 python3
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # 数据库密码
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # JWT 密钥

# 或用 openssl
openssl rand -base64 24
openssl rand -base64 48
```

其余配置项及默认值见 `.env.example` 内的中文注释，通常保持默认即可。需要关注的几个：

| 键 | 默认 | 说明 |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_DB` | `mcpsys` | 数据库用户名 / 库名 |
| `JWT_SECRET` | （占位） | **必改**。换掉会让已签发的 token 全部失效 |
| `JWT_EXPIRES_MINUTES` | `60` | 登录 token 有效期（分钟） |
| `PROXY_VERIFY_TLS` | `false` | 网关是否校验上游 MCP 服务的 TLS 证书。上游是 https 且证书可信时建议设 `true` |
| `CALL_LOG_BODY_RETENTION_DAYS` | `30` | 调用日志 body 多少天后置 NULL（metadata 永久保留、行不删） |
| `RETENTION_INTERVAL_SECONDS` | `3600` | 保留 worker 的清理周期 |
| `LOG_LEVEL` | `INFO` | 应用日志级别 |

> ⚠️ `.env` 已在 `.gitignore` 中、不会被提交。请妥善保管：丢 `JWT_SECRET` → 所有 token 失效；丢 `POSTGRES_PASSWORD` → 连不上库。建议存入企业密码管理器。

## 4. 构建并启动

```bash
docker compose build      # 构建镜像（首次约 2-5 分钟）
docker compose up -d      # 启动全部 6 个服务
docker compose ps         # 查看状态
```

期望所有服务 `Up`、带 healthcheck 的显示 `(healthy)`，约 30-60 秒内稳定。某个容器一直 `unhealthy` / `Restarting` 时见 `docs/deployment.md` §11 故障排查。

> **数据库迁移是自动的**：control-plane 容器启动时，entrypoint 会先执行 `alembic upgrade head` 再起服务，无需手动建表。

## 5. 创建初始管理员

```bash
docker compose exec control-plane python /app/scripts/seed_admin.py admin '<管理员密码>'
```

输出 `created admin 'admin'` 即成功。脚本幂等——重跑只会跳过、不会改密码。

## 6. 冒烟验证（可选但推荐）

```bash
# 若上一步管理员密码不是默认的 admin123，先导出：
export PASSWORD='<你设置的管理员密码>'
./scripts/smoke.sh
```

以 `[smoke] OK` 结尾即打通了「登录 → 建应用 → 注册服务 → 签发 Key → 经网关调用 → 落调用日志」全链路。

> 该脚本会注册一个指向 `httpbin.org` 的测试服务来打通调用链，需要服务器有出口网络。出口受限时改成内网某个 MCP 服务再跑即可。脚本需要本机有 `bash` / `curl` / `python`。

## 7. 访问入口

| 入口 | 地址 | 用途 |
|---|---|---|
| Web 管理后台 | `http://<host>:8088/` | 浏览器登录后操作 |
| 仪表盘 | `http://<host>:8088/dashboard` | 原生可视化看板（登录后从侧边栏进入） |
| Control-plane 健康 | `http://<host>:8088/healthz` | 应返回 `{"status":"ok"}` |
| Gateway 健康 | `http://<host>:8088/gw/healthz` | 同上 |
| 管理 API | `http://<host>:8088/api/v1/...` | JWT 鉴权 |
| Swagger UI | `http://<host>:8088/api/v1/docs` | 接口交互调试 |
| MCP 流量入口 | `POST http://<host>:8088/mcp/{slug}` | Agent 调用入口（API Key 鉴权） |

---

## 更新到新版本

```bash
cd MCPsys
git pull
docker compose build
docker compose up -d      # control-plane 启动时自动跑 alembic upgrade head
docker compose logs control-plane | grep -i alembic   # 确认迁移成功
```

含 schema 变更的版本，**先备份再升级**（备份命令见 `docs/deployment.md` §9）。

## 备份

- **Postgres**：`pg_dump` 备份（建议配每日 cron），命令与恢复流程见 `docs/deployment.md` §9。
- **Redis**：仅缓存（鉴权 / 限流 / 统计缓存），丢失无影响，重启自动回填。

## 运维与故障排查

日志查看、重启、进容器、签发 Key、注册服务、吊销 Key、404/401 排查等，统一见 `docs/deployment.md` §8–§11。

---

## 本地开发

后端（uv 工作区）：

```bash
uv sync                                              # 安装依赖
uv run --package control-plane pytest services/control_plane/tests
uv run --package gateway        pytest services/gateway/tests
uv run --package mcpsys-shared  pytest packages/mcpsys_shared/tests
```

前端（先 `docker compose up -d` 起后端栈）：

```bash
cd services/web
pnpm install
pnpm dev          # HMR 开发服务器 http://localhost:5173
pnpm test         # vitest 单测
pnpm typecheck    # vue-tsc --noEmit
pnpm build        # 产线打包到 dist/
```

## 运维说明

- **TLS 终结**：内置 nginx 仅监听 HTTP（容器内 :80，映射到宿主 :8088）。生产期望由企业边缘 / 上层反代终结 TLS。要本机直接做 TLS，给 `nginx/nginx.conf` 加 `listen 443 ssl;` 与证书挂载。
- **网关扩容**：MVP 量级（≤100 QPS）单实例足够。多副本需要给 nginx 上游加运行时 DNS resolver，属 v1 范围。
- **调用日志保留**：control-plane 的保留 worker 会按 `CALL_LOG_BODY_RETENTION_DAYS` 自动把超期日志的 body 置 NULL（metadata 永久、行不删）。

## 文档索引

- 系统设计与 v1 规划：`docs/specs/2026-04-30-mcp-management-system-design.md`
- 前端设计：`docs/specs/2026-05-06-web-admin-design.md`
- 完整部署 / 运维手册：`docs/deployment.md`
- 变更记录：`docs/changes/`
