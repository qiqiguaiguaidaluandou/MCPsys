# V1-A · 访问控制 & 限流 — 设计文档

- **状态**：已批准，待落实施计划
- **范围**：MCPsys v1 的第一段（共 3 段），仅覆盖 service 级白名单授权和 per-key/per-service 限流
- **依赖**：MVP 已部署（2026-05-06），网关、控制台、Web 控制面已可用
- **上一份**：`2026-04-30-mcp-management-system-design.md`（系统总体设计）

## 1. 背景与目标

MVP 上线后，gateway 鉴权只到「key 是否有效」一层 —— 任何 active key 都可以调任意 active service。
随着多个 application 接入共享部署，这个粒度无法满足：

- 隔离：A 团队的 key 不应能调到 B 团队的 service。
- 防护：key 泄露或 agent 死循环时需要熔断。
- 运营观测：被拒事件需要可见，否则没法定位"为什么不通"。

V1-A 解决前两条，并把"被拒"做成 call_logs 一等公民，为 V1-B 的审计/观测做铺垫。
V1-A **不做**：tool 级权限、per-application 限流、SSO、健康检查、熔断（见 §11）。

## 2. 交付拆分

按"一块能力一套 PR、底层 → API → UI 一次到位"的节奏：

- **PR1 · service_permissions（白名单）**
  - schema：`service_permissions` 新表 + alembic
  - control-plane：`/api/v1/services/{slug}/permissions` CRUD、`/api/v1/applications/{id}/permissions` 反查
  - gateway：鉴权链插入 permission 检查（`PolicyCache`，30s TTL）
  - web：service 详情页加「授权应用」面板
  - smoke：扩展授权 grant 步骤；新增"未授权 → 403"路径

- **PR2 · ratelimit + 拒绝可观测**
  - schema：`api_keys.rate_limit_qps`、`mcp_services.rate_limit_qps`；`CallStatus` 加 `denied`、`throttled`
  - gateway：`TokenBucket`（redis Lua）+ 鉴权链插入双桶检查；写拒绝行进 call_logs
  - control-plane：services / api-keys 的 POST/PATCH 接受 `rate_limit_qps`
  - web：service 与 api-key 表单加 QPS 字段、call-logs 列表 status 筛选加 denied/throttled
  - smoke：429 路径

每个 PR 自身可演示、可回滚。PR1 不依赖 PR2，PR2 假设 PR1 已经合入（denied 是 permission 的产物）。

## 3. 数据模型

### 3.1 新表 `service_permissions`

```python
class ServicePermission(Base):
    __tablename__ = "service_permissions"
    __table_args__ = (
        UniqueConstraint("application_id", "service_id"),
        Index("ix_service_permissions_service", "service_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("mcp_services.id", ondelete="CASCADE"), nullable=False
    )
    granted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    note: Mapped[str | None] = mapped_column(Text)
```

语义：

- 行存在 = 允许；不存在 = 默认拒绝。**不存 deny 行**。
- `(application_id, service_id)` UNIQUE → grant 幂等。
- `ondelete="CASCADE"`：app 或 service 硬删时连带清掉。当前都是软删，cascade 是为后续硬删留的安全网。
- `granted_by` 允许 NULL：seed / bootstrap 脚本可写不属于任何 user 的授权。
- 不加 `expires_at`：spec 没要求过期授权，YAGNI。

### 3.2 既有表加列

```python
# packages/mcpsys_shared/src/mcpsys_shared/models.py

class ApiKey(...):
    rate_limit_qps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NULL = 不限；0 = 全拒（"停用但不撤销"）；正整数 = QPS 上限

class McpService(...):
    rate_limit_qps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 同上语义
```

### 3.3 enum 扩展 `CallStatus`

```python
class CallStatus(str, enum.Enum):
    success = "success"
    error = "error"
    timeout = "timeout"
    denied = "denied"        # 新：permission 拒
    throttled = "throttled"  # 新：ratelimit 拒
```

postgres 侧 `ALTER TYPE callstatus ADD VALUE 'denied'`、`'throttled'`，alembic 用 `op.execute()`，无 DDL 锁风险。

### 3.4 不动的表

- `api_keys.scopes` JSONB：留作后续 tool 级权限的扩展点，V1-A 不读不写。
- `audit_events`：V1-A 不写，全部拒绝事件统一进 call_logs。audit_events 在 V1-B 处理。

## 4. API

### 4.1 control-plane 新增 endpoints

```
GET    /api/v1/services/{slug}/permissions
POST   /api/v1/services/{slug}/permissions      body: {"application_id": int, "note"?: str}
DELETE /api/v1/services/{slug}/permissions/{application_id}

GET    /api/v1/applications/{id}/permissions    # 反查：app 能调哪些 service
```

约束：

- POST 重复 grant 返回 200 + 既有行（幂等），**不**抛 409。
- DELETE 不存在的 grant 返回 204（幂等）。
- 角色控制沿用 `require_role`：admin / operator 可写；admin / operator / viewer 可读。

### 4.2 既有 endpoint 字段扩展

