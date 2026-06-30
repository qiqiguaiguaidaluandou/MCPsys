# 自研 MCP 服务与 MCPsys 同机协同部署方案

- 日期：2026-06-30
- 状态：待评审（先出方案，评审后实施）
- 关联：`docs/specs/2026-04-30-mcp-management-system-design.md`、`README.md`、`compose.yaml`

## 1. 背景与目标

现状：MCPsys 只做**控制面**（注册 / 鉴权 / 限流 / 日志 / 看板），真正的 MCP 服务跑在服务器的**其它端口**、与管理系统是两套东西，新增和迭代一个 MCP 服务要手工建容器、记端口、再去后台手填 `endpoint_url`，心智负担重。

目标（本方案范围）：

1. 把自研 MCP 服务和 MCPsys 放进**同一台机器、同一个 docker compose 工程**，gateway 用**内网服务名**直连，对外仍只有 nginx 的 `8088`。
2. 提供**标准模板（脚手架）**，新增一个 MCP 服务 ≈ 复制一个目录 + 改业务代码。
3. 提供**一条命令**完成「生成编排 + 注册到控制面」，让服务定义单一来源、不漂移。
4. 迭代单个服务时只重建那一个容器，不影响管理系统与其它服务。

**不破坏现有解耦**：控制面 / 数据面仍然分离，gateway 仍按 `endpoint_url` 转发。本方案只在「部署编排」和「开发模板」两层把它们粘起来。

非目标（留给后续）：MCP 服务多副本 / 跨机扩缩容（README 已注明属 v1，需要 nginx 上游 DNS resolver）；`endpoint_url` 的 SSRF 黑名单（spec 已注明属 v1）。

## 2. 关键事实核对（已验证）

| 事实 | 出处 | 对方案的意义 |
|---|---|---|
| compose 顶部 `name: mcpsys`，无显式 networks，全在 `mcpsys_default` | `compose.yaml:1` | 新服务用同一 project 起即可内网互通，无需 external network |
| 注册接口 `POST /api/v1/services`，slug 冲突 409，`PATCH /{slug}` 更新 | `services.py:81`、`:192` | 脚本可做幂等 upsert（GET → 不存在则 POST，存在则 PATCH）|
| `endpoint_url` 仅 `HttpUrl` 结构校验，内网 http 合法 | `services.py:36` | `http://mcp-foo:8000/mcp` 可直接注册 |
| 健康检查 = 向 `endpoint_url` POST JSON-RPC `initialize`，2xx/4xx 即 healthy | `health_checker.py:32` | `endpoint_url` 指向 RPC 路径即可自动纳入监控 |
| gateway 请求时才 resolve 上游，失败返回 502 | `routers/mcp.py:78` | MCP 服务**不必**进 gateway 的 `depends_on`，保持松耦合 |
| 注册 / 改服务需 admin 或 operator 角色，登录走 `POST /api/v1/auth/login`（form） | `services.py:89`、`smoke.sh:15` | 同步脚本需一个 operator 账号的凭据 |

## 3. 总体设计

### 3.1 目录结构

```
mcp-services/
  _template/                # 脚手架模板
    Dockerfile
    requirements.txt        # 依赖（小脚本服务用 requirements 比打包更省事）
    src/server.py
    service.yaml            # 服务清单（占位）
    .env.example
    README.md
  echo/                     # 示例服务（阶段 1 产出，用于端到端打通）
    Dockerfile
    pyproject.toml
    src/server.py
    service.yaml
    .env.example            # 该服务对接公司接口所需的环境变量样例（提交到 git）
    .env                    # 真实密钥值（gitignore，不提交）
  <your-service>/
    ...
compose.mcp.yaml            # 由脚本从各 service.yaml 生成（不手改）
scripts/
  new_mcp_service.sh        # 脚手架：复制模板 + 改名
  sync_mcp_services.py      # 生成 compose.mcp.yaml + upsert 注册到控制面
```

### 3.2 单一信息源（SSOT）：`service.yaml`

每个 MCP 服务目录下放一份清单，**编排和注册都从它派生**，杜绝「compose 里一个端口、后台又填另一个」的漂移：

```yaml
# mcp-services/echo/service.yaml
slug: echo                       # 唯一，小写连字符，2-64 字符（与 SLUG_RE 一致）
display_name: Echo 测试服务
description: 回显入参的最小 MCP 服务，用于打通链路
owner_team: platform
tags: [demo]
port: 8000                       # 容器内监听端口（模板统一 8000）
path: /mcp                       # MCP RPC 路径
rate_limit_qps: null             # null=不限；上线建议配一个值
required_env:                    # 该服务对接公司接口需要的环境变量"名字"（不含值）
  - HR_API_BASE                  # 值放在同目录 .env（gitignore），sync 脚本只校验是否齐全
  - HR_API_TOKEN
```

