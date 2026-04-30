# MCPsys 部署手册

把当前仓库部署到一台新服务器的完整流程。涵盖环境检查、代码迁移、配置、启动、首次初始化、验证、常用运维操作和故障排查。

适用对象：第一次接管这套系统的运维或开发同学。

---

## 1. 目标服务器前置要求

| 组件 | 最低版本 | 检查命令 |
|---|---|---|
| Linux | 任意主流发行版（Ubuntu 22.04+ / CentOS 8+ 推荐） | `uname -a` |
| Docker Engine | 24.0+ | `docker --version` |
| Docker Compose | v2.20+（命令是 `docker compose`，非 `docker-compose`） | `docker compose version` |
| 可用磁盘 | ≥ 20 GB（postgres + grafana + 镜像） | `df -h` |
| 可用内存 | ≥ 2 GB（postgres 占大头） | `free -h` |
| 开放端口 | 80（对外）；其他端口仅容器内通信 | `ss -tlnp \| grep :80` |
| Git（可选） | 任意版本，仅用于代码拉取 | `git --version` |

如果 Docker 没装：

```bash
# Ubuntu / Debian
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER     # 加完需要重新登录
sudo systemctl enable --now docker

# 确认 compose v2 已包含
docker compose version
```

---

## 2. 把代码弄到这台服务器

源仓库当前是本地 git 仓库（`/dataspace/kqspace/MCPsys/.git`），还没推过 remote。三种方式任选：

### 方式 A：通过 git remote（推荐，可持续更新）

在**源机器**上：

```bash
cd /dataspace/kqspace/MCPsys
# 把仓库推到企业内的 GitLab / Gitea / GitHub Private
git remote add origin git@gitlab.example.com:infra/mcpsys.git
git push -u origin master
```

在**目标服务器**上：

```bash
git clone git@gitlab.example.com:infra/mcpsys.git
cd mcpsys
```

### 方式 B：rsync（无远端 git，快速搬一次）

在源机器上：

```bash
rsync -avz --exclude='.venv/' --exclude='postgres-data/' --exclude='redis-data/' \
      --exclude='grafana-data/' --exclude='.env' \
      /dataspace/kqspace/MCPsys/ user@deploy-host:/opt/mcpsys/
```

### 方式 C：tar 打包传输

```bash
# 源机器
cd /dataspace/kqspace
tar --exclude='MCPsys/.venv' --exclude='MCPsys/postgres-data' \
    --exclude='MCPsys/redis-data' --exclude='MCPsys/grafana-data' \
    --exclude='MCPsys/.env' \
    -czf mcpsys.tgz MCPsys/
scp mcpsys.tgz user@deploy-host:/opt/

# 目标服务器
cd /opt && tar -xzf mcpsys.tgz && cd MCPsys
```

无论哪种方式，最终目标服务器上应该有完整的 `MCPsys/` 目录。本文后续命令都假设你 `cd` 到了这个目录。

---

## 3. 配置 `.env`

```bash
cp .env.example .env
```

打开 `.env`，**必须修改**两个值：

```dotenv
POSTGRES_PASSWORD=<生成强密码>
JWT_SECRET=<生成 ≥32 字节随机串>
```

生成命令：

```bash
# 数据库密码（24 字节 base64url）
python3 -c "import secrets; print(secrets.token_urlsafe(24))"

# JWT 密钥（48 字节）
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

如果服务器没装 python3，可用 openssl：

```bash
openssl rand -base64 24
openssl rand -base64 48
```

其他键的默认值通常可保留：

| 键 | 默认 | 说明 |
|---|---|---|
| `POSTGRES_USER` | `mcpsys` | 数据库用户名 |
| `POSTGRES_DB` | `mcpsys` | 数据库名 |
| `POSTGRES_PORT` | `5432` | （未对外暴露，只在容器网络内） |
| `REDIS_PORT` | `6379` | （同上） |
| `JWT_EXPIRES_MINUTES` | `60` | JWT 过期时间 |
| `GATEWAY_PORT` | `8080` | （容器内端口，外部走 nginx） |
| `CONTROL_PLANE_PORT` | `8000` | （同上） |
| `GRAFANA_PORT` | `3000` | （同上） |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | **生产环境必改** |
| `LOG_LEVEL` | `INFO` | 应用日志级别 |

> ⚠️ `.env` 已在 `.gitignore` 中，不会被 commit。**请妥善保管这个文件**：丢失了 JWT_SECRET 会导致所有已签发的 token 失效；丢失 POSTGRES_PASSWORD 会让你无法连库。把它存进企业密码管理器是好习惯。

---

## 4. 构建镜像 & 启动

```bash
# 构建两个 Python 镜像（首次约 2-5 分钟）
docker compose build

# 启动全部 6 个服务
docker compose up -d

