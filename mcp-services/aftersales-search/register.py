"""容器自注册：启动时读 service.yaml，调 control-plane 现有 API 把本服务 upsert 到后台。

不改 control-plane —— 用的是已存在的 /api/v1/auth/login + /api/v1/services。
失败只告警、退避重试若干次后放弃，绝不阻塞 MCP 服务启动。
失败时打印 HTTP 状态码 + 返回体，方便直接在 `docker compose logs` 里排查。

环境变量（由 compose.mcp.yaml 注入）：
  MCPSYS_URL              control-plane 内网地址，默认 http://control-plane:8000
  REGISTRAR_USER/PASSWORD 自注册账号（operator 角色）；缺省则跳过自注册
  REGISTER_ATTEMPTS       重试次数，默认 10
  REGISTER_BACKOFF_SECONDS 每次退避秒数，默认 3
"""
import os
import sys
import time

import httpx
import yaml

MCPSYS_URL = os.environ.get("MCPSYS_URL", "http://control-plane:8000").rstrip("/")
USER = os.environ.get("REGISTRAR_USER", "")
PASSWORD = os.environ.get("REGISTRAR_PASSWORD", "")
SERVICE_YAML = os.environ.get("SERVICE_YAML", "/app/service.yaml")
ATTEMPTS = int(os.environ.get("REGISTER_ATTEMPTS", "10"))
BACKOFF = float(os.environ.get("REGISTER_BACKOFF_SECONDS", "3"))

_PATCH_FIELDS = ("display_name", "description", "owner_team", "tags", "endpoint_url", "rate_limit_qps")


def log(msg: str) -> None:
    print(f"[register] {msg}", flush=True)


def load_payload() -> dict:
    with open(SERVICE_YAML) as f:
        m = yaml.safe_load(f)
    slug = m["slug"]
    port = m.get("port", 8000)
    path = m.get("path", "/mcp")
    return {
        "slug": slug,
        "display_name": m.get("display_name", slug),
        "description": m.get("description"),
        "owner_team": m.get("owner_team"),
        "tags": m.get("tags") or [],
        # 内网地址：同 compose 工程下，本服务的网络别名就是 mcp-<slug>
        "endpoint_url": f"http://mcp-{slug}:{port}{path}",
        "rate_limit_qps": m.get("rate_limit_qps"),
    }


def register_once(payload: dict) -> bool:
    slug = payload["slug"]
    with httpx.Client(base_url=MCPSYS_URL, timeout=10) as c:
        r = c.post("/api/v1/auth/login", data={"username": USER, "password": PASSWORD})
        if r.status_code != 200:
            log(f"登录失败 HTTP {r.status_code}: {r.text[:300]}")
            return False
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        g = c.get(f"/api/v1/services/{slug}", headers=headers)
        if g.status_code == 200:
            body = {k: payload[k] for k in _PATCH_FIELDS}
            u = c.patch(f"/api/v1/services/{slug}", json=body, headers=headers)
            if u.status_code == 200:
                log(f"已更新服务 {slug} → {payload['endpoint_url']}")
                return True
            log(f"更新失败 HTTP {u.status_code}: {u.text[:300]}")
            return False
        if g.status_code == 404:
            p = c.post("/api/v1/services", json=payload, headers=headers)
            if p.status_code in (200, 201):
                log(f"已注册服务 {slug} → {payload['endpoint_url']}")
                return True
            log(f"注册失败 HTTP {p.status_code}: {p.text[:300]}")
            return False
        log(f"查询服务失败 HTTP {g.status_code}: {g.text[:300]}")
        return False


def main() -> int:
    if not USER or not PASSWORD:
        log("未配置 REGISTRAR_USER / REGISTRAR_PASSWORD，跳过自注册（服务照常启动）")
        return 0
    try:
        payload = load_payload()
    except Exception as e:  # noqa: BLE001 — 自注册失败绝不阻塞服务
        log(f"读取 service.yaml 失败：{e}（跳过自注册）")
        return 0

    for i in range(1, ATTEMPTS + 1):
        try:
            if register_once(payload):
                return 0
            log(f"第 {i}/{ATTEMPTS} 次自注册未成功")
        except httpx.RequestError as e:
            log(f"第 {i}/{ATTEMPTS} 次连接 control-plane 失败：{e}")
        if i < ATTEMPTS:
            time.sleep(BACKOFF)
    log("自注册多次失败，已放弃；服务仍在运行，control-plane 就绪后重启本容器即可重试")
    return 0


if __name__ == "__main__":
    sys.exit(main())