派生规则：
- 容器/服务名：`mcp-<slug>`
- 注册的 `endpoint_url`：`http://mcp-<slug>:<port><path>`，例 `http://mcp-echo:8000/mcp`

### 3.3 编排约定

- MCP 服务**不写 `ports:`**（不暴露宿主端口），只内网可达。
- 与 MCPsys 用**同一 project 名 `mcpsys`**：`compose.mcp.yaml` 顶部也写 `name: mcpsys`，启动用
  `docker compose -f compose.yaml -f compose.mcp.yaml up -d`（建议用 Makefile / `mcp.sh` 封装，避免每次手敲 `-f`）。
- MCP 服务**不进 gateway 的 `depends_on`**（运行时 resolve，松耦合）。可给自身加 `healthcheck`，便于 `docker compose ps` 观察。

`compose.mcp.yaml` 由 `sync_mcp_services.py --gen-compose` 生成，单个服务片段形如：

```yaml
name: mcpsys
services:
  mcp-echo:
    build: ./mcp-services/echo
    restart: unless-stopped
    env_file: ./mcp-services/echo/.env   # 注入对接公司接口的密钥（service.yaml 有 required_env 时才加）
    # 无 ports：仅 mcpsys_default 内网可达
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,json; urllib.request.urlopen(urllib.request.Request('http://localhost:8000/mcp', data=b'{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{}}', headers={'content-type':'application/json'}))"]
      interval: 15s
      timeout: 5s
      retries: 3
```

### 3.4 模板内容（Python + 官方 MCP SDK 示例）

> 语言不限；模板默认给 Python（streamable_http transport）。若用其它语言，只要：① 容器内监听约定端口；② 在 `<path>` 提供 MCP streamable_http endpoint（能响应 POST `initialize`，返回非 5xx）。

`mcp-services/_template/src/server.py`（占位示例，实施时按所选 SDK 落地）：

```python
# 用官方 mcp SDK 的 streamable_http；endpoint 暴露在 /mcp，监听 0.0.0.0:8000
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("__SLUG__", host="0.0.0.0", port=8000, streamable_http_path="/mcp")

@mcp.tool()
def ping(text: str) -> str:
    """示例工具：回显。"""
    return text

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

`Dockerfile`（统一暴露 8000）：

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
EXPOSE 8000
CMD ["python", "src/server.py"]
```

### 3.5 脚手架与同步脚本

`scripts/new_mcp_service.sh <slug> "<display_name>"`：
1. 校验 slug 合法（复用 `SLUG_RE` 同规则）、目录不存在；
2. `cp -r mcp-services/_template mcp-services/<slug>`；
3. 替换 `__SLUG__` / `__DISPLAY_NAME__` 占位符，写好 `service.yaml`；
4. 提示下一步：改业务代码 → `sync_mcp_services.py` → `up -d --build mcp-<slug>`。

`scripts/sync_mcp_services.py`（两件事，均幂等）：
- `--gen-compose`：扫描 `mcp-services/*/service.yaml` → 生成 `compose.mcp.yaml`。
- `--register`：登录控制面拿 token → 逐个服务 `GET /{slug}`：不存在 `POST` 创建，存在则 `PATCH`（对齐 `display_name/description/owner_team/tags/endpoint_url/rate_limit_qps`）。
  - 凭据来自环境变量（`MCPSYS_BASE` / `MCPSYS_USER` / `MCPSYS_PASSWORD`），账号需 operator+ 角色。
  - 默认两步都做；`--dry-run` 只打印 diff 不写。

> 归档语义注意：`DELETE /{slug}` 是软删（slug 改写为 `__archived_{id}`、status=disabled）。`service.yaml` 删除时同步脚本**不自动删服务**（避免误删历史），只告警提示手动归档，保护 `call_logs` 历史。

### 3.6 工具如何对接公司内部接口（HTTP 客户端 / 密钥约定 / 网络可达性）

绝大多数自研工具的本质是「包一层公司已有接口」。这里要分清两层调用，归属不同：

```
Agent ──①入站──▶ MCPsys 网关 ──②──▶ 你的 MCP 服务 ──③出站──▶ 公司内部系统（ERP/CRM/HR…）
         (鉴权/限流/日志由网关统一管，模板白送)              (你的业务逻辑，模板只提供脚手架)
```

