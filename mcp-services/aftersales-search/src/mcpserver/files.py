"""文件下载 HTTP 端点：把保存在服务器上的文件（如 FQC 报告）通过链接暴露给用户下载。

挂载到 MCP 服务同一个 starlette app 上，路由为 GET /files/{filename}，
从 config.FQC_REPORT_DIR 读取文件。工具用 build_download_url() 生成下载链接。
"""

import os
from urllib.parse import quote

from starlette.responses import FileResponse, PlainTextResponse
from starlette.routing import Route

from mcpserver import config

# 下载路由前缀。可经环境变量覆盖以做命名空间隔离（避免与前端 / 或多服务相互抢路径），
# 例如 /mcp-files/aftersales-search —— 需与 nginx 对应 location 一致。
DOWNLOAD_PREFIX = "/" + os.getenv("DOWNLOAD_PREFIX", "/files").strip("/")


async def _download(request):
    # os.path.basename 去掉任何目录成分，防止 ../ 目录穿越
    filename = os.path.basename(request.path_params["filename"])
    path = os.path.join(config.FQC_REPORT_DIR, filename)
    if not filename or not os.path.isfile(path):
        return PlainTextResponse("Not found", status_code=404)
    return FileResponse(path, filename=filename)


def build_download_url(filename: str) -> str:
    """根据文件名拼出完整下载链接。PUBLIC_BASE_URL 未配置时返回相对路径。"""
    return f"{config.PUBLIC_BASE_URL}{DOWNLOAD_PREFIX}/{quote(filename)}"


def register(app) -> None:
    """把下载路由挂到 starlette app 上。"""
    app.routes.append(
        Route(f"{DOWNLOAD_PREFIX}/{{filename:path}}", _download, methods=["GET"])
    )
