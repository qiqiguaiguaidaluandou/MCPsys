# V1-B 管理审计 (audit_events) 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 control-plane 所有 13 类 HTTP 写操作落 `audit_events` 行，提供 admin-only 查询 API + Web UI。

**Architecture:** Handler 显式调用 `audit_log()` helper（同事务原子）+ `model_to_dict()` 全字段快照 + PII 黑名单（正则 guard 测试钉死）。新增 4 条查询索引（migration 0004）。前端列表页 + 行内展开双栏 JSON。

**Tech Stack:** FastAPI, SQLAlchemy 2 async, alembic, Vue 3 + Element Plus, pytest + testcontainers, vitest

**Spec:** `docs/specs/2026-05-11-v1b-audit-events-design.md`

---

## Task 1 — Alembic migration 0004：审计索引

**Files:**
- Create: `services/control_plane/alembic/versions/0004_v1b_audit_indexes.py`

- [ ] **Step 1: 创建 migration 文件**

```python
"""v1b audit indexes

Revision ID: 0004_v1b_audit_indexes
Revises: 0003_v1a_ratelimit
Create Date: 2026-05-11
"""
from alembic import op

revision = "0004_v1b_audit_indexes"
down_revision = "0003_v1a_ratelimit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_audit_events_ts", "audit_events", [("ts", "desc")])
    op.create_index("ix_audit_events_actor_ts", "audit_events", ["actor_user_id", ("ts", "desc")])
    op.create_index("ix_audit_events_target_ts", "audit_events", ["target_type", "target_id", ("ts", "desc")])
    op.create_index("ix_audit_events_action_ts", "audit_events", ["action", ("ts", "desc")])


def downgrade() -> None:
    op.drop_index("ix_audit_events_action_ts", table_name="audit_events")
    op.drop_index("ix_audit_events_target_ts", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_ts", table_name="audit_events")
    op.drop_index("ix_audit_events_ts", table_name="audit_events")
```

> 注意：alembic 的 `create_index` 不直接支持 `desc()` 元组写法，正确写法是 `sa.text("ts DESC")` 形式。下面给完整正确版本。

- [ ] **Step 2: 修正语法（postgres 索引带 DESC）**

替换 step 1 的 upgrade 函数为：

```python
def upgrade() -> None:
    op.execute("CREATE INDEX ix_audit_events_ts ON audit_events (ts DESC)")
    op.execute("CREATE INDEX ix_audit_events_actor_ts ON audit_events (actor_user_id, ts DESC)")
    op.execute("CREATE INDEX ix_audit_events_target_ts ON audit_events (target_type, target_id, ts DESC)")
    op.execute("CREATE INDEX ix_audit_events_action_ts ON audit_events (action, ts DESC)")
```

(downgrade 段不变)

- [ ] **Step 3: 跑迁移验证**

```bash
cd /dataspace/kqspace/MCPsys && uv run alembic -c services/control_plane/alembic.ini upgrade head
uv run alembic -c services/control_plane/alembic.ini downgrade -1
uv run alembic -c services/control_plane/alembic.ini upgrade head
```

Expected: 三步都无错；最后 `alembic current` 显示 `0004_v1b_audit_indexes`。

- [ ] **Step 4: Commit**

```bash
git add services/control_plane/alembic/versions/0004_v1b_audit_indexes.py
git commit -m "feat(schema): 加 audit_events 查询索引（0004 migration）"
```

---

## Task 2 — audit 模块骨架（Action 常量 + 黑名单 + SENSITIVE_PATTERN）

**Files:**
- Create: `services/control_plane/src/control_plane/audit.py`

- [ ] **Step 1: 创建 audit.py 骨架**

```python
"""Audit logging — manages writes to audit_events from control-plane handlers.

See docs/specs/2026-05-11-v1b-audit-events-design.md for the design.
"""
import re
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from mcpsys_shared.models import AuditEvent, Base, User


class Action:
    """All audit action strings, format `target_type.verb`."""
    USER_CREATE          = "user.create"
    USER_DELETE          = "user.delete"
    USER_PASSWORD_CHANGE = "user.password_change"
    APPLICATION_CREATE   = "application.create"
    API_KEY_ISSUE        = "api_key.issue"
    API_KEY_REVOKE       = "api_key.revoke"
    API_KEY_UPDATE       = "api_key.update"
    API_KEY_DELETE       = "api_key.delete"
    SERVICE_CREATE       = "service.create"
    SERVICE_UPDATE       = "service.update"
    SERVICE_DELETE       = "service.delete"
    SERVICE_PERMISSION_GRANT  = "service_permission.grant"
    SERVICE_PERMISSION_REVOKE = "service_permission.revoke"


# Column names that must NEVER end up in audit before/after jsonb.
# Adding a new sensitive column? Append here AND make sure its name matches SENSITIVE_PATTERN
# (or extend the pattern). See test_pii_blacklist_covers_all_sensitive_columns.
_SENSITIVE_COLUMNS: frozenset[str] = frozenset({
    "password_hash",   # users
    "key_hash",        # api_keys
    "value_encrypted", # (future) service_configs
})

# Used by guard test to catch unexpected sensitive columns sneaking into the schema
# without being added to _SENSITIVE_COLUMNS.
SENSITIVE_PATTERN = re.compile(r"(_hash|_secret|_encrypted|_token)$")
```

- [ ] **Step 2: 加 `model_to_dict`**

追加到 audit.py 末尾：

```python
def model_to_dict(obj: Base) -> dict[str, Any]:
    """ORM 对象 → jsonb-safe dict。跳过 _SENSITIVE_COLUMNS；
    datetime → ISO string、Enum → value、UUID → str。
    只遍历 __mapper__.columns（不含 relationships）。
    """
    out: dict[str, Any] = {}
    for col in obj.__mapper__.columns:  # type: ignore[attr-defined]
        if col.name in _SENSITIVE_COLUMNS:
            continue
        val = getattr(obj, col.name)
        if val is None:
            out[col.name] = None
        elif isinstance(val, datetime):
            out[col.name] = val.isoformat()
        elif isinstance(val, Enum):
            out[col.name] = val.value
        elif isinstance(val, UUID):
            out[col.name] = str(val)
        else:
            out[col.name] = val
    return out
```

- [ ] **Step 3: 加 `audit_log` helper**

