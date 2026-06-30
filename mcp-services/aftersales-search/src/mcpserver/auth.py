"""统一鉴权模块：JWT 生成与缓存、登录换票据、带 401 自愈的请求原语。

所有需要 JWT 鉴权的工具都应通过这里取 token / 发请求，共享同一份缓存：
- 简单 JWT 鉴权（token 直接放 Authorization 头）的接口：用 `post_with_jwt`。
- 需要"JWT 换票据再调用"的接口（如 MES）：用 `get_ticket` 拿票据后再 `post_with_jwt`。

token / ticket 过期或被服务端拒绝（401/403）时，缓存会被清空并自动重试一次，
不会让一个坏 token 在整个 TTL 内毒化所有接口。
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import jwt

from mcpserver import config, http_client

_JWT_TTL_MINUTES = 60
_AUTH_REFRESH_BUFFER_SECONDS = 5 * 60

# JWT 缓存：按 (secret, issuer) 凭证集分桶。同一套凭证的接口共享一份 token，
# 不同凭证集（如 LOGIN_URL 用的独立凭证）各自缓存、互不影响。
_jwt_cache: dict[tuple[str, str], dict] = {}
_jwt_lock = asyncio.Lock()

# Ticket 缓存：仅"JWT 换票据"链路（如 MES）使用。
_ticket_cache: dict = {"ticket": None, "inv_org_id": None, "expires_at": 0.0}
_ticket_lock = asyncio.Lock()

_AUTH_FAIL_STATUS = (401, 403)


def _create_jwt_token(secret: str, issuer: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": issuer,
        "exp": int((now + timedelta(minutes=_JWT_TTL_MINUTES)).timestamp()),
        "sub": "",
        "aud": "",
        "nbf": int((now - timedelta(minutes=10)).timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


async def _get_jwt_token(secret: str, issuer: str) -> str:
    """返回指定凭证集缓存中的 JWT；不存在或已过期则本地重新生成并写回缓存。"""
    key = (secret, issuer)
    now = time.time()
    entry = _jwt_cache.get(key)
    if entry and now < entry["expires_at"]:
        return entry["token"]
    async with _jwt_lock:
        now = time.time()
        entry = _jwt_cache.get(key)
        if entry and now < entry["expires_at"]:
            return entry["token"]
        token = _create_jwt_token(secret, issuer)
        _jwt_cache[key] = {
            "token": token,
            "expires_at": now + _JWT_TTL_MINUTES * 60 - _AUTH_REFRESH_BUFFER_SECONDS,
        }
        return token


def invalidate_jwt(secret: str, issuer: str) -> None:
    """作废指定凭证集的 JWT 缓存，下次取 token 时强制重新生成。"""
    entry = _jwt_cache.get((secret, issuer))
    if entry:
        entry["expires_at"] = 0.0


def invalidate_ticket() -> None:
    """作废 ticket 缓存，下次取票据时强制重新登录。"""
    _ticket_cache["expires_at"] = 0.0


async def post_with_jwt(
    url: str, body: dict, *, secret: str | None = None, issuer: str | None = None
) -> dict:
    """带 JWT 鉴权发 POST 并返回 JSON。

    默认用主凭证集（config.JWT_SECRET / JWT_ISSUER）；需要独立凭证的接口
    （如 LOGIN_URL）显式传入 secret / issuer。token 取自对应凭证集的缓存。
    若服务端返回 401/403（视为 token 失效），清空该凭证集缓存并用新 token
    重试一次；仍失败则抛出 HTTP 异常。
    """
    secret = secret or config.JWT_SECRET
    issuer = issuer or config.JWT_ISSUER
    client = http_client.get_client()
    for attempt in range(2):
        token = await _get_jwt_token(secret, issuer)
        r = await client.post(url, json=body, headers={"Authorization": f"Bearer {token}"})
        if r.status_code in _AUTH_FAIL_STATUS and attempt == 0:
            invalidate_jwt(secret, issuer)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("unreachable")  # 循环必在上面 return 或 raise


async def _login_for_ticket() -> tuple[str, int]:
    body = {
        "Parameters": [
            {"Value": config.LOGIN_USERNAME},
            {"Value": config.LOGIN_PASSWORD},
        ],
        "ApiType": "AuthenticationController",
        "Method": "Login",
        "Context": None,
    }
    data = await post_with_jwt(
        config.LOGIN_URL,
        body,
        secret=config.LOGIN_JWT_SECRET,
        issuer=config.LOGIN_JWT_ISSUER,
    )
    if not data.get("Success"):
        raise RuntimeError(f"Login failed: {data.get('Message')}")
    ctx = data.get("Context") or {}
    ticket = ctx.get("Ticket")
    inv_org_id = ctx.get("InvOrgId")
    if not ticket or inv_org_id is None:
        raise RuntimeError("Login response missing Ticket or InvOrgId")
    return ticket, inv_org_id


async def get_ticket() -> tuple[str, int]:
    """返回缓存中的 (Ticket, InvOrgId)；不存在或已过期则用 JWT 重新登录换取。"""
    now = time.time()
    if _ticket_cache["ticket"] and now < _ticket_cache["expires_at"]:
        return _ticket_cache["ticket"], _ticket_cache["inv_org_id"]
    async with _ticket_lock:
        now = time.time()
        if _ticket_cache["ticket"] and now < _ticket_cache["expires_at"]:
            return _ticket_cache["ticket"], _ticket_cache["inv_org_id"]
        ticket, inv_org_id = await _login_for_ticket()
        _ticket_cache["ticket"] = ticket
        _ticket_cache["inv_org_id"] = inv_org_id
        _ticket_cache["expires_at"] = now + _JWT_TTL_MINUTES * 60 - _AUTH_REFRESH_BUFFER_SECONDS
        return ticket, inv_org_id
