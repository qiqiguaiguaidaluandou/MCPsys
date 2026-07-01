"""文件下载 HTTP 端点：把保存在服务器上的文件（如 FQC 报告）通过链接暴露给用户下载。

挂载到 MCP 服务同一个 starlette app 上，路由为 GET /files/{filename}，
从 config.FQC_REPORT_DIR 读取文件。工具用 build_download_url() 生成下载链接。
"""

import os
import threading
import time
from urllib.parse import quote

from starlette.responses import FileResponse, PlainTextResponse
from starlette.routing import Route

from mcpserver import config

# 下载路由前缀。可经环境变量覆盖以做命名空间隔离（避免与前端 / 或多服务相互抢路径），
# 例如 /mcp-files/aftersales-search —— 需与 nginx 对应 location 一致。
DOWNLOAD_PREFIX = "/" + os.getenv("DOWNLOAD_PREFIX", "/files").strip("/")


def _ttl_seconds() -> float:
    return config.FQC_REPORT_TTL_HOURS * 3600


def _is_expired(path: str) -> bool:
    """文件是否已超过有效期。TTL<=0 视为永不过期；stat 失败按已过期处理。"""
    ttl = _ttl_seconds()
    if ttl <= 0:
        return False
    try:
        return (time.time() - os.path.getmtime(path)) > ttl
    except OSError:
        return True


async def _download(request):
    # os.path.basename 去掉任何目录成分，防止 ../ 目录穿越
    filename = os.path.basename(request.path_params["filename"])
    path = os.path.join(config.FQC_REPORT_DIR, filename)
    # 过期文件按不存在处理：链接在满 TTL 那一刻即失效，不依赖清扫任务是否恰好跑过。
    if not filename or not os.path.isfile(path) or _is_expired(path):
        return PlainTextResponse("Not found", status_code=404)
    return FileResponse(path, filename=filename)


def sweep_expired() -> int:
    """删除 FQC_REPORT_DIR 下所有已过期文件，返回删除数量。供后台线程周期调用。"""
    directory = config.FQC_REPORT_DIR
    if _ttl_seconds() <= 0 or not os.path.isdir(directory):
        return 0
    removed = 0
    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        if os.path.isfile(path) and _is_expired(path):
            try:
                os.remove(path)
                removed += 1
            except OSError:
                # 可能被并发删除或权限问题；跳过，下轮再试
                pass
    return removed


def start_sweeper() -> None:
    """启动后台守护线程，周期清扫过期文件。TTL<=0 时不启动（永不过期）。"""
    if _ttl_seconds() <= 0:
        return
    interval = max(60.0, config.FQC_REPORT_SWEEP_INTERVAL_MINUTES * 60)

    def _loop() -> None:
        while True:
            try:
                sweep_expired()
            except Exception:
                # 守护线程绝不能因单次异常退出，否则磁盘将不再回收
                pass
            time.sleep(interval)

    threading.Thread(target=_loop, daemon=True, name="fqc-report-sweeper").start()


def build_download_url(filename: str) -> str:
    """根据文件名拼出完整下载链接。PUBLIC_BASE_URL 未配置时返回相对路径。"""
    return f"{config.PUBLIC_BASE_URL}{DOWNLOAD_PREFIX}/{quote(filename)}"


def register(app) -> None:
    """把下载路由挂到 starlette app 上。"""
    app.routes.append(
        Route(f"{DOWNLOAD_PREFIX}/{{filename:path}}", _download, methods=["GET"])
    )
