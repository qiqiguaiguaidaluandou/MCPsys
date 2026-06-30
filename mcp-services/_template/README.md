# __DISPLAY_NAME__（MCP 服务）

由 `scripts/new_mcp_service.sh` 从模板生成。本服务跑在 MCPsys 同一 docker 网络内，
对外不暴露端口，流量统一经网关 `POST /mcp/__SLUG__` 进来（鉴权 / 限流 / 日志由网关负责）。

## 目录

- `src/server.py` —— 业务代码，把 `example` 工具换成你的工具
- `service.yaml` —— 服务清单（slug / 端口 / 路径 / 限流 / required_env），编排与注册的单一信息源
- `requirements.txt` —— Python 依赖
- `.env.example` → 复制为 `.env` 填密钥（`.env` 不进 git）

## 上线前清单

1. **写业务**：编辑 `src/server.py`，定义你的工具；要调公司接口就用预置的 `_client`。
2. **配密钥**：`cp .env.example .env` 并填真实值；把用到的变量名同步写进 `service.yaml` 的 `required_env`。
3. **网络可达性自检**（确认容器能访问到公司系统）：
   ```bash
   # 起服务后，进容器测对公司接口的连通性
   docker compose -f compose.yaml -f compose.mcp.yaml exec mcp-__SLUG__ \
       python -c "import os,httpx; print(httpx.get(os.environ['UPSTREAM_BASE'], timeout=5, verify=False).status_code)"
   ```
   连不上 → 检查内网 DNS、防火墙出向、IP 白名单、VPN 路由（见方案文档 §3.6(c)）。
4. **注册 + 起服务**（在仓库根目录）：
   ```bash
   scripts/sync_mcp_services.py          # 生成 compose 片段 + 注册到控制面
   docker compose -f compose.yaml -f compose.mcp.yaml up -d --build mcp-__SLUG__
   ```
5. **授权**：在 Web 后台把本服务加入某个「应用」的服务白名单，该应用的 API Key 才能调通（默认拒绝）。