模板**不替你写 ③ 的业务**，但把 ③ 周边的重复杂活标准化掉：现成 HTTP 客户端、密钥读取位置、统一报错。你只写「调哪个接口、传什么、返回怎么整理」。

#### (a) HTTP 客户端约定

模板在 `src/server.py` 里预置一个带超时/重试的 `httpx` 客户端，工具直接复用，不必每个服务重配。示例（对接公司 HR 接口）：

```python
import os, httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hr", host="0.0.0.0", port=8000, streamable_http_path="/mcp")

# 密钥从环境变量读（见下 (b)），不写死、不进 git
HR_API_BASE = os.environ["HR_API_BASE"]
HR_API_TOKEN = os.environ["HR_API_TOKEN"]
# 是否校验公司接口的 TLS 证书。公司内部多为自签证书 → 默认 false 跳过校验。
# 与网关上游的 PROXY_VERIFY_TLS 互不相干，这是本服务"出站"调用的开关。
VERIFY_TLS = os.environ.get("UPSTREAM_VERIFY_TLS", "false").lower() == "true"

# 模板预置：复用一个长连接客户端，统一超时；verify 由环境变量控制
_client = httpx.Client(base_url=HR_API_BASE, timeout=10,
                       verify=VERIFY_TLS,
                       headers={"Authorization": f"Bearer {HR_API_TOKEN}"})

@mcp.tool()
def get_employee(emp_id: str) -> dict:
    """根据工号查员工信息。"""
    try:
        resp = _client.get(f"/employees/{emp_id}")
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:           # 公司接口返回 4xx/5xx
        return {"error": f"上游返回 {e.response.status_code}"}
    except httpx.RequestError as e:              # 连不上 / 超时
        return {"error": f"无法访问公司接口: {e}"}
```

> 报错口径：工具内部把上游异常转成**结构化返回**（而不是抛出去），让 Agent 能读懂失败原因；同时 MCPsys 网关那一层照常记录 ② 段的调用日志。

#### (b) 密钥约定（重要：不进 git、单服务一份）

- 每个服务目录放 `.env`（**gitignore**，存真实值）+ `.env.example`（提交，只列变量名供参考）。模板 `.env.example` 预置标准开关 `UPSTREAM_VERIFY_TLS=false`（默认跳过出站证书校验，连自签证书的公司接口开箱即用）。
- `service.yaml` 的 `required_env` 列出**变量名清单**（只声明依赖，不含值），作为文档 + 校验依据。
- 生成的 compose 片段用 `env_file: ./mcp-services/<slug>/.env` 把密钥注入容器。
- `sync_mcp_services.py` 在 `--gen-compose` / 起服务前校验：`required_env` 里每个变量在 `.env` 中都有非空值，缺失则**报错中止**，避免起了个连不上公司接口的空壳服务。
- 全局根 `.gitignore` 增加 `mcp-services/*/.env` 一条。

#### (c) 网络可达性检查清单（部署前逐项确认）

容器要能从 docker 内网"出去"访问公司系统，常见卡点：

- [ ] **能解析公司接口域名**：容器内 `nslookup <公司接口域名>` 能拿到 IP（内网 DNS 是否对 docker 网络可见）。
- [ ] **能连通**：容器内 `curl -sS -m 5 <公司接口>` 有响应（防火墙 / 安全组放行了这台服务器的出向）。
- [ ] **IP 白名单**：若公司系统按来源 IP 放行，把本服务器出口 IP 加白（docker 默认用宿主 IP 出网，一般无需特殊配置）。
- [ ] **走 VPN/专线的情况**：确认容器网络能用到宿主的 VPN 路由；必要时该服务用 `network_mode: host` 或加静态路由（属个别服务的例外，不改全局约定）。
- [ ] **TLS（出站证书校验）**：公司接口多为自签/内部 CA 的 https，模板客户端默认 `UPSTREAM_VERIFY_TLS=false` **跳过证书校验**即可直连。若该服务所在链路不可信、想严格校验，则设 `UPSTREAM_VERIFY_TLS=true` 并把公司 CA 挂进容器（`verify=` 指向 CA 文件）。注意这是**服务自身的出站调用**，与网关上游的 `PROXY_VERIFY_TLS`（②段）完全独立、互不影响。

模板的 `README.md` 会带一份「填 `.env` → 跑可达性检查 → `up -d`」的清单，新服务照着走即可。

## 4. 端到端调用链（不变，仅上游变内网）

