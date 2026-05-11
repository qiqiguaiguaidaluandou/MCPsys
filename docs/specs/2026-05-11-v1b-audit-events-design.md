# V1-B · 管理审计（audit_events）— 设计文档

- **状态**：已批准，待落实施计划
- **范围**：MCPsys v1 的 V1-B 段中的「主题 A：审计事件全量化」，独占一段 spec/plan；
  V1-B 主题 B（call_logs 详情页 + body）和主题 C（Grafana 监控深化）走 `docs/changes/` 小需求批次，不在本 spec 内
- **依赖**：V1-A + V1-A.1 已入 main（2026-05-09 末），`audit_events` 表 schema 自 MVP `0001_initial.py` 起已存在
- **上一份**：`2026-05-08-v1a-access-control-and-ratelimit-design.md`（V1-A 设计）
- **总图**：`2026-04-30-mcp-management-system-design.md` §6 12–14 周路线图中的 v1 段 (line 336–345)

---

## 1. 背景与目标

MVP 上线后，control-plane 的所有写操作（创建 / 修改 / 删除 service、application、api_key、user、permission、限流字段）都是**悄无声息**的——表里只能看到「当前是什么」，看不到「之前是什么、谁改的、何时改的」。`mcp_services.updated_at` 只是一个时间戳，无人无变更内容。当前已暴露的实际问题：

- 故障回溯无依据：服务的 endpoint URL 被错改、找不到改人改时
- 权限滥用无审计：哪个 application 何时被授权访问敏感服务，没有线索
- API Key 吊销无 actor：`api_keys.revoked_at` 只记时间不记人
- 角色变更无历史：`users.role` 只有当前值，谁把 viewer 升 admin 查不到

`audit_events` 表 schema 自 MVP `0001_initial.py` 就建好，但**全仓零写入**——`grep AuditEvent services/ packages/` 仅命中 ORM 模型定义。`docs/deployment.md §12` 也标注「审计日志（管理动作 / 配置变更）尚未写入 audit_events 表 — v1 范围」。

V1-B 审计就是补齐这一段：让每个 control-plane HTTP 写操作落一行 `audit_events`，提供查询 API + Web UI，权限收敛到 admin。

V1-B 审计**不做**：bootstrap_permissions.py / alembic 等部署期写入的审计；登录失败审计；行级权限（admin 之外的精细授权）；WORM 级别防改防删（见 §11）。

## 2. 数据模型

表已建（`packages/mcpsys_shared/src/mcpsys_shared/models.py:211`），本 spec 不动 schema 字段。复用以下字段：

```python
class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: BigInteger primary_key
    ts: timestamptz server_default=now() not null
    actor_user_id: int | None  → FK users.id (nullable, 用户被删后保留审计行)
    action: String(64) not null         e.g. "service.update"
    target_type: String(64) not null    e.g. "mcp_service"
    target_id: String(64) | None        always str(numeric_id)
    before: jsonb | None
    after: jsonb | None
    ip: String(64) | None
```

**新增索引**（迁移 `0004_v1b_audit_indexes`）：

| 索引 | 列 | 服务的查询 |
|---|---|---|
| `ix_audit_events_ts` | `(ts DESC)` | 默认时间线 + 时间窗 |
| `ix_audit_events_actor_ts` | `(actor_user_id, ts DESC)` | 按 actor 过滤 |
| `ix_audit_events_target_ts` | `(target_type, target_id, ts DESC)` | 单实体历史（最高频排障） |
| `ix_audit_events_action_ts` | `(action, ts DESC)` | 按 action 类型过滤 |

四条索引、单表小数据量（估每天最多几千条），写开销可忽略。

## 3. 写入路径

### 3.1 新模块 `services/control_plane/src/control_plane/audit.py`

承载三件事：

**(a) Action 常量集合**

```python
class Action:
    USER_CREATE          = "user.create"
    USER_DELETE          = "user.delete"
    USER_PASSWORD_CHANGE = "user.password_change"
    APPLICATION_CREATE   = "application.create"
    API_KEY_ISSUE        = "api_key.issue"
    API_KEY_REVOKE       = "api_key.revoke"
    API_KEY_UPDATE       = "api_key.update"
    API_KEY_DELETE       = "api_key.delete"      # permanent hard delete
    SERVICE_CREATE       = "service.create"
    SERVICE_UPDATE       = "service.update"
    SERVICE_DELETE       = "service.delete"
    SERVICE_PERMISSION_GRANT  = "service_permission.grant"
    SERVICE_PERMISSION_REVOKE = "service_permission.revoke"
```