# 查看启动状态
docker compose ps
```

期望最终所有服务都是 `Up` 且 healthcheck 显示 `(healthy)`。约 30-60 秒内稳定。

如果某个服务一直 `(unhealthy)` 或 `Restarting`，跳到 §9 故障排查。

---

## 5. 首次初始化：创建管理员

```bash
docker compose exec control-plane python scripts/seed_admin.py admin '<你想要的强密码>'
```

输出：`created admin 'admin'`

> 这个脚本是幂等的 —— 重跑只会跳过，不会改密码。改密码请直接 SQL：`docker compose exec postgres psql -U mcpsys -d mcpsys -c "UPDATE users SET password_hash='<bcrypt-hash>' WHERE username='admin'"`，或先 `DELETE FROM users WHERE username='admin'` 再重跑脚本。

---

## 6. 端到端冒烟验证

```bash
./scripts/smoke.sh
```

如果你改过 admin 用户名/密码，先 `export USERNAME=... PASSWORD=...` 再跑。

期望以 `[smoke] OK` 结尾。脚本会依次：
1. healthz
2. 用 admin 登录拿 JWT
3. 创建 application `smoke-app`
4. 注册服务 `smoke-svc`（指向 httpbin.org，仅用于打通调用链）
5. 给 smoke-app 签发一个 API Key
6. 用这个 key 通过 gateway 调一次 `smoke-svc`
7. 拉 call_logs 看是否有记录

如果 5/6 步失败（gateway 连不上 httpbin.org），通常是出口网络受限。可以改成你内网的 MCP 服务再跑。

---

## 7. 验证关键入口

| 入口 | 路径 | 用途 |
|---|---|---|
| Control-plane 健康 | `http://<host>/healthz` | 应返回 `{"status":"ok"}` |
| Gateway 健康 | `http://<host>/gw/healthz` | 同上 |
| 管理 API（OpenAPI 文档） | `http://<host>/api/v1/openapi.json` | 给前端/集成方对照接口 |
| 管理 API（Swagger UI） | `http://<host>/docs` | 浏览器交互调试 |
| MCP 流量入口 | `POST http://<host>/mcp/<service-slug>` | Agent 调用入口 |
| Grafana | `http://<host>/grafana/` | 监控面板，登录 `admin / <GRAFANA_ADMIN_PASSWORD>` |

进 Grafana 后默认会看到 "MCPsys" 文件夹下的 "MCP Overview" 仪表盘（4 个面板：24h 调用总数 / 错误率 / Top 服务 / 每分钟调用）。冒烟跑完后应该能看到 1-2 条数据。

---

## 8. 常用运维操作

### 查看日志

```bash
docker compose logs -f control-plane    # 实时跟随
docker compose logs --tail=200 gateway
docker compose logs                      # 所有服务
```

### 重启某个服务

```bash
docker compose restart gateway
```

### 进容器排查

```bash
docker compose exec control-plane bash
docker compose exec postgres psql -U mcpsys -d mcpsys
docker compose exec redis redis-cli
```

### 给 Agent 团队发一个 API Key

```bash
# 先用 admin 登录拿 JWT
TOKEN=$(curl -s -X POST http://localhost/api/v1/auth/login \
    -d "username=admin&password=<adminpw>" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 创建 application
APP=$(curl -s -X POST http://localhost/api/v1/applications \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"name":"team-foo-agent","team":"foo"}')
APP_ID=$(echo "$APP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 签发 key（明文只会返回一次！）
curl -s -X POST http://localhost/api/v1/api-keys \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d "{\"name\":\"team-foo prod\",\"owner_type\":\"application\",\"owner_id\":$APP_ID}" \
    | python3 -m json.tool
# → 把 plaintext 字段安全地交给 Agent 团队（只此一次）
```

### 注册一个新的 MCP 服务

```bash
curl -X POST http://localhost/api/v1/services \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{
      "slug":"hr-bot",
      "display_name":"HR Bot",
      "description":"内部 HR 系统的 MCP 接口",
      "owner_team":"hr",
      "endpoint_url":"http://hr-bot.internal:8000/mcp"
    }'
```

之后 Agent 用 `POST http://<host>/mcp/hr-bot` 即可调用。

### 吊销 API Key

```bash
curl -X DELETE "http://localhost/api/v1/api-keys/<key_id>" \
    -H "Authorization: Bearer $TOKEN"
```

> 注：吊销后最长 60 秒缓存窗口内 gateway 仍可能放行（设计取舍，spec §4.2 解释）。生效前可主动 `docker compose exec redis redis-cli FLUSHDB` 强制刷新。

---

## 9. 备份与恢复

### Postgres 每日备份（建议设个 cron）

```bash
# /etc/cron.daily/mcpsys-backup
#!/bin/sh
BACKUP_DIR=/var/backups/mcpsys
mkdir -p "$BACKUP_DIR"
DATE=$(date +%Y%m%d)
docker compose -f /opt/mcpsys/compose.yaml exec -T postgres \
    pg_dump -U mcpsys -d mcpsys \
    | gzip > "$BACKUP_DIR/mcpsys-$DATE.sql.gz"
# 保留最近 30 天
find "$BACKUP_DIR" -name 'mcpsys-*.sql.gz' -mtime +30 -delete
```

### 从备份恢复

```bash
gunzip -c /var/backups/mcpsys/mcpsys-20260601.sql.gz \
    | docker compose exec -T postgres psql -U mcpsys -d mcpsys
```