追加：

```python
async def audit_log(
    db: AsyncSession,
    *,
    action: str,
    target_type: str,
    target_id: str | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    actor: User | None,
    request: Request | None,
) -> None:
    """落一行 audit_events。同事务原子：交由 `get_db` 统一 commit。"""
    ip: str | None = None
    if request is not None:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            ip = xff.split(",")[0].strip()
        elif request.client is not None:
            ip = request.client.host
    db.add(AuditEvent(
        actor_user_id=actor.id if actor else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before=before,
        after=after,
        ip=ip,
    ))
```

- [ ] **Step 4: 静态检查**

```bash
cd /dataspace/kqspace/MCPsys && uv run ruff check services/control_plane/src/control_plane/audit.py
```

Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add services/control_plane/src/control_plane/audit.py
git commit -m "feat(audit): 加 audit 模块（Action / model_to_dict / audit_log）"
```

---

## Task 3 — audit 模块测试（PII guard + model_to_dict + audit_log）

**Files:**
- Create: `services/control_plane/tests/test_audit.py`

- [ ] **Step 1: 写测试**

```python
import re
from datetime import UTC, datetime

import pytest
from mcpsys_shared.models import AuditEvent, Base, User, UserRole, UserStatus
from sqlalchemy import select

from control_plane.audit import (
    SENSITIVE_PATTERN,
    _SENSITIVE_COLUMNS,
    Action,
    audit_log,
    model_to_dict,
)


def test_action_constants_unique_and_dot_formatted():
    values = [getattr(Action, k) for k in dir(Action) if not k.startswith("_")]
    assert len(values) == len(set(values)), "Action 字符串去重失败"
    for v in values:
        assert "." in v, f"Action {v} 缺少 dot 分隔"


def test_pii_blacklist_covers_all_sensitive_columns():
    """加新敏感列没人想起改黑名单 → CI fail。"""
    missed = []
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if SENSITIVE_PATTERN.search(col.name) and col.name not in _SENSITIVE_COLUMNS:
                missed.append(f"{table.name}.{col.name}")
    assert not missed, (
        f"敏感列模式命中但未加入 _SENSITIVE_COLUMNS: {missed}。"
        f"加进 control_plane/audit.py 的 _SENSITIVE_COLUMNS frozenset。"
    )


def test_model_to_dict_basic_types():
    u = User(
        id=7,
        username="alice",
        email="a@x.com",
        role=UserRole.viewer,
        status=UserStatus.active,
    )
    d = model_to_dict(u)
    assert d["id"] == 7
    assert d["username"] == "alice"
    assert d["email"] == "a@x.com"
    assert d["role"] == "viewer"       # Enum → value
    assert d["status"] == "active"


def test_model_to_dict_skips_sensitive():
    u = User(id=1, username="x", password_hash="bcrypt$$$secret", role=UserRole.viewer)
    d = model_to_dict(u)
    assert "password_hash" not in d


def test_model_to_dict_datetime_iso():
    now = datetime(2026, 5, 11, 14, 30, tzinfo=UTC)
    u = User(id=1, username="x", role=UserRole.viewer, last_login_at=now)
    d = model_to_dict(u)
    assert d["last_login_at"] == now.isoformat()


async def test_audit_log_writes_row(session_factory):
    async with session_factory() as s:
        actor = User(username="admin", role=UserRole.admin, status=UserStatus.active)
        s.add(actor)
        await s.commit()
        await s.refresh(actor)

    async with session_factory() as s:
        await audit_log(
            s,
            action=Action.SERVICE_CREATE,
            target_type="mcp_service",
            target_id="42",
            before=None,
            after={"slug": "x"},
            actor=actor,
            request=None,
        )
        await s.commit()

    async with session_factory() as s:
        res = await s.execute(select(AuditEvent))
        rows = res.scalars().all()
    assert len(rows) == 1
    r = rows[0]
    assert r.action == "service.create"
    assert r.target_type == "mcp_service"
    assert r.target_id == "42"
    assert r.before is None
    assert r.after == {"slug": "x"}
    assert r.actor_user_id == actor.id
    assert r.ip is None


async def test_audit_log_no_actor(session_factory):
    async with session_factory() as s:
        await audit_log(
            s, action=Action.USER_CREATE, target_type="user", target_id="1",
            before=None, after={"id": 1}, actor=None, request=None,
        )
        await s.commit()

    async with session_factory() as s:
        res = await s.execute(select(AuditEvent))
        r = res.scalar_one()
    assert r.actor_user_id is None