13 条 action，格式 `target_type.verb`，与 AWS CloudTrail / GCP Audit 同风格，便于 `LIKE 'service.%'` 过滤。常量类（非 Enum）—— 入库就是字符串，Enum 额外语义无价值。Handler 引用 `Action.SERVICE_CREATE` 避免 typo。

> **校准记录**（2026-05-11）：spec 草稿原列 `application.update / application.delete` 但 `applications.py` 实际未实现 PATCH / DELETE 端点；同时 `api_keys.py` 实际多两个写端点（`PATCH` 和 permanent `DELETE`）spec 未覆盖。本次以现状为准重排：去掉 application 的 update/delete，加上 api_key 的 update/delete，总数仍为 13。application 的 PATCH/DELETE handler 留待后续单独小需求新增（届时同步加 `application.update/delete` action）。

**(b) PII 黑名单 + `model_to_dict`**

```python
_SENSITIVE_COLUMNS: frozenset[str] = frozenset({
    "password_hash",     # users.password_hash
    "key_hash",          # api_keys.key_hash
    "value_encrypted",   # (未来) service_configs.value_encrypted
})

def model_to_dict(obj: Base) -> dict[str, Any]:
    """ORM 对象 → jsonb-safe dict。
    跳过 _SENSITIVE_COLUMNS；datetime → ISO、Enum → value、UUID → str。
    只遍历 __mapper__.columns，不动 relationships。
    """
```

将来加 `users.api_token`、`service_configs.value_encrypted` 等新列时，**guard 测试**（§5.1）会强制要求加入黑名单，迟漂移在 CI 阶段被钉死。

**(c) 写入 helper `audit_log`**

```python
async def audit_log(
    db: AsyncSession,
    *,
    action: str,
    target_type: str,
    target_id: str | None,
    before: dict | None,
    after: dict | None,
    actor: User | None,
    request: Request | None,
) -> None:
    ip = None
    if request is not None:
        xff = request.headers.get("X-Forwarded-For")
        ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else None)
    db.add(AuditEvent(
        actor_user_id=actor.id if actor else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before=before,
        after=after,
        ip=ip,
    ))
    # 不 commit、不 flush；交由 `get_db` 的统一 commit 钉死同事务原子
```

**不**在内部做 try/except。同事务原子：主写失败 → audit 回滚；audit 写失败（极不可能：无 FK / unique / NOT NULL 全有默认值）→ 主写也回滚（可接受，能在 control-plane 日志立即看到 traceback）。

### 3.2 Handler 接入模式

每个 control-plane 写 handler 在主操作前后抓 snapshot，调一次 `audit_log`。以 `service.update` 为模板：

```python
@router.patch("/{slug}")
async def update_service(
    slug: str, payload: ServiceUpdate,
    current_user: User = Depends(require_role("admin", "operator")),
    db: AsyncSession = Depends(get_db),
    request: Request,
):
    service = await _get_service_by_slug(db, slug)
    before = model_to_dict(service)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(service, k, v)
    await db.flush()  # 让 server_default / onupdate 生效
    after = model_to_dict(service)
    await audit_log(db, action=Action.SERVICE_UPDATE,
                    target_type="mcp_service", target_id=str(service.id),
                    before=before, after=after,
                    actor=current_user, request=request)
    return ServiceOut.model_validate(service)
```

**Create 边界**：先 `db.flush()` 拿主键，`before=None, after=model_to_dict(obj)`。
**Delete 边界**：snapshot 必须在 `await db.delete(obj)` 之前抓，`before=model_to_dict(obj), after=None`。

### 3.3 target_id / target_type 约定

| target_type | 取自 | target_id |
|---|---|---|
| `user` | `users.__tablename__` | `str(user.id)` |
| `application` | `applications.__tablename__` 单数化 | `str(app.id)` |
| `api_key` | `api_keys.__tablename__` 单数化 | `str(key.id)` |
| `mcp_service` | `mcp_services.__tablename__` 单数化 | `str(service.id)` |
| `service_permission` | 同上 | `str(perm.id)` |

数字 PK 而非 slug：service 即使将来 PATCH 改了 slug，审计历史 target_id 仍稳定。代价是排障时 id 不直观——前端 UI 在 after / before 里始终包含 `name` / `slug` / `username` 等显示字段（model_to_dict 全字段快照天然带），不需额外 lookup。

### 3.4 不在审计范围