```
Agent ──Bearer mcpk_…──▶ nginx:8088 ──▶ gateway /mcp/echo
   ① 鉴权 apikey  ② resolve slug→endpoint  ③ 应用×服务白名单  ④ 限流  ⑤ 转发
                                                              │
                                          http://mcp-echo:8000/mcp（内网）
                                                              │
                                                       ⑥ 异步写 call_logs
```

授权仍是默认拒绝：新服务注册后，需在「应用」侧把该服务加入 `service_ids` 白名单（`smoke.sh:71` 同款操作），Key 才能调通。

## 5. 实施阶段

**阶段 0 — 验证网络互通（~10 分钟）**
- 临时起一个 busybox 加入 `mcpsys_default`，从 gateway 容器 `curl http://<name>:port` 确认服务名可达。产出：确认 `-f` 合并 + 同 project 网络方案成立。

**阶段 1 — 模板 + echo 示例端到端打通**
- 落地 `mcp-services/_template` 与 `mcp-services/echo`；
- 手动写 `compose.mcp.yaml`（echo 一项）；
- `up -d --build` → 后台注册 echo（endpoint `http://mcp-echo:8000/mcp`）→ 建应用授权 → 用 Key 经网关 `POST /mcp/echo` 调通 → 看到 `call_logs` 落库、健康检查变 healthy。
- 验收：复用 smoke 思路跑一遍（可临时把 `smoke.sh` 的 `endpoint_url` 指到 `http://mcp-echo:8000/mcp` 验证内网链路）。

**阶段 2 — 脚本化**
- `new_mcp_service.sh` + `sync_mcp_services.py`（`--gen-compose` / `--register` / `--dry-run`）；
- 用脚本重新生成 echo 的 compose 片段与注册，确认与手写一致。

**阶段 3 — 文档与封装**
- `README.md` 增一节「新增一个 MCP 服务」（三步：`new_mcp_service.sh` → 写代码 → `sync_mcp_services.py && docker compose -f … up -d --build mcp-<slug>`）；
- `docs/deployment.md` 增「MCP 服务编排 / 迭代 / 下线」章节；
- 提供 `Makefile` 或 `mcp.sh` 封装常用 `-f` 组合命令。

## 6. 「日常操作」一览（落地后）

| 操作 | 命令 |
|---|---|
| 新增服务 | `scripts/new_mcp_service.sh foo "Foo 服务"` → 改 `src/server.py` |
| 生成编排 + 注册 | `scripts/sync_mcp_services.py`（默认 gen-compose + register）|
| 起 / 改一个服务 | `docker compose -f compose.yaml -f compose.mcp.yaml up -d --build mcp-foo` |
| 看某服务健康 | 后台服务详情页（health_checker 自动探活）|
| 下线服务 | 后台归档（软删）→ 删 `mcp-services/foo` 目录 → 重生成 compose |

## 7. 风险与注意

- **健康检查路径**：`endpoint_url` 必须是 MCP 的 RPC 路径（`/mcp`），不是 `/healthz`；探活发的是 `initialize`，SDK 默认会返回 200/4xx → 判定 healthy。实施时用 echo 实测确认。
- **限流默认不限**：`rate_limit_qps` 默认 null，上线服务记得在 `service.yaml` 配置。
- **project / 网络一致性**：两个 compose 文件必须落到同一 project（均 `name: mcpsys`）且用 `-f a -f b` 合并，否则不在同一网络、服务名不可达。
- **资源隔离**：同机共栈，单个 MCP 服务 OOM/CPU 飙升可能影响邻居；阶段 3 可按需给容器加 `mem_limit` / `cpus`。
- **构建时长**：服务多了 `docker compose build` 变慢；用 `--build mcp-<slug>` 只构建单个。
- **多副本扩容**：超出 MVP（≤100 QPS）后，MCP 服务或 gateway 多副本需 nginx 上游 resolver，属 v1，本方案不覆盖。

## 8. 决策记录（2026-06-30 已定）

1. **MCP 服务默认技术栈**：Python + 官方 `mcp`（FastMCP），与后端同栈。其它语言按需另开模板（只需遵守端口/路径/协议约定）。
2. **同步脚本删除策略**：只告警、不自动删——本地删了服务目录/清单，脚本仅提示，需人工去后台软删，保护 `call_logs` 历史。
3. **命令封装**：加 `Makefile`，封装 `docker compose -f compose.yaml -f compose.mcp.yaml …`（`make up` / `make build s=mcp-foo` 等），避免手敲长 `-f` 串。
