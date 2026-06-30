"""__DISPLAY_NAME__ —— MCP 服务（由模板生成）。

约定：
- 监听 0.0.0.0:8000，MCP streamable-http endpoint 暴露在 /mcp
  （这两项与 service.yaml 的 port/path 一致；一般不用改）
- 对接公司接口的密钥从环境变量读（见 .env.example），不写死、不进 git

把下面的 example 工具替换成你的业务即可。
"""
import os

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("__SLUG__", host="0.0.0.0", port=8000, streamable_http_path="/mcp")

# --- 对接公司内部接口的出站客户端（按需修改） ---
# 公司接口基地址，例 https://erp.corp.local
UPSTREAM_BASE = os.environ.get("UPSTREAM_BASE", "")
# 出站调用是否校验 TLS 证书。公司内部多为自签证书 → 默认 false 跳过校验。
# 注意：这是本服务"出站"调用的开关，与网关上游的 PROXY_VERIFY_TLS 互不相干。
UPSTREAM_VERIFY_TLS = os.environ.get("UPSTREAM_VERIFY_TLS", "false").lower() == "true"

# 复用一个长连接客户端，统一超时；verify 由环境变量控制
_client = httpx.Client(
    base_url=UPSTREAM_BASE,
    timeout=10,
    verify=UPSTREAM_VERIFY_TLS,
)


@mcp.tool()
def example(text: str) -> str:
    """示例工具：把它替换成你的业务。

    调公司接口的写法（取消注释并按需修改）：

        try:
            resp = _client.get("/some/path", params={"q": text})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"上游返回 {e.response.status_code}"}
        except httpx.RequestError as e:
            return {"error": f"无法访问公司接口: {e}"}
    """
    return f"__SLUG__ received: {text}"


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
