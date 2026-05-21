#!/usr/bin/env python3
"""端到端验证一个已注册的 MCP 服务是否真的能用。

以真实调用者身份，经网关（POST /mcp/{slug}）完成 MCP Streamable HTTP 握手
（initialize → notifications/initialized），再 tools/list 列出工具，可选 tools/call。
能列出工具 = 这个服务通过本系统端到端可用。

为什么不用官方 MCP SDK：本系统网关是 POST-only 代理（gateway 只有 POST /mcp/{slug}），
不实现 MCP 规范里可选的 GET SSE 流。官方 SDK 会去开 GET 流；规范要求客户端容忍 405、
但不同 SDK 健壮性不一。验证场景要的是确定性，所以这里只走 POST，手动管理 Mcp-Session-Id。

用法:
    export MCPSYS_BASE_URL=https://mcp.com        # 或 http://localhost:8088
    export MCPSYS_API_KEY=mcpk_xxx                # 被授权访问该服务的 key
    python scripts/verify_service.py --slug progress-search

    # 顺便实际调一个工具
    python scripts/verify_service.py --slug progress-search --call <工具名> --args '{"q":"hi"}'
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

PROTOCOL_VERSION = "2025-06-18"

# 网关层（FastAPI HTTPException）的拒绝，body 形如 {"detail": "..."}，根本没转发到上游
_GATEWAY_LAYER = {
    401: "鉴权失败（API key 缺失/无效/吊销/过期）",
    403: "授权失败（该应用未被授权访问此服务）",
    404: "服务不存在（slug 未注册）",
    429: "被限流",
    502: "代理失败（连不上上游）",
    504: "上游超时",
}


class VerifyError(RuntimeError):
    pass


def _parse_jsonrpc(resp: httpx.Response) -> dict:
    """网关透传上游响应，可能是 application/json 或 text/event-stream，都解析成 JSON-RPC dict。"""
    text = resp.text
    if "text/event-stream" in resp.headers.get("content-type", ""):
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith("data:"):
                payload = line[len("data:"):].strip()
                if payload:
                    try:
                        msg = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(msg, dict) and "jsonrpc" in msg:
                        return msg
        raise VerifyError(f"SSE 响应里没有可解析的 JSON-RPC 消息:\n{text[:800]}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise VerifyError(f"响应不是合法 JSON (HTTP {resp.status_code}):\n{text[:800]}") from e


def _check_gateway(resp: httpx.Response) -> None:
    """网关层拒绝 → 抛出清晰错误（这些请求未转发到上游）。"""
    if resp.status_code < 400:
        return
    detail = None
    try:
        body = resp.json()
        if isinstance(body, dict):
            detail = body.get("detail")
    except (json.JSONDecodeError, ValueError):
        pass
    # JSON-RPC 错误（如缺 session id）是上游回的，交给上层按 JSON-RPC 处理，这里不拦
    if detail is not None:
        layer = _GATEWAY_LAYER.get(resp.status_code, "网关返回错误")
        raise VerifyError(f"[网关 HTTP {resp.status_code}] {layer}：{detail} —— 未转发到上游")


def _post(client, url, headers, body, session_id=None):
    h = dict(headers)
    if session_id:
        h["Mcp-Session-Id"] = session_id
    return client.post(url, headers=h, content=json.dumps(body).encode())


def verify(base_url, slug, api_key, tool, tool_args, timeout) -> int:
    url = f"{base_url.rstrip('/')}/mcp/{slug}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    with httpx.Client(timeout=timeout) as client:
        # ── 第 1 层：网关链路 + initialize 握手 ────────────────────────────
        print(f"[1/3] 连接网关 + 鉴权 + 握手  →  POST {url} (initialize)")
        resp = _post(client, url, headers, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                       "clientInfo": {"name": "verify_service.py", "version": "1.0"}},
        })
        _check_gateway(resp)
        print(f"      HTTP {resp.status_code}  x-request-id={resp.headers.get('x-request-id')}")
        init = _parse_jsonrpc(resp)
        if "error" in init:
            raise VerifyError(f"上游拒绝 initialize: {init['error']}（端点在线，但 MCP 握手失败）")
        session_id = resp.headers.get("mcp-session-id")
        server_info = init.get("result", {}).get("serverInfo", {})
        print(f"      ✓ 网关已转发，上游完成 MCP 握手  serverInfo={server_info}  session={session_id!r}")

        # 握手完成通知（多数有状态服务器要求此后才接收其它请求）
        _check_gateway(_post(client, url, headers,
                             {"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id))

        # ── 第 2 层：tools/list ───────────────────────────────────────────
        print(f"[2/3] 列出工具  →  POST {url} (tools/list)")
        resp = _post(client, url, headers, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session_id)
        _check_gateway(resp)
        listed = _parse_jsonrpc(resp)
        if "error" in listed:
            raise VerifyError(f"上游拒绝 tools/list: {listed['error']}")
        tools = listed.get("result", {}).get("tools", [])
        print(f"      ✓ 工具数: {len(tools)}")
        for t in tools:
            print(f"        - {t.get('name')}: {(t.get('description') or '')[:80]}")
        if not tools:
            print("      ⚠ 服务可达且是合法 MCP，但未暴露任何工具")

        # ── 第 3 层（可选）：tools/call ───────────────────────────────────
        if tool:
            print(f"[3/3] 调用工具 {tool}  →  POST {url} (tools/call)")
            resp = _post(client, url, headers, {
                "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": tool, "arguments": tool_args},
            }, session_id)
            _check_gateway(resp)
            called = _parse_jsonrpc(resp)
            if "error" in called:
                raise VerifyError(f"上游拒绝 tools/call: {called['error']}")
            print("      ✓ 调用结果:")
            print(json.dumps(called.get("result", {}), ensure_ascii=False, indent=2))
        else:
            print("[3/3] （跳过 tools/call，加 --call <工具名> 可实际调用）")

    print(f"\n✅ 验证通过：服务 '{slug}' 端到端可用（网关 → 上游 MCP 握手 → 工具可列）")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="端到端验证 MCP 服务是否可用")
    p.add_argument("--base-url", default=os.environ.get("MCPSYS_BASE_URL"),
                   help="网关地址，如 https://mcp.com 或 http://localhost:8088（或环境变量 MCPSYS_BASE_URL）")
    p.add_argument("--slug", required=True, help="服务 slug，如 progress-search")
    p.add_argument("--api-key", default=os.environ.get("MCPSYS_API_KEY"),
                   help="被授权的 API key 明文（mcpk_ 开头；或环境变量 MCPSYS_API_KEY）")
    p.add_argument("--call", default=None, help="可选：要实际调用的工具名")
    p.add_argument("--args", default="{}", help="可选：工具参数 JSON 字符串")
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args()

    if not args.base_url:
        p.error("缺少 --base-url（或环境变量 MCPSYS_BASE_URL）")
    if not args.api_key:
        p.error("缺少 --api-key（或环境变量 MCPSYS_API_KEY）")
    try:
        tool_args = json.loads(args.args)
    except json.JSONDecodeError as e:
        p.error(f"--args 不是合法 JSON: {e}")

    try:
        return verify(args.base_url, args.slug, args.api_key, args.call, tool_args, args.timeout)
    except VerifyError as e:
        print(f"\n❌ 验证未通过：{e}", file=sys.stderr)
        return 1
    except httpx.HTTPError as e:
        print(f"\n❌ 网络错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