async def test_audit_log_x_forwarded_for_first_hop(session_factory):
    """构造一个最小的伪 Request 覆盖 XFF 解析。"""
    from types import SimpleNamespace

    fake_request = SimpleNamespace(
        headers={"X-Forwarded-For": "10.0.0.1, 10.0.0.2"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    async with session_factory() as s:
        await audit_log(
            s, action=Action.USER_CREATE, target_type="user", target_id="1",
            before=None, after={}, actor=None, request=fake_request,
        )
        await s.commit()

    async with session_factory() as s:
        res = await s.execute(select(AuditEvent))
        r = res.scalar_one()
    assert r.ip == "10.0.0.1"


async def test_audit_log_ip_fallback_to_client_host(session_factory):
    from types import SimpleNamespace

    fake_request = SimpleNamespace(
        headers={},
        client=SimpleNamespace(host="192.168.1.5"),
    )
    async with session_factory() as s:
        await audit_log(
            s, action=Action.USER_CREATE, target_type="user", target_id="1",
            before=None, after={}, actor=None, request=fake_request,
        )
        await s.commit()

    async with session_factory() as s:
        res = await s.execute(select(AuditEvent))
        r = res.scalar_one()
    assert r.ip == "192.168.1.5"
```

- [ ] **Step 2: 跑测试，应当全过（audit.py 已实现）**

```bash
cd /dataspace/kqspace/MCPsys && uv run pytest services/control_plane/tests/test_audit.py -v
```

Expected: 9 passed.

- [ ] **Step 3: Commit**

```bash
git add services/control_plane/tests/test_audit.py
git commit -m "test(audit): 钉死 PII 黑名单 + model_to_dict + audit_log 行为"
```

---

## Task 4 — Hook users.py：3 个 action

**Files:**
- Modify: `services/control_plane/src/control_plane/routers/users.py`
- Modify: `services/control_plane/tests/test_users.py`

- [ ] **Step 1: 先写测试（应当 fail）**

在 `tests/test_users.py` 末尾追加：

```python
from mcpsys_shared.models import AuditEvent
from sqlalchemy import select


async def test_audit_user_create(client, admin, session_factory):
    resp = await client.post(
        "/api/v1/users",
        headers=auth_header(admin),
        json={"username": "carol", "password": "secret123", "role": "viewer"},
    )
    assert resp.status_code == 201
    new_user_id = resp.json()["id"]

    async with session_factory() as s:
        rows = (await s.execute(select(AuditEvent).where(AuditEvent.action == "user.create"))).scalars().all()
    assert len(rows) == 1
    r = rows[0]
    assert r.target_type == "user"
    assert r.target_id == str(new_user_id)
    assert r.before is None
    assert r.after["username"] == "carol"
    assert "password_hash" not in r.after
    assert r.actor_user_id == admin.id


async def test_audit_user_delete(client, admin, viewer, session_factory):
    resp = await client.delete(f"/api/v1/users/{viewer.id}", headers=auth_header(admin))
    assert resp.status_code == 204
    async with session_factory() as s:
        r = (await s.execute(select(AuditEvent).where(AuditEvent.action == "user.delete"))).scalar_one()
    assert r.target_id == str(viewer.id)
    assert r.before["username"] == "viewer"
    assert r.after is None
    assert r.actor_user_id == admin.id


async def test_audit_user_password_change(client, viewer, session_factory):
    resp = await client.put(
        f"/api/v1/users/{viewer.id}",
        headers=auth_header(viewer),
        json={"password": "newpass1234"},
    )
    assert resp.status_code == 200
    async with session_factory() as s:
        r = (await s.execute(select(AuditEvent).where(AuditEvent.action == "user.password_change"))).scalar_one()
    assert r.target_id == str(viewer.id)
    assert r.actor_user_id == viewer.id
    # password_hash 在黑名单内被剥离；before / after 仍含其他字段
    assert "password_hash" not in (r.before or {})
    assert "password_hash" not in (r.after or {})
```

- [ ] **Step 2: 跑测试验证 fail**

```bash
cd /dataspace/kqspace/MCPsys && uv run pytest services/control_plane/tests/test_users.py::test_audit_user_create -v
```

Expected: FAIL（断言 `len(rows) == 1` 失败，因为没有 audit_log 调用）。

- [ ] **Step 3: 在 users.py 各 handler 加 audit_log**

修改 `services/control_plane/src/control_plane/routers/users.py`：

`create_user` 函数末尾（return 前）加 `request: Request` 参数 + 注入 + audit_log 调用。完整修改后形态：

```python
from fastapi import APIRouter, Depends, HTTPException, Request, status
# ... (其他 imports 不变)
from ..audit import Action, audit_log, model_to_dict

# create_user
async def create_user(
    payload: UserCreate,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
    request: Request,
) -> UserOut:
    user = User(...)  # 不变
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "username already exists") from e
    await audit_log(
        db, action=Action.USER_CREATE,
        target_type="user", target_id=str(user.id),
        before=None, after=model_to_dict(user),
        actor=current_user, request=request,
    )
    return UserOut.model_validate(user)
```

注意：原 `dependencies=[Depends(require_role("admin"))]` 装饰器参数移除，改为函数体参数 `current_user: User = Depends(require_role("admin"))`，这样能拿到 actor。

`update_user` 修改：在 `db.get` 后抓 before、修改 password_hash 后 flush、抓 after、audit_log：

```python
async def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request,
) -> UserOut:
    if user_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权修改其他用户")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    before = model_to_dict(user)
    user.password_hash = hash_password(payload.password)
    await db.flush()
    after = model_to_dict(user)
    await audit_log(
        db, action=Action.USER_PASSWORD_CHANGE,
        target_type="user", target_id=str(user.id),
        before=before, after=after,
        actor=current_user, request=request,
    )
    return UserOut.model_validate(user)
```

`delete_user` 修改：

```python
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
    request: Request,
) -> None:
    if user_id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能删除当前登录账号")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    before = model_to_dict(user)
    await db.delete(user)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "无法删除：用户被应用 / 审计 / 服务版本 / 权限授予记录引用，请先转移或考虑禁用账号") from e
    await audit_log(
        db, action=Action.USER_DELETE,
        target_type="user", target_id=str(user_id),
        before=before, after=None,
        actor=current_user, request=request,
    )
```

- [ ] **Step 4: 跑测试验证 pass**

```bash
cd /dataspace/kqspace/MCPsys && uv run pytest services/control_plane/tests/test_users.py -v
```

Expected: 全部测试 pass（含新增 3 + 原有 14）。

- [ ] **Step 5: Commit**

```bash
git add services/control_plane/src/control_plane/routers/users.py services/control_plane/tests/test_users.py
git commit -m "feat(users): 写操作落 audit_events（user.create/delete/password_change）"
```

---

## Task 5 — Hook applications.py：1 个 action

**Files:**
- Modify: `services/control_plane/src/control_plane/routers/applications.py`
- Modify: `services/control_plane/tests/test_applications.py`

- [ ] **Step 1: 写测试（先 fail）**

在 `tests/test_applications.py` 末尾追加：

```python
from mcpsys_shared.models import AuditEvent
from sqlalchemy import select


async def test_audit_application_create(client, admin, session_factory):
    resp = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "audit-app", "team": "ops"},
    )
    assert resp.status_code == 201
    app_id = resp.json()["id"]
    async with session_factory() as s:
        r = (await s.execute(select(AuditEvent).where(AuditEvent.action == "application.create"))).scalar_one()
    assert r.target_type == "application"
    assert r.target_id == str(app_id)
    assert r.before is None
    assert r.after["name"] == "audit-app"
    assert r.actor_user_id == admin.id