```
POST  /api/v1/services            + rate_limit_qps?
PATCH /api/v1/services/{slug}     + rate_limit_qps?
POST  /api/v1/api-keys            + rate_limit_qps?
PATCH /api/v1/api-keys/{id}       + rate_limit_qps?
```

PATCH 传 `null` 显式置 NULL（恢复"不限"）；不传则不动；传 `0` 接受（即停用语义）。Pydantic schema 用 `int | None = Field(default=UNSET)` 实现这个三态。

### 4.3 错误响应

| 阶段 | HTTP | body | 额外 header |
|---|---|---|---|
| 缺/坏 token | 401 | `{"detail":"missing bearer token"}` / `"invalid api key"` | — |
| service 不存在 / disabled | 404 | `{"detail":"service not found"}` | — |
| 无授权 | **403** | `{"detail":"application not authorized for this service"}` | — |
| key 超限 | **429** | `{"detail":"key rate limit exceeded"}` | `Retry-After: <s>` |
| service 超限 | **429** | `{"detail":"service rate limit exceeded"}` | `Retry-After: <s>` |
| 上游 5xx / timeout | 既有 | 既有 | — |

错误体一律保持 FastAPI 默认 `{"detail": ...}` 形状，跟现有 401/404 一致。
两种 429 用不同文案，便于客户端定位是 key 还是 service 触限。

## 5. 数据流（gateway 鉴权链）

```
auth (key有效?) → permission (app→service 白名单?) → ratelimit (双桶通过?) → forward
   401              403                                429                  上游 status
```

每一步失败立即结束、写 call_logs、不消耗下一步资源。

```python
# services/gateway/src/gateway/routers/mcp.py 伪代码
async def mcp_endpoint(slug, request, body):
    # 1. auth — 既有
    key = await auth.resolve_key(authorization_header)
    if not key:
        return 401

    # 2. resolve service — 既有
    svc = await resolver.get_service(slug)
    if not svc or svc.status != active:
        return 404 / 503

    # 3. permission（V1-A 新增）
    if not await policy_cache.is_allowed(
        app_id=key.application_id, service_id=svc.id
    ):
        await write_call_log(status=denied, http_status=403, duration_ms=0, ...)
        return 403, {"detail": "application not authorized for this service"}

    # 4. ratelimit（V1-A 新增；两个桶都通过才放行）
    rl_key = await ratelimit.check(f"rl:k:{key.id}", qps=key.rate_limit_qps)
    if not rl_key.allowed:
        await write_call_log(status=throttled, http_status=429, ...)
        return 429, headers={"Retry-After": str(rl_key.retry_after_s)}, \
            body={"detail": "key rate limit exceeded"}

    rl_svc = await ratelimit.check(f"rl:s:{svc.id}", qps=svc.rate_limit_qps)
    if not rl_svc.allowed:
        # 注意：key 桶已扣 1 token，此处不回滚（见下）
        await write_call_log(status=throttled, http_status=429, ...)
        return 429, headers={"Retry-After": str(rl_svc.retry_after_s)}, \
            body={"detail": "service rate limit exceeded"}

    # 5. forward — 既有
    ...
```

边角设计决定：

- **service 桶拒绝时不回滚 key 桶。** 回滚意味着 ratelimit.check 必须支持 release，redis Lua 复杂度翻倍。代价仅是极端情况下 key 桶被多扣 1 token，可忽略。
- **NULL qps = 不创建桶、跳过 check。** 不写"无限大"哨兵值。

## 6. PolicyCache（permission 缓存）

```python
# services/gateway/src/gateway/policy.py

# key = service_id, value = (frozenset[application_id], cached_at)
_cache: dict[int, tuple[frozenset[int], float]] = {}
TTL_SECONDS = 30
```

- `is_allowed(app_id, service_id)`：
  - cache 未命中或过期 → `SELECT application_id FROM service_permissions WHERE service_id=$1` 重建该 service 的 allow set。
  - 命中 → `app_id in allow_set`。
- 缓存粒度按 service 而非 (app, service) pair：单次 SELECT 拿全部，control-plane grant/revoke 一次只 invalidate 一个 service 即可（V1-A 不做主动 invalidate，TTL 自然过期）。
- 不上 LRU：service 数量级是百，纯 dict 够用。
- 单 process 内 lock 防雪崩：同一 service 同时多个请求 cache miss 时，只让一个去查 DB（`asyncio.Lock` 按 service_id sharding 可选）。V1-A 简化：不加锁，被多查几次可接受。

## 7. TokenBucket（redis Lua）

```lua
-- KEYS[1]=bucket key   ARGV[1]=now_ms  ARGV[2]=qps  ARGV[3]=burst
local data = redis.call('HMGET', KEYS[1], 'tokens', 'updated_ms')
local tokens = tonumber(data[1]) or tonumber(ARGV[3])
local updated = tonumber(data[2]) or tonumber(ARGV[1])
local elapsed = math.max(0, tonumber(ARGV[1]) - updated)
tokens = math.min(
    tonumber(ARGV[3]),
    tokens + elapsed * tonumber(ARGV[2]) / 1000
)
local allowed = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated_ms', ARGV[1])
redis.call('PEXPIRE', KEYS[1], 60000)  -- 1min idle 后丢弃，省内存
return {allowed, tokens}
```