> ⚠️ 恢复前先 `docker compose stop control-plane gateway`，避免应用同时写入。

### Grafana / Redis 数据

- Grafana 配置和 dashboards 走的是 provisioning（`grafana/provisioning/`），重建容器不丢；用户自定义在 UI 创建的图表才需要备份 `grafana-data` volume
- Redis 只是缓存，丢了无影响

---

## 10. 升级到新版本

```bash
cd /opt/mcpsys
git pull                          # 或者 rsync 新代码进来
docker compose build              # 重新构建镜像
docker compose up -d              # 滚动应用新镜像
# 控制面容器启动时 entrypoint 会自动跑 alembic upgrade head
```

如果新版本含数据库 schema 变更，**建议先备份再升级**：

```bash
/etc/cron.daily/mcpsys-backup     # 手动跑一次
git pull && docker compose build && docker compose up -d
docker compose logs control-plane | grep alembic   # 确认迁移成功
```

---

## 11. 故障排查

### 容器卡在 `Restarting`

```bash
docker compose logs <service-name> --tail=100
```

常见原因：

| 现象 | 可能原因 | 修复 |
|---|---|---|
| `control-plane` 启动后 die | alembic 连不上 postgres | 等 postgres healthy 后会自动重连；持续失败检查 `.env` 的 POSTGRES_* |
| `gateway` die，日志报 connect refused | redis 没起来 | `docker compose restart redis` |
| `nginx` 起不来，端口冲突 | 宿主 :80 被占 | `ss -tlnp \| grep :80` 看谁占用，停掉它或改 nginx 容器 ports 映射 |
| 所有容器都 healthy 但访问 404 | 浏览器缓存 / 路径错 | 访问 `http://host/healthz` 验证基础路径 |

### 调用 `/mcp/<slug>` 401

- 检查 Authorization header 是 `Bearer mcpk_...` 形式
- 检查 key 是否被吊销：`docker compose exec postgres psql -U mcpsys -d mcpsys -c "SELECT key_prefix, revoked_at, expires_at FROM api_keys"`
- 缓存窗口（60s）问题：`docker compose exec redis redis-cli FLUSHDB`

### 调用 `/mcp/<slug>` 404

- slug 拼错或服务被软删除：`SELECT slug, status FROM mcp_services`
- 软删除过的服务 `status='disabled'`，重新启用：`UPDATE mcp_services SET status='active' WHERE slug='xxx'` 或通过 `PATCH /api/v1/services/<slug>` 把 status 改回 active

### Grafana 看不到数据

- 检查 datasource 是否连上：Grafana → Connections → Data sources → "MCPsys Postgres" → Test
- 容器间 DNS：在 grafana 容器内 `nc -vz postgres 5432` 应该能通
- 数据存在性：`SELECT count(*) FROM call_logs;` 返回非 0 才会有数据

### 想把日志保留时间缩短

MVP 没实现自动清理。手动方案：

```sql
-- 删除 30 天前的调用日志
DELETE FROM call_logs WHERE ts < now() - interval '30 days';
-- 仅清空 body 字段，保留元数据
UPDATE call_logs SET request_body=NULL, response_body=NULL
  WHERE ts < now() - interval '30 days';
```

可以包成 cron 跑。

---

## 12. 当前 MVP 已知限制

照实告知运维，避免被开 ticket：

- **网关单实例**：`compose.yaml` 不再用 `deploy.replicas`，nginx 上游也是单条记录。50 个服务 / 100 QPS 以下完全够用，更大规模需要按 README "Operational notes" 改 nginx + 扩容。
- **吊销/过期延迟最长 60 秒**：API Key 缓存 TTL。要立即生效就 `redis-cli FLUSHDB`。
- **HTTP only**：本 nginx 监听 :80，期望 TLS 由企业边缘终结。如要本机做 TLS，给 `nginx/nginx.conf` 加 `listen 443 ssl;` 块和证书挂载。
- **审计日志（管理动作 / 配置变更）尚未写入** `audit_events` 表 —— v1 范围。
- **细粒度权限 / 限流 / 配置中心 / SSO** 都是 v1，按 spec §6 排期。

---

## 13. 关键文件速查

```
.env.example          # 环境变量模板
compose.yaml          # 服务编排
nginx/nginx.conf      # 反向代理
grafana/provisioning/ # Grafana 自动配置
scripts/seed_admin.py # 创建初始 admin
scripts/smoke.sh      # 端到端冒烟
docs/specs/           # 设计文档
docs/plans/           # 实施计划
```

应用代码在 `services/control_plane/` 和 `services/gateway/`，共享层在 `packages/mcpsys_shared/`。

---

## 附录：联系与升级路径

- 系统设计与 v1 规划：`docs/specs/2026-04-30-mcp-management-system-design.md`
- 实施计划与历史：`docs/plans/2026-04-30-mcp-management-mvp-plan.md`
- 升级路径：v1 加 SSO / 限流 / 配置中心 / 审计 / 健康检查；v2 加生命周期编排（容器层）
