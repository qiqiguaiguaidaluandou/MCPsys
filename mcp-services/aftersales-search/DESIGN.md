# MCP Server 方案文档

## 1. 目标

搭建一个个人可扩展的 MCP（Model Context Protocol）服务，统一把外部能力与自研接口以标准协议暴露给 Claude Code / Claude Desktop / Cursor 等 MCP 客户端。

首版目标：

- 提供通用工具：**查询天气**（基于 wttr.in，免 API key）。
- 提供通用包装：将**自有 HTTP 接口**以 MCP tool 的形式对外暴露。
- 支持 HTTP 传输，便于多客户端接入与后续远程部署。

## 2. 技术选型

| 维度 | 选择 | 理由 |
|---|---|---|
| 语言 | Python ≥ 3.10 | 生态丰富，FastMCP 装饰器写法最简洁 |
| MCP SDK | `mcp` 官方包（FastMCP） | 官方维护，文档全，升级稳定 |
| HTTP 客户端 | `httpx`（异步） | 与 FastMCP 的 async 天然契合 |
| 传输方式 | `streamable-http` | 新一代 MCP 远程传输，单一 HTTP endpoint |
| 天气数据源 | wttr.in | 免 key、JSON (`?format=j1`) 可直接消费 |
| 构建系统 | hatchling | PEP 621 标准，零配置 |

## 3. 项目结构

```
mcpserver/
├── pyproject.toml             # 项目元数据 + 依赖 + 入口脚本
├── .env.example               # 环境变量样例
├── DESIGN.md                  # 本文档
└── src/mcpserver/
    ├── __init__.py
    ├── server.py              # 入口：创建 FastMCP 实例并启动
    ├── config.py              # 读取环境变量：HOST/PORT/自有 API 配置
    └── tools/
        ├── __init__.py
        ├── weather.py         # get_weather / get_forecast
        └── my_api.py          # my_api_get / my_api_post（自研接口通用包装）
```

分层原则：

- **server.py**：只负责装配，不写业务逻辑。
- **config.py**：所有运行时可变量统一从环境变量读，避免硬编码。
- **tools/**：一个文件一个主题域，对外只暴露一个 `register(mcp)` 函数，便于独立测试与按需开关。

## 4. 核心模块

### 4.1 `server.py`（入口）

```python
from mcp.server.fastmcp import FastMCP
from mcpserver.config import HOST, PORT
from mcpserver.tools import my_api, weather

mcp = FastMCP("mcpserver", host=HOST, port=PORT)
weather.register(mcp)
my_api.register(mcp)

def main() -> None:
    mcp.run(transport="streamable-http")
```

- 通过 `pyproject.toml` 的 `[project.scripts]` 暴露为 `mcpserver` 可执行命令。
- 默认监听 `127.0.0.1:8765`，MCP endpoint 为 `http://127.0.0.1:8765/mcp`。

### 4.2 `tools/weather.py`

封装 wttr.in，对外两个 tool：

- `get_weather(location: str) -> dict`
  返回当前温度、体感、湿度、风速、天气描述、观测时间。
- `get_forecast(location: str, days: int = 3) -> list[dict]`
  返回未来 1–3 天每日最高/最低温、日出日落、白天天气描述。

调用示例：`https://wttr.in/Beijing?format=j1`，从 `current_condition[0]` 与 `weather[]` 抽取结构化字段后返回。

### 4.3 `tools/my_api.py`

通用自研 API 包装，适合初期还没定型 endpoint 的阶段：

- `my_api_get(path, params=None) -> dict`
- `my_api_post(path, body=None) -> dict`

两者都会自动拼接 `MY_API_BASE_URL`，并在存在 `MY_API_TOKEN` 时带上 `Authorization: Bearer …`。

### 4.4 `config.py`

| 变量 | 默认 | 说明 |
|---|---|---|
| `MCP_HOST` | `127.0.0.1` | 服务监听地址 |
| `MCP_PORT` | `8765` | 服务监听端口 |
| `MY_API_BASE_URL` | `https://httpbin.org` | 自研 API 基础地址 |
| `MY_API_TOKEN` | *(空)* | Bearer Token，可选 |

## 5. 启动与接入

### 5.1 本地启动

```bash
cd /root/kqspace/mcpserver
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
mcpserver               # 监听 127.0.0.1:8765
```

### 5.2 Claude Code 接入

```bash
claude mcp add --transport http mcpserver http://127.0.0.1:8765/mcp
```

接入后 `/mcp` 能看到 `mcpserver`，可调用 `get_weather`、`get_forecast`、`my_api_get`、`my_api_post`。

### 5.3 调试工具

- `npx @modelcontextprotocol/inspector` 启动官方 Inspector，用 Streamable HTTP 连到同一地址可视化调用。
- 直接 `curl` 亦可，但 MCP 协议握手后才会暴露 tool 列表，Inspector 更直观。

## 6. 扩展方式

### 6.1 新增一个 tool 主题

1. 新建 `src/mcpserver/tools/<topic>.py`，实现：

   ```python
   def register(mcp):
       @mcp.tool()
       async def do_something(arg: str) -> dict:
           """一句话说明工具用途与参数语义。"""
           ...
   ```

2. 在 `server.py` 加 `<topic>.register(mcp)`。

### 6.2 把自研接口改为强类型 tool

`my_api_get/my_api_post` 适合原型阶段。接口稳定后，**建议一个业务动作一个 tool**，例如：

```python
@mcp.tool()
async def list_orders(user_id: int, status: str = "paid") -> list[dict]:
    """查询指定用户的订单列表。"""
    ...
```

原因：模型是按 tool 的 **docstring + 参数签名** 选择工具的，越具体越不容易误用。

## 7. 安全与部署建议

| 场景 | 建议 |
|---|---|
| 本地单机 | 保持 `127.0.0.1` 监听，避免误暴露 |
| 公网部署 | 前置 nginx/Caddy，启用 HTTPS；在 MCP endpoint 前加鉴权头/IP 白名单 |
| Token 管理 | `MY_API_TOKEN` 等敏感值只从环境变量读，禁止写入代码或日志 |
| 超时 | 所有 `httpx` 调用均设置 `timeout`（weather 10s，my_api 15s），防止 tool 调用挂起 |
| 错误处理 | 目前使用 `raise_for_status()` 直接透传 HTTP 异常；稳定后可统一包装为结构化错误返回 |

## 8. 后续规划

- [ ] 增加缓存层（如 wttr.in 同一城市 5 分钟内复用），减少外部依赖抖动。
- [ ] 引入结构化日志（`structlog`），输出 tool 调用耗时与失败率。
- [ ] 把 `my_api_*` 逐步替换为业务强类型 tool。
- [ ] 增加 CI：lint（ruff）+ type check（mypy）+ 针对 tool 的最小集成测试。
- [ ] 远程部署方案：Dockerfile + 反向代理 + Token 鉴权中间件。
