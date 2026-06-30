"""进程级共享的 httpx 异步客户端。

所有对外 HTTP 调用都应通过 get_client() 取同一个实例，复用连接池与 keep-alive，
避免每次请求新建客户端的开销。客户端在首次调用（已处于事件循环内）时惰性创建。
"""

import httpx

_DEFAULT_TIMEOUT = 15
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """返回共享的 httpx 异步客户端，不存在或已关闭则新建。"""
    global _client
    if _client is None or _client.is_closed:
        # verify=False：绕过 SSL 证书验证（接口为自签名/内网证书）
        _client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, verify=False)
    return _client


async def aclose() -> None:
    """关闭共享客户端（用于进程退出或测试清理）。"""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