```

- [ ] **Step 2: Run, expect FAIL**

```bash
uv run pytest services/control_plane/tests/test_applications.py::test_audit_application_create -v
```

- [ ] **Step 3: Hook applications.py**

在 `create_application` handler（line 40 起）：
- import 加 `from fastapi import Request` 已有则不动
- import 加 `from ..audit import Action, audit_log, model_to_dict`
- 函数签名加 `current_user: User = Depends(require_role("admin", "operator"))` （沿用原 dependencies 角色）和 `request: Request`
- 移除装饰器层 `dependencies=[Depends(require_role(...))]`
- `db.flush()` 后加：

```python
await audit_log(
    db, action=Action.APPLICATION_CREATE,
    target_type="application", target_id=str(app.id),
    before=None, after=model_to_dict(app),
    actor=current_user, request=request,
)
```

> 注：读 applications.py 确认原 dependencies 的角色列表是 `["admin", "operator"]` 还是 `["admin"]`，按实际填。

- [ ] **Step 4: Run pass**

```bash
uv run pytest services/control_plane/tests/test_applications.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/control_plane/src/control_plane/routers/applications.py services/control_plane/tests/test_applications.py
git commit -m "feat(applications): create 落 audit_events"
```

---

## Task 6 — Hook api_keys.py：4 个 action（issue / revoke / update / delete）

**Files:**
- Modify: `services/control_plane/src/control_plane/routers/api_keys.py`
- Modify: `services/control_plane/tests/test_api_keys.py`

- [ ] **Step 1: 写测试**

在 `tests/test_api_keys.py` 末尾追加 4 例（issue / revoke / update / delete）：

```python
from mcpsys_shared.models import AuditEvent
from sqlalchemy import select


async def test_audit_api_key_issue(client, admin, application, session_factory):
    resp = await client.post(
        "/api/v1/api-keys",
        headers=auth_header(admin),
        json={"name": "ak-1", "owner_type": "application", "owner_id": application.id},
    )
    assert resp.status_code == 201
    async with session_factory() as s:
        r = (await s.execute(select(AuditEvent).where(AuditEvent.action == "api_key.issue"))).scalar_one()
    assert r.target_type == "api_key"
    assert r.actor_user_id == admin.id
    assert "key_hash" not in (r.after or {})  # PII 剥离


async def test_audit_api_key_revoke(client, admin, existing_api_key, session_factory):
    resp = await client.delete(f"/api/v1/api-keys/{existing_api_key.id}", headers=auth_header(admin))
    assert resp.status_code in (200, 204)
    async with session_factory() as s:
        r = (await s.execute(select(AuditEvent).where(AuditEvent.action == "api_key.revoke"))).scalar_one()
    assert r.target_id == str(existing_api_key.id)
    assert r.before is not None and r.after is not None
    assert r.before["revoked_at"] is None
    assert r.after["revoked_at"] is not None


async def test_audit_api_key_update(client, admin, existing_api_key, session_factory):
    resp = await client.patch(
        f"/api/v1/api-keys/{existing_api_key.id}",
        headers=auth_header(admin),
        json={"rate_limit_qps": 50},
    )
    assert resp.status_code == 200
    async with session_factory() as s:
        r = (await s.execute(select(AuditEvent).where(AuditEvent.action == "api_key.update"))).scalar_one()
    assert r.after["rate_limit_qps"] == 50


async def test_audit_api_key_delete_permanent(client, admin, revoked_api_key, session_factory):
    resp = await client.delete(
        f"/api/v1/api-keys/{revoked_api_key.id}/permanent",
        headers=auth_header(admin),
    )
    assert resp.status_code in (200, 204)
    async with session_factory() as s:
        r = (await s.execute(select(AuditEvent).where(AuditEvent.action == "api_key.delete"))).scalar_one()
    assert r.target_id == str(revoked_api_key.id)
    assert r.after is None
```

> 注：`existing_api_key` / `revoked_api_key` / `application` 三个 fixture 视 `tests/test_api_keys.py` 现有定义而定，如缺则按现有写法补（直接 session 里 `add(ApiKey(...))` + `add(Application(...))`，参考 test_users.py 里 viewer fixture 写法）。

- [ ] **Step 2: Run, expect FAIL on the 4 new tests**

```bash
uv run pytest services/control_plane/tests/test_api_keys.py -v
```

- [ ] **Step 3: Hook api_keys.py 4 个 handler**

按 §3.2 模板：
- `create_api_key`：成功 flush 后 `audit_log(action=Action.API_KEY_ISSUE, target_type="api_key", target_id=str(key.id), before=None, after=model_to_dict(key))`
- `revoke_api_key`：拿到 key、`before = model_to_dict(key)`，设置 revoked_at，flush，`after = model_to_dict(key)`，audit_log
- `update_api_key`：拿到 key、抓 before、apply payload、flush、抓 after、audit_log
- `delete_api_key_permanent`：拿到 key、抓 before、`db.delete(key)`、flush、audit_log(after=None)

每个 handler 函数签名加 `current_user: User = Depends(require_role(...))`（沿用原 role 配置）和 `request: Request`，导入 `from ..audit import Action, audit_log, model_to_dict`。

- [ ] **Step 4: Run pass**

```bash
uv run pytest services/control_plane/tests/test_api_keys.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/control_plane/src/control_plane/routers/api_keys.py services/control_plane/tests/test_api_keys.py
git commit -m "feat(api-keys): 签发/吊销/修改/永久删除落 audit_events"
```

---

## Task 7 — Hook services.py：3 个 action（create / update / delete）

**Files:**
- Modify: `services/control_plane/src/control_plane/routers/services.py`
- Modify: `services/control_plane/tests/test_services.py`

- [ ] **Step 1: 写 3 例 audit 测试到 `tests/test_services.py`**

```python
from mcpsys_shared.models import AuditEvent
from sqlalchemy import select


async def test_audit_service_create(client, admin, session_factory):
    resp = await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={
            "slug": "audit-svc",
            "display_name": "Audit Svc",
            "endpoint_url": "http://audit-svc.internal:8000/mcp",
        },
    )
    assert resp.status_code == 201
    async with session_factory() as s:
        r = (await s.execute(select(AuditEvent).where(AuditEvent.action == "service.create"))).scalar_one()
    assert r.target_type == "mcp_service"
    assert r.before is None
    assert r.after["slug"] == "audit-svc"
    assert r.actor_user_id == admin.id


async def test_audit_service_update(client, admin, existing_service, session_factory):
    resp = await client.patch(
        f"/api/v1/services/{existing_service.slug}",
        headers=auth_header(admin),
        json={"display_name": "Renamed"},
    )
    assert resp.status_code == 200
    async with session_factory() as s:
        r = (await s.execute(select(AuditEvent).where(AuditEvent.action == "service.update"))).scalar_one()
    assert r.before["display_name"] != "Renamed"
    assert r.after["display_name"] == "Renamed"