- **bootstrap_permissions.py、alembic migration、任何不经 HTTP handler 的写**：部署期一次性变更，没有 actor / IP 上下文，强行造 system user 是 noise。
- **gateway 写 `call_logs` 与 `api_keys.last_used_at`**：数据面副作用，与管理动作正交。
- **`auth.login_failed`**：登录失败合规审计若将来需要，单独建 `auth_log` 表，不挤 audit_events。

## 4. 查询 API

### 4.1 端点

`GET /api/v1/audit-events`，`dependencies=[Depends(require_role("admin"))]`。

### 4.2 Schema

```python
class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ts: datetime
    actor_user_id: int | None
    actor_username: str | None     # LEFT JOIN users，已删用户保留 NULL
    action: str
    target_type: str
    target_id: str | None
    before: dict | None
    after: dict | None
    ip: str | None

class AuditEventList(BaseModel):
    items: list[AuditEventOut]
    total: int
```

### 4.3 过滤参数

全部为 Query 参数，None 即不过滤；与 services/applications 等现有列表分页约定一致。

| 参数 | 类型 | 语义 |
|---|---|---|
| `actor_user_id` | `int \| None` | 谁操作的 |
| `action` | `str \| None` | 精确匹配（前端用下拉选 13 条之一） |
| `target_type` | `str \| None` | 表维度（user / application / api_key / mcp_service / service_permission） |
| `target_id` | `str \| None` | 与 target_type 配合定位单实体历史 |
| `from_ts` | `datetime \| None` | 时间窗起 |
| `to_ts` | `datetime \| None` | 时间窗止 |
| `page` | `int = 1` | 起始 1 |
| `page_size` | `int = 50, le=200` | 上限 200 |

排序：固定 `ts DESC`。

### 4.4 实现位置

新文件 `services/control_plane/src/control_plane/routers/audit_events.py`；
`main.py` `app.include_router(audit_events_router.router)`。

## 5. 前端

### 5.1 导航

`services/web/src/components/nav/SideBar.vue:43-47` 的 `system-group`（admin only，目前只含「用户」）追加一条「审计」；移除原 `upcoming-group:53` 的 disabled 占位。labelKey `nav.audit` 已存在，icon `clipboard-list` 已存在，无需新增。

### 5.2 路由

`services/web/src/router/index.ts` 新增：

```ts
{
  path: '/audit-events',
  name: 'AuditEventList',
  component: () => import('@/views/audit/AuditEventListPage.vue'),
  meta: { requiresAuth: true, roles: ['admin'], layout: 'app', title: 'nav.audit' },
}
```

### 5.3 API 层

新文件 `services/web/src/api/audit.ts`：

```ts
import { client } from './client';
import type { PaginatedList } from './types';

export interface AuditEvent {
  id: number;
  ts: string;
  actor_user_id: number | null;
  actor_username: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string | null;
}

export interface AuditEventFilter {
  actor_user_id?: number;
  action?: string;
  target_type?: string;
  target_id?: string;
  from_ts?: string;
  to_ts?: string;
  page?: number;
  page_size?: number;
}

export function listAuditEvents(filter?: AuditEventFilter): Promise<PaginatedList<AuditEvent>> {
  return client.get('/api/v1/audit-events', { params: filter }).then((r) => r.data);
}
```

### 5.4 列表页 `services/web/src/views/audit/AuditEventListPage.vue`

结构（参考 `CallLogListPage.vue` 风格）：

- `PageHeader title="审计" description="管理动作变更历史"`
- 筛选条横排：
  - **操作类型** 下拉（13 条 action，按 target_type 分组）
  - **目标类型** 下拉（5 个 target_type）
  - **目标 ID** 输入框（启用条件：选了 target_type）
  - **操作者** 下拉（拉全量 users 列表，与现有 admin 一致）
  - **时间范围** `el-date-picker type="datetimerange"`
  - 「重置」「查询」按钮
- 中部 `DataTable`：
  - 列：时间（`<RelativeTime>`）、操作者（actor_username 或 `已删用户#${id}`）、动作（el-tag）、目标（`target_type / target_id`）、IP
  - 行内展开（`expand` 列）：
    - **create** 单栏右 → after JSON
    - **delete** 单栏左 → before JSON
    - **update** 双栏 → before / after
    - 渲染：`<pre class="json-block">` + `JSON.stringify(obj, null, 2)`，无 diff 高亮
- 分页：与 CallLogListPage 同款