约定：

- `burst = 2 × qps`，硬编码在 gateway 调用侧，不进 schema。
- 返回 `(allowed, remaining)`；`retry_after_s = ceil((1 - remaining) / qps)` 在 Python 端算。
- key 命名：`rl:k:{api_key_id}`（key 桶）、`rl:s:{service_id}`（service 桶）。
- TTL 60s：长时间不调用的 bucket 自动清掉，redis 内存不爆。
- 选 redis Lua 而非进程内桶：多 gateway 实例可共享桶（V1 仍单实例，但 V2 横扩时不用重写）。
- **`rate_limit_qps == 0` 走特殊分支**：不调 Lua、直接 `allowed=False`、不返回 `Retry-After`（无意义 —— 永远不会有 token），错误体仍是 throttled 文案。避免 Python 侧 `(1 - remaining) / qps` 除零。

## 8. 失败模式

| 失败 | 行为 | 理由 |
|---|---|---|
| Redis 不可用（Lua 异常） | **fail-open**：放行 + log warning | 限流挂了不能拖死整个网关；安全靠 permission |
| Postgres 不可用（cache 重建失败） | **fail-closed**：返 503 | permission 是安全边界，宁拒不放 |
| Cache 过期 + DB 短暂慢 | 当前请求等 DB（无 stale-while-revalidate） | YAGNI |
| Service 软删后 cache 还有 30s 命中 | §5 第 2 步 status 检查会拦掉 | cache 命中也无意义 |

## 9. 测试

### 9.1 unit

- `gateway/policy.py`：cache hit / miss / TTL 过期重读 / 空 allow set / DB 异常 fail-closed
- `gateway/ratelimit.py`：用 fakeredis 跑 lua，覆盖 burst 用尽、refill、NULL qps 跳桶、redis 异常 fail-open

### 9.2 integration（services/gateway/tests）

- 鉴权链次序：401 / 403 / 429 / 200 各一条，确认拒绝阶段都不打上游 mock
- 拒绝路径都写了 call_logs（status=denied / throttled，duration_ms 接近 0）
- service 软删后 grant 过的 app 拿 404（不是 403）

### 9.3 control-plane（services/control_plane/tests）

- POST permission 重复 grant 返回 200 + 同一行（幂等）
- DELETE 不存在 grant 返回 204
- DELETE 后 30s 内 cache 仍命中是 expected（写一条防回归测试）
- viewer 角色不能写 permission / 不能改 rate_limit_qps

### 9.4 web smoke（scripts/smoke.sh、web-smoke.sh）

- 现 smoke.sh 必须扩展：注册服务 → 创建 app+key → **新增：grant permission** → 验证调用通；同时跑一条「未 grant 直接调」预期 403 路径
- 限流路径：把 service rate_limit_qps 设为 1，连发 3 次取得 1×200 + 2×429（带 Retry-After header）

## 10. 迁移与上线

部署前必须的步骤：

1. `alembic upgrade head` —— 建 service_permissions 表 + 加 rate_limit_qps 列 + 扩 enum。
2. **bootstrap 脚本（必跑）**：把当前所有 (active key 的 application × active service) 笛卡尔积写进 service_permissions。这是从「全开」无损切到「白名单」的唯一安全路径。
   - 提供 `scripts/bootstrap_permissions.py`，admin 操作，幂等。
3. 灰度方式：bootstrap 后即可发新版 gateway，**不**搞 feature flag 灰度。理由：bootstrap 后等价于"全开"，发布无行为差异。
4. 上线后操作员逐步收敛权限（删多余 grant 行）。
5. 已在 prod 跑的 service（如 crmserver）必须确认 bootstrap 后 smoke.sh 仍通，再发新版 gateway。

回滚：rate_limit_qps 列设回 NULL，gateway 回退旧版本，service_permissions 表保留（无害）。

## 11. 非范围（V1-A 显式不做）

- **tool 级权限**（spec §1.3 已声明 v1 只到服务级）
- **per-application 限流**（key 级 + service 级已覆盖 95% 场景）
- **审计事件 audit_events 写入**（留 V1-B）
- **熔断 / 健康检查**（V2）
- **rate_limit 配置热下发 < 30s**（V1 接受 30s TTL 延迟，V1-B 之后再考虑 redis pub/sub）
- **stale-while-revalidate cache**（YAGNI）
- **gateway 横向扩缩**（compose 单实例；多实例需要 nginx upstream resolver 调整，spec 已记录，V2 处理）

## 12. 后续工作（V1-A 之后）

- V1-B：audit_events 全量写入 + 查询 API + UI 页 + call-log 详情页 + Grafana P50/P95/P99
- V1-C：service_configs（Fernet 加密 + 热下发）+ mcp_service_versions（CRUD + 当前版本切换）