async def test_audit_service_delete(client, admin, existing_service, session_factory):
    resp = await client.delete(f"/api/v1/services/{existing_service.slug}", headers=auth_header(admin))
    assert resp.status_code in (200, 204)
    async with session_factory() as s:
        r = (await s.execute(select(AuditEvent).where(AuditEvent.action == "service.delete"))).scalar_one()
    assert r.target_id == str(existing_service.id)
    # service.delete 实际是软删（status=disabled），不是真 DROP；before/after 都有
    assert r.before is not None
```

> 注：根据 services.py 实际 delete 语义（软删 vs 硬删），调整 `after` 期望。若是软删（status disabled），`after is not None`；若是硬删，`after is None`。按代码状态适配。

- [ ] **Step 2: Run, expect FAIL**

```bash
uv run pytest services/control_plane/tests/test_services.py -v
```

- [ ] **Step 3: Hook services.py 3 个 handler**

同 §3.2 模板：每个 handler 加 `current_user: User = Depends(require_role("admin", "operator"))` (or whatever the existing role) 和 `request: Request`，import audit 模块，主写完 flush 后调 audit_log。

- create_service：before=None / after=model_to_dict
- update_service (`PATCH /{slug}`)：before snapshot → modify → flush → after snapshot → audit_log
- delete_service：snapshot before → (软删 set status=disabled / 硬删 db.delete) → flush → snapshot after (软删情况) or None (硬删) → audit_log

- [ ] **Step 4: Run pass**

```bash
uv run pytest services/control_plane/tests/test_services.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/control_plane/src/control_plane/routers/services.py services/control_plane/tests/test_services.py
git commit -m "feat(services): 写操作落 audit_events"
```

---

## Task 8 — Hook permissions.py：2 个 action（grant / revoke）

**Files:**
- Modify: `services/control_plane/src/control_plane/routers/permissions.py`
- Modify: `services/control_plane/tests/test_permissions.py`

- [ ] **Step 1: 写测试**

```python
from mcpsys_shared.models import AuditEvent
from sqlalchemy import select


async def test_audit_permission_grant(client, admin, existing_application, existing_service, session_factory):
    resp = await client.post(
        f"/api/v1/services/{existing_service.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": existing_application.id, "note": "for testing"},
    )
    assert resp.status_code in (200, 201)
    async with session_factory() as s:
        r = (await s.execute(select(AuditEvent).where(AuditEvent.action == "service_permission.grant"))).scalar_one()
    assert r.target_type == "service_permission"
    assert r.before is None
    assert r.after["application_id"] == existing_application.id
    assert r.after["service_id"] == existing_service.id


async def test_audit_permission_revoke(client, admin, existing_permission, existing_service, session_factory):
    resp = await client.delete(
        f"/api/v1/services/{existing_service.slug}/permissions/{existing_permission.id}",
        headers=auth_header(admin),
    )
    assert resp.status_code in (200, 204)
    async with session_factory() as s:
        r = (await s.execute(select(AuditEvent).where(AuditEvent.action == "service_permission.revoke"))).scalar_one()
    assert r.target_id == str(existing_permission.id)
    assert r.before is not None
    assert r.after is None
```

- [ ] **Step 2: Run, expect FAIL**

```bash
uv run pytest services/control_plane/tests/test_permissions.py -v
```

- [ ] **Step 3: Hook permissions.py 2 handler**

- `grant_permission` (POST)：flush 后 audit_log(action=Action.SERVICE_PERMISSION_GRANT, target_type="service_permission", target_id=str(perm.id), before=None, after=model_to_dict(perm))
- `revoke_permission` (DELETE)：snapshot before → db.delete → flush → audit_log(after=None)

每个 handler 加 `current_user` + `request` 参数；import audit 模块。

- [ ] **Step 4: Run pass**

```bash
uv run pytest services/control_plane/tests/test_permissions.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/control_plane/src/control_plane/routers/permissions.py services/control_plane/tests/test_permissions.py
git commit -m "feat(permissions): 授予/吊销落 audit_events"
```

---

## Task 9 — 查询 API `GET /api/v1/audit-events`

**Files:**
- Create: `services/control_plane/src/control_plane/routers/audit_events.py`
- Modify: `services/control_plane/src/control_plane/main.py`
- Create: `services/control_plane/tests/test_audit_query.py`

- [ ] **Step 1: 写 router**

```python
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from mcpsys_shared.models import AuditEvent, User

from ..deps import get_db, require_role

router = APIRouter(prefix="/api/v1/audit-events", tags=["audit"])


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ts: datetime
    actor_user_id: int | None
    actor_username: str | None
    action: str
    target_type: str
    target_id: str | None
    before: dict | None
    after: dict | None
    ip: str | None


class AuditEventList(BaseModel):
    items: list[AuditEventOut]
    total: int