样式（scoped CSS）：
```css
.json-block {
  background: var(--color-gray-50);
  padding: var(--space-3);
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 12px;
  white-space: pre;
  overflow-x: auto;
  max-height: 360px;
  overflow-y: auto;
}
```

### 5.5 国际化

`services/web/src/i18n/locales/zh-CN.ts` 加约 15 条键：列头、筛选器 label、13 条 action 的显示名映射（`audit.action.service.create` → "创建服务"）。

## 6. 测试策略

预期 30 例。

### 6.1 后端（`services/control_plane/tests/test_audit.py`）

| # | 测试 | 验证 |
|---|---|---|
| 1 | `test_pii_blacklist_covers_all_sensitive_columns` | 遍历 `Base.metadata.sorted_tables`，列名命中 `(_hash\|_secret\|_encrypted\|_token)$` 正则但不在黑名单 → fail。CI 钉死「加新敏感列没人想起改黑名单」 |
| 2 | `test_model_to_dict_basic` | 普通字段全字段输出（datetime ISO / Enum value / UUID str） |
| 3 | `test_model_to_dict_skips_sensitive` | password_hash / key_hash 不在输出中 |
| 4 | `test_model_to_dict_skips_relationships` | 不动 relationships |
| 5 | `test_audit_log_writes_row` | 调一次 helper → audit_events 多一行、字段对齐 |
| 6 | `test_audit_log_no_actor` | actor=None 时 actor_user_id=None |
| 7 | `test_audit_log_no_request` | request=None 时 ip=None |
| 8 | `test_audit_log_x_forwarded_for_first_hop` | XFF 多跳取第一个 |

### 6.2 端到端每 action（同上文件或拆 test_audit_actions.py）

13 例，每例：调对应 control-plane API → 断言主写生效 + `audit_events` 多一行 + action/target_type/target_id 正确 + before/after 内容符合预期。

### 6.3 查询 API（`tests/test_audit_query.py`）

| # | 用例 | 期望 |
|---|---|---|
| 1 | 未认证 | 401 |
| 2 | viewer 调 | 403 |
| 3 | operator 调 | 403 |
| 4 | admin 无 filter | 200，items 按 ts DESC |
| 5 | actor_user_id 过滤 | 仅返回该 actor |
| 6 | action 过滤 | 仅返回该 action |
| 7 | target_type + target_id 组合 | 单实体历史 |
| 8 | from_ts / to_ts 边界 | 时间窗内 |
| 9 | page_size=2 跨页 | page=1 / page=2 各 2 条；total 全量 |
| 10 | page_size=500 | 422（Pydantic `le=200` 拦截） |

### 6.4 冒烟脚本

`scripts/smoke.sh` 末尾加一行：用 admin token 调 `GET /api/v1/audit-events?limit=5`，断言 items 非空且包含脚本前面动作产生的 `service.create` / `application.create`。

### 6.5 前端

不加单元测试（与现有惯例一致，列表页之前没有单测，UI 流程 ROI 低）。

## 7. 性能预算

- 写延迟：每写操作 +1 条 INSERT（无 FK / unique / NOT NULL 有默认）+ Python 端 jsonb 序列化 < 1ms，端到端 +1–3ms 不可见
- 写体积：单条 audit_events 行字典化 ≤ 1KB（最重的 service 表含 tags 数组也就 1–2KB），峰值 2000 条/天 = 2MB/天，永久保留十年也才 7GB 量级
- 查询延迟：索引覆盖所有过滤维度，分页 50 条 < 10ms

## 8. 部署 / 迁移

- 新增 alembic migration `0004_v1b_audit_indexes`：四条索引创建，downgrade 删除
- 部署：`docker compose build control-plane web && docker compose up -d control-plane web && docker compose restart nginx`
- migration 由 control-plane 容器 entrypoint 自动 `alembic upgrade head`，无人工动作
- 与 V1-A 不同：本次**不**需要 bootstrap 脚本，因为审计是「增量行为」（生效后产生的新写操作开始落 audit 行），无需对存量数据回填——存量动作历史无源可查这条已在 §11 标注

## 9. 拆分与 PR 节奏

按「底层 → API → UI 一次到位」一段交付即可。本次审计 scope 较紧凑（约 30 例测试 + 1 backend helper + 1 router + 1 alembic + 1 frontend page），建议**单 PR**：

