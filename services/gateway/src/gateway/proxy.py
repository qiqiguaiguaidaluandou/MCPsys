import time
from dataclasses import dataclass

import httpx

# Headers that should NOT be forwarded upstream (managed by httpx or hop-by-hop)
HOP_BY_HOP = {
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "authorization",  # Gateway's own bearer; do not forward
}


class ProxyTimeout(Exception):
    pass


@dataclass
class ProxyResult:
    status: int
    headers: dict[str, str]
    body: bytes
    duration_ms: int


def filter_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP}


async def forward(
    *,
    client: httpx.AsyncClient,
    upstream_url: str,
    body: bytes,
    headers: dict[str, str],
    extra_headers: dict[str, str] | None = None,
) -> ProxyResult:
    """Forward a single MCP JSON-RPC POST upstream and return the full response.

    Streamable HTTP allows either a single JSON response or an SSE event stream.
    For MVP we read the full body (10-100 QPS makes streaming optimization unnecessary).
    """
    out_headers = filter_headers(headers)
    if extra_headers:
        out_headers.update(extra_headers)

    started = time.perf_counter()
    try:
        resp = await client.post(upstream_url, content=body, headers=out_headers)
    except httpx.TimeoutException as e:
        raise ProxyTimeout(str(e)) from e
    duration_ms = int((time.perf_counter() - started) * 1000)

    return ProxyResult(
        status=resp.status_code,
        headers=dict(resp.headers),
        body=resp.content,
        duration_ms=duration_ms,
    )