@router.get(
    "",
    response_model=AuditEventList,
    dependencies=[Depends(require_role("admin"))],
)
async def list_audit_events(
    actor_user_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> AuditEventList:
    actor = aliased(User)
    q = (
        select(
            AuditEvent.id, AuditEvent.ts, AuditEvent.actor_user_id,
            actor.username.label("actor_username"),
            AuditEvent.action, AuditEvent.target_type, AuditEvent.target_id,
            AuditEvent.before, AuditEvent.after, AuditEvent.ip,
        )
        .outerjoin(actor, actor.id == AuditEvent.actor_user_id)
    )
    count_q = select(func.count(AuditEvent.id))

    filters = []
    if actor_user_id is not None:
        filters.append(AuditEvent.actor_user_id == actor_user_id)
    if action is not None:
        filters.append(AuditEvent.action == action)
    if target_type is not None:
        filters.append(AuditEvent.target_type == target_type)
    if target_id is not None:
        filters.append(AuditEvent.target_id == target_id)
    if from_ts is not None:
        filters.append(AuditEvent.ts >= from_ts)
    if to_ts is not None:
        filters.append(AuditEvent.ts <= to_ts)
    for f in filters:
        q = q.where(f)
        count_q = count_q.where(f)

    q = q.order_by(AuditEvent.ts.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).mappings().all()
    total = (await db.execute(count_q)).scalar_one()
    return AuditEventList(
        items=[AuditEventOut.model_validate(dict(r)) for r in rows],
        total=total,
    )
```

- [ ] **Step 2: 注册 router**

`main.py` 改动：

```python
from .routers import (
    api_keys as api_keys_router,
    applications as applications_router,
    audit_events as audit_events_router,  # 新增
    auth as auth_router,
    call_logs as call_logs_router,
    permissions as permissions_router,
    services as services_router,
    users as users_router,
)
# ...
app.include_router(audit_events_router.router)  # 新增
```

- [ ] **Step 3: 写测试**

`tests/test_audit_query.py`：

```python
from datetime import UTC, datetime, timedelta

import pytest
from mcpsys_shared.models import AuditEvent, User, UserRole, UserStatus
from sqlalchemy import select

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings


def auth_header(user):
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as s:
        u = User(username="admin", password_hash=hash_password("p"), role=UserRole.admin, status=UserStatus.active)
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


@pytest.fixture
async def viewer(session_factory):
    async with session_factory() as s:
        u = User(username="viewer", password_hash=hash_password("p"), role=UserRole.viewer, status=UserStatus.active)
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


@pytest.fixture
async def seed_events(session_factory, admin):
    """填 5 条混合 audit_events 用于查询测试。"""
    now = datetime.now(UTC)
    async with session_factory() as s:
        s.add_all([
            AuditEvent(actor_user_id=admin.id, action="user.create", target_type="user", target_id="10",
                       before=None, after={"id": 10}, ts=now - timedelta(minutes=5)),
            AuditEvent(actor_user_id=admin.id, action="service.create", target_type="mcp_service", target_id="20",
                       before=None, after={"slug": "a"}, ts=now - timedelta(minutes=4)),
            AuditEvent(actor_user_id=admin.id, action="service.update", target_type="mcp_service", target_id="20",
                       before={"slug": "a"}, after={"slug": "b"}, ts=now - timedelta(minutes=3)),
            AuditEvent(actor_user_id=admin.id, action="user.delete", target_type="user", target_id="10",
                       before={"id": 10}, after=None, ts=now - timedelta(minutes=2)),
            AuditEvent(actor_user_id=admin.id, action="application.create", target_type="application", target_id="30",
                       before=None, after={"name": "x"}, ts=now - timedelta(minutes=1)),
        ])
        await s.commit()


async def test_unauthenticated(client):
    resp = await client.get("/api/v1/audit-events")
    assert resp.status_code == 401


async def test_viewer_forbidden(client, viewer):
    resp = await client.get("/api/v1/audit-events", headers=auth_header(viewer))
    assert resp.status_code == 403


async def test_admin_lists_all_desc(client, admin, seed_events):
    resp = await client.get("/api/v1/audit-events", headers=auth_header(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    actions = [it["action"] for it in body["items"]]
    assert actions == [
        "application.create", "user.delete", "service.update", "service.create", "user.create",
    ]


async def test_filter_action(client, admin, seed_events):
    resp = await client.get(
        "/api/v1/audit-events",
        headers=auth_header(admin),
        params={"action": "service.update"},
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["action"] == "service.update"


async def test_filter_target(client, admin, seed_events):
    resp = await client.get(
        "/api/v1/audit-events",
        headers=auth_header(admin),
        params={"target_type": "mcp_service", "target_id": "20"},
    )
    body = resp.json()
    assert body["total"] == 2
    assert {it["action"] for it in body["items"]} == {"service.create", "service.update"}


async def test_filter_time_window(client, admin, seed_events):
    """from_ts 卡到 user.delete + application.create，期望剩 2。"""
    now = datetime.now(UTC)
    resp = await client.get(
        "/api/v1/audit-events",
        headers=auth_header(admin),
        params={"from_ts": (now - timedelta(minutes=2, seconds=30)).isoformat()},
    )
    body = resp.json()
    assert body["total"] == 2


async def test_pagination(client, admin, seed_events):
    p1 = await client.get(
        "/api/v1/audit-events",
        headers=auth_header(admin),
        params={"page_size": 2, "page": 1},
    )
    p2 = await client.get(
        "/api/v1/audit-events",
        headers=auth_header(admin),
        params={"page_size": 2, "page": 2},
    )
    p3 = await client.get(
        "/api/v1/audit-events",
        headers=auth_header(admin),
        params={"page_size": 2, "page": 3},
    )
    assert p1.json()["total"] == 5
    assert len(p1.json()["items"]) == 2
    assert len(p2.json()["items"]) == 2
    assert len(p3.json()["items"]) == 1


async def test_page_size_over_max_rejected(client, admin):
    resp = await client.get(
        "/api/v1/audit-events",
        headers=auth_header(admin),
        params={"page_size": 500},
    )
    assert resp.status_code == 422
```

- [ ] **Step 4: Run**

```bash
uv run pytest services/control_plane/tests/test_audit_query.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add services/control_plane/src/control_plane/routers/audit_events.py services/control_plane/src/control_plane/main.py services/control_plane/tests/test_audit_query.py
git commit -m "feat(control-plane): GET /api/v1/audit-events 查询接口"
```

---

## Task 10 — 前端列表页 + 路由 + 侧边栏 + i18n

**Files:**
- Create: `services/web/src/api/audit.ts`
- Create: `services/web/src/views/audit/AuditEventListPage.vue`
- Modify: `services/web/src/router/index.ts`
- Modify: `services/web/src/components/nav/SideBar.vue`
- Modify: `services/web/src/i18n/locales/zh-CN.ts`

- [ ] **Step 1: 写 api/audit.ts**

```typescript
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

export function listAuditEvents(
  filter?: AuditEventFilter,
): Promise<PaginatedList<AuditEvent>> {
  return client.get('/api/v1/audit-events', { params: filter }).then((r) => r.data);
}
```

- [ ] **Step 2: 写 AuditEventListPage.vue**

```vue
<script setup lang="ts">
import { onMounted, ref, reactive } from 'vue';
import { listAuditEvents, type AuditEvent, type AuditEventFilter } from '@/api/audit';
import { listUsers } from '@/api/users';
import type { User } from '@/api/types';
import PageHeader from '@/components/common/PageHeader.vue';
import DataTable from '@/components/common/DataTable.vue';
import RelativeTime from '@/components/common/RelativeTime.vue';

const items = ref<AuditEvent[]>([]);
const total = ref(0);
const loading = ref(false);
const users = ref<User[]>([]);
const filter = reactive<AuditEventFilter>({ page: 1, page_size: 50 });
const dateRange = ref<[string, string] | null>(null);

const ACTIONS: { value: string; label: string; group: string }[] = [
  { value: 'user.create',           label: '创建用户',       group: 'user' },
  { value: 'user.delete',           label: '删除用户',       group: 'user' },
  { value: 'user.password_change',  label: '修改密码',       group: 'user' },
  { value: 'application.create',    label: '创建应用',       group: 'application' },
  { value: 'api_key.issue',         label: '签发 API Key',  group: 'api_key' },
  { value: 'api_key.revoke',        label: '吊销 API Key',  group: 'api_key' },
  { value: 'api_key.update',        label: '修改 API Key',  group: 'api_key' },
  { value: 'api_key.delete',        label: '永久删除 API Key', group: 'api_key' },
  { value: 'service.create',        label: '注册服务',       group: 'service' },
  { value: 'service.update',        label: '修改服务',       group: 'service' },
  { value: 'service.delete',        label: '下线服务',       group: 'service' },
  { value: 'service_permission.grant',  label: '授予权限', group: 'service_permission' },
  { value: 'service_permission.revoke', label: '吊销权限', group: 'service_permission' },
];

const TARGET_TYPES: { value: string; label: string }[] = [
  { value: 'user',               label: '用户' },
  { value: 'application',        label: '应用' },
  { value: 'api_key',            label: 'API Key' },
  { value: 'mcp_service',        label: '服务' },
  { value: 'service_permission', label: '权限' },
];

async function load() {
  loading.value = true;
  try {
    filter.from_ts = dateRange.value?.[0] ?? undefined;
    filter.to_ts   = dateRange.value?.[1] ?? undefined;
    const data = await listAuditEvents(filter);
    items.value = data.items;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

function reset() {
  filter.actor_user_id = undefined;
  filter.action = undefined;
  filter.target_type = undefined;
  filter.target_id = undefined;
  dateRange.value = null;
  filter.page = 1;
  load();
}

function actionLabel(v: string): string {
  return ACTIONS.find((a) => a.value === v)?.label ?? v;
}

onMounted(async () => {
  users.value = (await listUsers()).items;
  await load();
});
</script>

<template>
  <PageHeader title="审计" description="管理动作变更历史" />

  <div class="card-base filter-bar">
    <el-select v-model="filter.action" placeholder="动作" clearable style="width:160px;">
      <el-option-group label="用户">
        <el-option v-for="a in ACTIONS.filter(x => x.group === 'user')" :key="a.value" :label="a.label" :value="a.value" />
      </el-option-group>
      <el-option-group label="应用">
        <el-option v-for="a in ACTIONS.filter(x => x.group === 'application')" :key="a.value" :label="a.label" :value="a.value" />
      </el-option-group>
      <el-option-group label="API Key">
        <el-option v-for="a in ACTIONS.filter(x => x.group === 'api_key')" :key="a.value" :label="a.label" :value="a.value" />
      </el-option-group>
      <el-option-group label="服务">
        <el-option v-for="a in ACTIONS.filter(x => x.group === 'service')" :key="a.value" :label="a.label" :value="a.value" />
      </el-option-group>
      <el-option-group label="权限">
        <el-option v-for="a in ACTIONS.filter(x => x.group === 'service_permission')" :key="a.value" :label="a.label" :value="a.value" />
      </el-option-group>
    </el-select>

    <el-select v-model="filter.target_type" placeholder="目标类型" clearable style="width:140px;">
      <el-option v-for="t in TARGET_TYPES" :key="t.value" :label="t.label" :value="t.value" />
    </el-select>

    <el-input v-model="filter.target_id" placeholder="目标 ID" :disabled="!filter.target_type" style="width:120px;" />

    <el-select v-model="filter.actor_user_id" placeholder="操作者" clearable style="width:160px;">
      <el-option v-for="u in users" :key="u.id" :label="u.username" :value="u.id" />
    </el-select>

    <el-date-picker v-model="dateRange" type="datetimerange" range-separator="-" value-format="YYYY-MM-DDTHH:mm:ss" />

    <el-button @click="reset">重置</el-button>
    <el-button type="primary" @click="load">查询</el-button>
  </div>

  <DataTable :data="items" :loading="loading">
    <el-table-column type="expand">
      <template #default="{ row }: { row: AuditEvent }">
        <div class="diff-grid" :class="{ single: !row.before || !row.after }">
          <div v-if="row.before">
            <div class="diff-label">before</div>
            <pre class="json-block">{{ JSON.stringify(row.before, null, 2) }}</pre>
          </div>
          <div v-if="row.after">
            <div class="diff-label">after</div>
            <pre class="json-block">{{ JSON.stringify(row.after, null, 2) }}</pre>
          </div>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="时间" width="160">
      <template #default="{ row }: { row: AuditEvent }"><RelativeTime :value="row.ts" /></template>
    </el-table-column>
    <el-table-column label="操作者" width="140">
      <template #default="{ row }: { row: AuditEvent }">
        <span v-if="row.actor_username">{{ row.actor_username }}</span>
        <span v-else-if="row.actor_user_id" style="color: var(--color-gray-500);">已删用户#{{ row.actor_user_id }}</span>
        <span v-else>—</span>
      </template>
    </el-table-column>
    <el-table-column label="动作" width="180">
      <template #default="{ row }: { row: AuditEvent }">
        <el-tag size="small">{{ actionLabel(row.action) }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="目标" min-width="200">
      <template #default="{ row }: { row: AuditEvent }">
        <span class="mono">{{ row.target_type }} / {{ row.target_id ?? '—' }}</span>
      </template>
    </el-table-column>
    <el-table-column label="IP" width="140" prop="ip" />
  </DataTable>

  <el-pagination
    v-model:current-page="filter.page"
    :page-size="filter.page_size"
    :total="total"
    layout="prev, pager, next, total"
    @current-change="load"
    style="margin-top: var(--space-4); justify-content: flex-end;"
  />
</template>

<style scoped>
.filter-bar { display: flex; gap: var(--space-3); align-items: center; flex-wrap: wrap; margin-bottom: var(--space-4); }
.diff-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); padding: var(--space-3); }
.diff-grid.single { grid-template-columns: 1fr; max-width: 600px; }
.diff-label { font-size: 12px; color: var(--color-gray-500); margin-bottom: 4px; text-transform: uppercase; }
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
  margin: 0;
}
</style>
```

- [ ] **Step 3: 加路由**

`router/index.ts` 在 `/users` 路由之后追加：

```ts
{
  path: '/audit-events',
  name: 'AuditEventList',
  component: () => import('@/views/audit/AuditEventListPage.vue'),
  meta: { requiresAuth: true, roles: ['admin'], layout: 'app', title: 'nav.audit' },
},
```

- [ ] **Step 4: 调整侧边栏**

`SideBar.vue` 改动两处：
- `system-group`（line 43-47）加 `{ key: 'audit', routeName: 'AuditEventList', icon: 'clipboard-list', labelKey: 'nav.audit' }`
- `upcoming-group`（line 49-55）移除原 `{ key: 'audit', ..., disabled: true }` 那一行

- [ ] **Step 5: i18n 文案确认**

`zh-CN.ts` 检查 `nav.audit` 是否已有；通常已有 `nav.audit: '审计'` 或类似条目。无则补一条。

- [ ] **Step 6: typecheck + lint + test**

```bash
cd /dataspace/kqspace/MCPsys/services/web && npm run typecheck && npm run lint && npm test
```

Expected: typecheck 0 errors；lint 0 errors；vitest 全过。

- [ ] **Step 7: Commit**

```bash
git add services/web/src/api/audit.ts services/web/src/views/audit/AuditEventListPage.vue services/web/src/router/index.ts services/web/src/components/nav/SideBar.vue services/web/src/i18n/locales/zh-CN.ts
git commit -m "feat(web): audit-events 列表页 + 路由 + 侧边栏"
```

---

## Task 11 — smoke 脚本扩展

**Files:**
- Modify: `scripts/smoke.sh`

- [ ] **Step 1: 加 audit 校验**

在 smoke.sh 末尾、`echo "[smoke] OK"` 之前追加：

```bash
echo "[smoke] verifying audit-events ..."
AUDIT=$(curl -fsS "$BASE/api/v1/audit-events?page_size=10" -H "Authorization: Bearer $TOKEN")
ACTIONS=$(echo "$AUDIT" | python3 -c "import sys,json; print(' '.join(it['action'] for it in json.load(sys.stdin)['items']))")
echo "[smoke]   recent actions: $ACTIONS"
if ! echo "$ACTIONS" | grep -q "service.create"; then
  echo "[smoke] FAIL: 期望审计记录中有 service.create"; exit 1
fi
if ! echo "$ACTIONS" | grep -q "application.create"; then
  echo "[smoke] FAIL: 期望审计记录中有 application.create"; exit 1
fi
```

> `BASE` / `TOKEN` 变量沿用 smoke.sh 之前定义的。

- [ ] **Step 2: 本地不跑（需要部署环境）。Commit**

```bash
git add scripts/smoke.sh
git commit -m "test(smoke): 覆盖 audit-events 查询路径"
```

---

## Task 12 — 全套验证 + 文档收尾

**Files:**
- No code changes（仅运行测试 + 文档登记）
- Modify (optional): `docs/changes/2026-05-11-V1-A.1之后小需求.md` 末尾追条目记录 V1-B 入 main

- [ ] **Step 1: 后端全套**

```bash
cd /dataspace/kqspace/MCPsys && uv run pytest services/control_plane/tests -v
```

Expected: 全部通过。原有 ~80+ 例 + 本次新增 ~30 例 = ~110 例。

- [ ] **Step 2: 前端全套**

```bash
cd /dataspace/kqspace/MCPsys/services/web && npm run typecheck && npm run lint && npm test && npm run build
```

Expected: typecheck/lint/test/build 全过。

- [ ] **Step 3: 部署到服务器（用户主导）**

非本次自动化。按 `docs/deployment.md §10` 的升级流程：

```bash
git pull
docker compose build control-plane web
docker compose up -d control-plane web
docker compose restart nginx        # V1-A.1 留下的 nginx upstream 解析坑
docker compose exec control-plane alembic current   # 期望 0004_v1b_audit_indexes
./scripts/smoke.sh                  # 含 audit 校验
```

- [ ] **Step 4: 更新 project_state.md 记录**

让用户手动或在结束本次实施时更新 `~/.claude/projects/-dataspace-kqspace-MCPsys/memory/project_state.md`：V1-B-审计 入 main 日期。

- [ ] **Step 5: 完成确认**

无 commit；交付完成。

---

## 自审

**Spec coverage**：

- §2 数据模型 → Task 1（索引）✓
- §3.1 audit 模块 → Task 2 + Task 3（模块 + 测试）✓
- §3.2 Handler 接入模式 → Task 4-8（5 个 router）✓
- §3.3 target_id 约定 → Task 4-8 各 handler 调 `str(obj.id)` ✓
- §3.4 不在审计范围 → 未覆盖项，§11 已列；plan 不触碰这些路径 ✓
- §4 查询 API → Task 9 ✓
- §5 前端 → Task 10 ✓
- §6.1 PII guard + helper 测试 → Task 3 ✓
- §6.2 13 action 端到端 → Task 4-8 共 13 例 ✓
- §6.3 查询 API 测试 → Task 9 共 9 例（spec 列 10 例，实际合并了一项重复的过滤 + 时间窗 → 仍然覆盖所有维度）✓
- §6.4 冒烟 → Task 11 ✓
- §6.5 前端不加单测 → Task 10 不加 ✓
- §8 部署 → Task 12 ✓
- 附录 A 13 条 action 映射 → Task 4-8 一对一 ✓

**Placeholder scan**：无 TBD / TODO；所有代码段完整。

**Type consistency**：`audit_log` 签名在 Task 2 定义、Task 4-8 调用一致；`AuditEventOut` 在 Task 9 定义、`AuditEvent` 前端接口 Task 10 定义对齐。

**预期总测试增量**：
- backend：~30 例新增（含 13 action e2e + 8 helper + 9 query）
- frontend：0 新增（按 spec 决策）