- `feat/v1b-audit-events`
  - alembic 0004
  - `control_plane/audit.py`（Action + model_to_dict + audit_log）
  - 13 handler 接入 audit_log
  - `routers/audit_events.py`
  - frontend：api/audit.ts + AuditEventListPage.vue + 路由 + 导航迁移 + i18n
  - 测试 30 例
  - smoke 加一行
  - changelog / docs/changes 追条目

不必拆 PR1/PR2，handler 接入和 helper 是耦合演化。

## 10. 风险

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| 漏接某个 handler，事件遗漏 | 中 | 中（漏的那类动作无审计） | §6.2 13 例端到端，CI 拦截 |
| 加新敏感列没加进黑名单 | 中 | 高（PII 泄露到 jsonb） | §6.1 guard 测试 + SENSITIVE_PATTERN 正则 |
| 加新敏感列但列名不符合正则模式 | 低 | 高 | 代码评审 checklist 项；文档明示规则 |
| 同事务原子导致 audit 失败阻断主写 | 极低 | 中 | audit row 无 FK / unique，失败概率约 0；万一发生让运维看 traceback 修 |
| 查询接口被前端误用拉全量 | 低 | 低 | `page_size ≤ 200` 服务端 clamp；前端默认 50 |
| 单条 audit 行过大（jsonb > 100KB） | 极低 | 低 | model_to_dict 不递归关系；service_configs.value_encrypted 已在 PII 黑名单内剥离 |

## 11. 未覆盖（明确不做，避免日后被开 ticket）

1. **bootstrap_permissions.py / alembic / 任何不经 HTTP 的写**不进审计。审计 scope = control-plane HTTP handler 写操作
2. **gateway 写 call_logs、api_keys.last_used_at** 不进审计（数据面副作用）
3. **`auth.login_failed`** 不记，未来合规要求另开 `auth_log` 表
4. **审计行不可改不可删**靠约定（无 PUT/DELETE 端点），不加 DB 触发器。WORM 级别（pg_audit / 只读对象存储）是 V2 议题
5. **行级权限**：仅 admin 可查询，service owner 看自己服务审计是后续增量
6. **存量动作历史**无法回填，审计是「从 V1-B 部署开始的增量记录」
7. **审计统计 / 聚合面板**（每天动作量、按 actor 排行）不做，Grafana 主题 C 时再决定要不要做
8. **跨 service 关联**（一次 grant 影响多个 application）：每个 grant 一条独立 audit，靠 ts 接近排序识别，不做 batch_id

---

## 附录 A · 13 条 action 与 handler 映射

| Action | HTTP | Handler | target_type | before / after |
|---|---|---|---|---|
| `user.create` | POST `/api/v1/users` | `routers/users.py:create_user` | `user` | None / 全字段 |
| `user.delete` | DELETE `/api/v1/users/{id}` | `routers/users.py:delete_user` | `user` | 全字段 / None |
| `user.password_change` | PUT `/api/v1/users/{id}` | `routers/users.py:update_user` | `user` | password_hash 黑名单内被剥离；before/after 仅含其他字段（语义上 changed=password 由 action 名表达） |
| `application.create` | POST `/api/v1/applications` | `routers/applications.py:create_application` | `application` | None / 全字段 |
| `api_key.issue` | POST `/api/v1/api-keys` | `routers/api_keys.py:create_api_key` | `api_key` | None / 全（key_hash 黑名单剥离） |
| `api_key.revoke` | DELETE `/api/v1/api-keys/{id}` (软删) | `routers/api_keys.py:revoke_api_key` | `api_key` | 全 / 全（revoked_at 差异） |
| `api_key.update` | PATCH `/api/v1/api-keys/{id}` | `routers/api_keys.py:update_api_key` | `api_key` | 全 / 全 |
| `api_key.delete` | DELETE `/api/v1/api-keys/{id}/permanent` (硬删) | `routers/api_keys.py:delete_api_key_permanent` | `api_key` | 全 / None |
| `service.create` | POST `/api/v1/services` | `routers/services.py` | `mcp_service` | None / 全 |
| `service.update` | PATCH `/api/v1/services/{slug}` | 同上 | `mcp_service` | 全 / 全 |
| `service.delete` | DELETE / 软删 `/api/v1/services/{slug}` | 同上 | `mcp_service` | 全 / 全 |
| `service_permission.grant` | POST `/api/v1/services/{slug}/permissions` | `routers/permissions.py` | `service_permission` | None / 全 |
| `service_permission.revoke` | DELETE `/api/v1/services/{slug}/permissions/{id}` | 同上 | `service_permission` | 全 / None |
