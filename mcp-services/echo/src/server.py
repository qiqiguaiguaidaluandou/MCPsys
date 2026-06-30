"""Echo 测试 MCP 服务：回显入参，用于打通 MCPsys 端到端链路。

监听 0.0.0.0:8000，MCP streamable-http endpoint 在 /mcp。
不对接任何公司接口，因此无需密钥。
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("echo", host="0.0.0.0", port=8000, streamable_http_path="/mcp")


@mcp.tool()
def ping(text: str) -> str:
    """回显输入的文本。"""
    return text


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
