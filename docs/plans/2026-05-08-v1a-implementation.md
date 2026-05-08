# V1-A · 访问控制 & 限流 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 MCP 网关上落地 service 级白名单授权（PR1）和 per-key/per-service 双桶 QPS 限流（PR2），并把被拒事件做成 call_logs 一等公民。

**Architecture:** 鉴权链顺序 `auth → permission → ratelimit → forward`；permission 用 30s 进程内 dict cache；ratelimit 用 Redis Lua token bucket（burst = 2×qps）。每个能力端到端打包：schema → control-plane API → gateway 接入 → Web UI。两个 PR 串行交付。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Pydantic v2 / asyncpg / redis-py async / Vue 3 + Element Plus / pytest-asyncio + testcontainers / alembic。

**参考文档:** `docs/specs/2026-05-08-v1a-access-control-and-ratelimit-design.md`

---

## 文件结构

新增文件：

```
packages/mcpsys_shared/src/mcpsys_shared/models.py          # 加 ServicePermission 类、CallStatus 加值、ApiKey/McpService 加列
services/control_plane/alembic/versions/0002_v1a_permissions.py   # PR1 migration
services/control_plane/alembic/versions/0003_v1a_ratelimit.py     # PR2 migration
services/control_plane/src/control_plane/routers/permissions.py   # PR1 router
services/control_plane/tests/test_permissions.py                  # PR1 router tests
services/gateway/src/gateway/policy.py                            # PolicyCache 模块
services/gateway/src/gateway/ratelimit.py                         # TokenBucket 模块
services/gateway/tests/test_policy.py
services/gateway/tests/test_ratelimit.py
scripts/bootstrap_permissions.py                                  # 笛卡尔积 bootstrap
services/web/src/api/permissions.ts                               # 前端 API 客户端
```

修改文件：

```
services/control_plane/src/control_plane/main.py                  # include permissions router
services/control_plane/src/control_plane/routers/services.py      # ServiceCreate/Update 加 rate_limit_qps
services/control_plane/src/control_plane/routers/api_keys.py      # ApiKeyCreate/Update 加 rate_limit_qps
services/gateway/src/gateway/main.py                              # 注入 PolicyCache + TokenBucket 到 app.state
services/gateway/src/gateway/routers/mcp.py                       # 接入 permission + ratelimit
services/gateway/tests/conftest.py                                # 注入 policy / ratelimit fixture
services/web/src/api/services.ts                                  # 类型 + 表单字段
services/web/src/api/api-keys.ts                                  # 类型 + 表单字段
services/web/src/api/types.ts                                     # CallStatus 加值
services/web/src/views/services/ServiceDetailPage.vue             # 「授权应用」面板 + QPS 字段
services/web/src/views/api-keys/...                               # QPS 字段
services/web/src/views/call-logs/CallLogsPage.vue                 # 状态筛选加 denied/throttled
scripts/smoke.sh                                                   # grant 步骤 + 403/429 路径
```

---

# Phase 1 (PR1) — service_permissions 白名单

## Task 1 · ServicePermission 模型 + alembic 迁移

**Files:**
- Modify: `packages/mcpsys_shared/src/mcpsys_shared/models.py`
- Create: `services/control_plane/alembic/versions/0002_v1a_permissions.py`

- [ ] **Step 1.1: 在 `models.py` 末尾追加 ServicePermission 类**

```python
class ServicePermission(Base):
    """White-list grant: (application × service). Row exists ⇒ allowed.
    Default-deny semantics: no row means no access."""

    __tablename__ = "service_permissions"
    __table_args__ = (
        UniqueConstraint("application_id", "service_id", name="uq_service_permissions_app_service"),
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

- [ ] **Step 1.2: 写 alembic 迁移 0002**

文件：`services/control_plane/alembic/versions/0002_v1a_permissions.py`

```python
"""v1a permissions

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-08 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "service_id",
            sa.Integer(),
            sa.ForeignKey("mcp_services.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("granted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.UniqueConstraint("application_id", "service_id", name="uq_service_permissions_app_service"),
    )
    op.create_index("ix_service_permissions_service", "service_permissions", ["service_id"])


def downgrade() -> None:
    op.drop_index("ix_service_permissions_service", table_name="service_permissions")
    op.drop_table("service_permissions")
```

- [ ] **Step 1.3: 跑迁移**

```bash
cd services/control_plane && uv run alembic upgrade head
```

期望输出包含 `Running upgrade 0001 -> 0002, v1a permissions`。

- [ ] **Step 1.4: 提交**

```bash
git add packages/mcpsys_shared/src/mcpsys_shared/models.py \
  services/control_plane/alembic/versions/0002_v1a_permissions.py
git commit -m "feat(schema): service_permissions table for application-level whitelist"
```

---

## Task 2 · permissions 路由 + 测试

**Files:**
- Create: `services/control_plane/src/control_plane/routers/permissions.py`
- Create: `services/control_plane/tests/test_permissions.py`
- Modify: `services/control_plane/src/control_plane/main.py`

- [ ] **Step 2.1: 写测试 `test_permissions.py`**

```python
import pytest

from mcpsys_shared.models import Application, McpService, User, UserRole, UserStatus

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as s:
        u = User(
            username="admin-perm",
            password_hash=hash_password("p"),
            role=UserRole.admin,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


@pytest.fixture
async def viewer(session_factory):
    async with session_factory() as s:
        u = User(
            username="viewer-perm",
            password_hash=hash_password("p"),
            role=UserRole.viewer,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


@pytest.fixture
async def app_row(session_factory, admin):
    async with session_factory() as s:
        a = Application(name="perm-app", owner_user_id=admin.id, team="t")
        s.add(a)
        await s.commit()
        await s.refresh(a)
        return a


@pytest.fixture
async def svc_row(session_factory):
    async with session_factory() as s:
        svc = McpService(slug="perm-svc", display_name="P", endpoint_url="http://p/mcp")
        s.add(svc)
        await s.commit()
        await s.refresh(svc)
        return svc


def auth_header(user):
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


async def test_grant_permission(client, admin, app_row, svc_row):
    resp = await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id, "note": "for crm bot"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["application_id"] == app_row.id
    assert body["service_id"] == svc_row.id
    assert body["note"] == "for crm bot"
    assert body["granted_by"] == admin.id


async def test_grant_is_idempotent(client, admin, app_row, svc_row):
    await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id},
    )
    resp = await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id, "note": "second call"},
    )
    assert resp.status_code == 200  # 200 not 201, not 409
    assert resp.json()["application_id"] == app_row.id


async def test_list_service_permissions(client, admin, app_row, svc_row):
    await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id},
    )
    resp = await client.get(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(it["application_id"] == app_row.id for it in items)


async def test_revoke_permission(client, admin, app_row, svc_row):
    await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id},
    )
    resp = await client.delete(
        f"/api/v1/services/{svc_row.slug}/permissions/{app_row.id}",
        headers=auth_header(admin),
    )
    assert resp.status_code == 204


async def test_revoke_unknown_grant_is_204(client, admin, app_row, svc_row):
    resp = await client.delete(
        f"/api/v1/services/{svc_row.slug}/permissions/{app_row.id}",
        headers=auth_header(admin),
    )
    assert resp.status_code == 204  # idempotent


async def test_reverse_list_by_application(client, admin, app_row, svc_row):
    await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id},
    )
    resp = await client.get(
        f"/api/v1/applications/{app_row.id}/permissions",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(it["service_id"] == svc_row.id for it in items)


async def test_viewer_cannot_write_permission(client, viewer, app_row, svc_row):
    resp = await client.post(
        f"/api/v1/services/{svc_row.slug}/permissions",
        headers=auth_header(viewer),
        json={"application_id": app_row.id},
    )
    assert resp.status_code == 403


async def test_grant_unknown_service_is_404(client, admin, app_row):
    resp = await client.post(
        "/api/v1/services/no-such-svc/permissions",
        headers=auth_header(admin),
        json={"application_id": app_row.id},
    )
    assert resp.status_code == 404
```

- [ ] **Step 2.2: 跑测试确认全 fail**

```bash
cd services/control_plane && uv run pytest tests/test_permissions.py -v
```

期望：所有 test 都因 `404 service /api/v1/...permissions not found` / collection error 失败。

- [ ] **Step 2.3: 写 router 文件 `permissions.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mcpsys_shared.models import Application, McpService, ServicePermission

from ..deps import get_db, get_current_user, require_role


router = APIRouter(tags=["permissions"])


class PermissionCreate(BaseModel):
    application_id: int
    note: str | None = None


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    application_id: int
    service_id: int
    granted_by: int | None
    granted_at: str
    note: str | None


class PermissionList(BaseModel):
    items: list[PermissionOut]
    total: int


async def _get_service_by_slug(slug: str, db: AsyncSession) -> McpService:
    res = await db.execute(select(McpService).where(McpService.slug == slug))
    svc = res.scalar_one_or_none()
    if svc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "service not found")
    return svc


@router.post(
    "/api/v1/services/{slug}/permissions",
    response_model=PermissionOut,
    dependencies=[Depends(require_role("admin", "operator"))],
)
async def grant_permission(
    slug: str,
    payload: PermissionCreate,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_user),
) -> PermissionOut:
    svc = await _get_service_by_slug(slug, db)

    res = await db.execute(select(Application).where(Application.id == payload.application_id))
    if res.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "application not found")

    res = await db.execute(
        select(ServicePermission).where(
            ServicePermission.application_id == payload.application_id,
            ServicePermission.service_id == svc.id,
        )
    )
    existing = res.scalar_one_or_none()
    if existing is not None:
        # idempotent: return 200 with the existing row
        response.status_code = status.HTTP_200_OK
        return PermissionOut.model_validate(_serialize(existing))

    perm = ServicePermission(
        application_id=payload.application_id,
        service_id=svc.id,
        granted_by=actor.id,
        note=payload.note,
    )
    db.add(perm)
    try:
        await db.flush()
    except IntegrityError as e:
        # race: another concurrent grant succeeded; re-read and return 200
        await db.rollback()
        res = await db.execute(
            select(ServicePermission).where(
                ServicePermission.application_id == payload.application_id,
                ServicePermission.service_id == svc.id,
            )
        )
        existing = res.scalar_one()
        response.status_code = status.HTTP_200_OK
        return PermissionOut.model_validate(_serialize(existing))

    response.status_code = status.HTTP_201_CREATED
    return PermissionOut.model_validate(_serialize(perm))


@router.get(
    "/api/v1/services/{slug}/permissions",
    response_model=PermissionList,
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)
async def list_service_permissions(
    slug: str, db: AsyncSession = Depends(get_db)
) -> PermissionList:
    svc = await _get_service_by_slug(slug, db)
    res = await db.execute(
        select(ServicePermission)
        .where(ServicePermission.service_id == svc.id)
        .order_by(ServicePermission.id)
    )
    rows = res.scalars().all()
    items = [PermissionOut.model_validate(_serialize(r)) for r in rows]
    return PermissionList(items=items, total=len(items))


@router.delete(
    "/api/v1/services/{slug}/permissions/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("admin", "operator"))],
)
async def revoke_permission(
    slug: str, application_id: int, db: AsyncSession = Depends(get_db)
) -> Response:
    svc = await _get_service_by_slug(slug, db)
    res = await db.execute(
        select(ServicePermission).where(
            ServicePermission.application_id == application_id,
            ServicePermission.service_id == svc.id,
        )
    )
    row = res.scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/api/v1/applications/{application_id}/permissions",
    response_model=PermissionList,
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)
async def list_application_permissions(
    application_id: int, db: AsyncSession = Depends(get_db)
) -> PermissionList:
    res = await db.execute(
        select(ServicePermission)
        .where(ServicePermission.application_id == application_id)
        .order_by(ServicePermission.id)
    )
    rows = res.scalars().all()
    items = [PermissionOut.model_validate(_serialize(r)) for r in rows]
    return PermissionList(items=items, total=len(items))


def _serialize(p: ServicePermission) -> dict:
    return {
        "id": p.id,
        "application_id": p.application_id,
        "service_id": p.service_id,
        "granted_by": p.granted_by,
        "granted_at": p.granted_at.isoformat() if p.granted_at else None,
        "note": p.note,
    }
```

> 注意：`get_current_user` 是从 deps 模块取已认证 user。如果项目里没有这个 dep，先在 `services/control_plane/src/control_plane/deps.py` 里看现有的 jwt decode dep（多半叫 `get_current_user` 或 `get_user`）。如果叫法不一样，把上面 import 改对即可。

- [ ] **Step 2.4: 在 main.py 注册路由**

修改 `services/control_plane/src/control_plane/main.py`，找到现有的 `app.include_router(...)` 块，加一行：

```python
from .routers import permissions as permissions_router
...
app.include_router(permissions_router.router)
```

- [ ] **Step 2.5: 跑测试确认全过**

```bash
cd services/control_plane && uv run pytest tests/test_permissions.py -v
```

期望：8 个 test 全部 PASS。

- [ ] **Step 2.6: 提交**

```bash
git add services/control_plane/src/control_plane/routers/permissions.py \
  services/control_plane/src/control_plane/main.py \
  services/control_plane/tests/test_permissions.py
git commit -m "feat(control-plane): service_permissions CRUD with idempotent grant"
```

---

## Task 3 · gateway PolicyCache

**Files:**
- Create: `services/gateway/src/gateway/policy.py`
- Create: `services/gateway/tests/test_policy.py`

- [ ] **Step 3.1: 写测试 `test_policy.py`**

```python
import time

import pytest
from sqlalchemy import select

from mcpsys_shared.models import Application, McpService, ServicePermission, User, UserRole
from gateway.policy import PolicyCache


@pytest.fixture
async def setup_perm(session_factory):
    async with session_factory() as s:
        admin = User(username="pa", password_hash="x", role=UserRole.admin)
        s.add(admin)
        await s.flush()
        app = Application(name="pa-app", owner_user_id=admin.id)
        s.add(app)
        svc = McpService(slug="pa-svc", display_name="P", endpoint_url="http://p/mcp")
        s.add(svc)
        await s.flush()
        s.add(ServicePermission(application_id=app.id, service_id=svc.id, granted_by=admin.id))
        await s.commit()
        await s.refresh(app)
        await s.refresh(svc)
        return app.id, svc.id


async def test_allowed(session_factory, setup_perm):
    app_id, svc_id = setup_perm
    cache = PolicyCache(session_factory=session_factory, ttl_seconds=30)
    assert await cache.is_allowed(application_id=app_id, service_id=svc_id) is True


async def test_denied_when_no_grant(session_factory, setup_perm):
    _, svc_id = setup_perm
    cache = PolicyCache(session_factory=session_factory, ttl_seconds=30)
    assert await cache.is_allowed(application_id=99999, service_id=svc_id) is False


async def test_denied_when_application_id_none(session_factory, setup_perm):
    _, svc_id = setup_perm
    cache = PolicyCache(session_factory=session_factory, ttl_seconds=30)
    assert await cache.is_allowed(application_id=None, service_id=svc_id) is False


async def test_cache_hit_avoids_db(session_factory, setup_perm, monkeypatch):
    app_id, svc_id = setup_perm
    cache = PolicyCache(session_factory=session_factory, ttl_seconds=30)
    await cache.is_allowed(application_id=app_id, service_id=svc_id)

    # Drop the row directly so DB now says "not allowed". Cache should still say allowed.
    async with session_factory() as s:
        await s.execute(
            select(ServicePermission).where(ServicePermission.service_id == svc_id)
        )
        rows = (await s.execute(select(ServicePermission))).scalars().all()
        for r in rows:
            await s.delete(r)
        await s.commit()

    assert await cache.is_allowed(application_id=app_id, service_id=svc_id) is True


async def test_cache_expires(session_factory, setup_perm):
    app_id, svc_id = setup_perm
    cache = PolicyCache(session_factory=session_factory, ttl_seconds=0)  # immediate expiry
    await cache.is_allowed(application_id=app_id, service_id=svc_id)
    # remove grant
    async with session_factory() as s:
        rows = (await s.execute(select(ServicePermission))).scalars().all()
        for r in rows:
            await s.delete(r)
        await s.commit()
    assert await cache.is_allowed(application_id=app_id, service_id=svc_id) is False


async def test_invalidate_clears_service_entry(session_factory, setup_perm):
    app_id, svc_id = setup_perm
    cache = PolicyCache(session_factory=session_factory, ttl_seconds=300)
    await cache.is_allowed(application_id=app_id, service_id=svc_id)
    cache.invalidate(service_id=svc_id)
    assert svc_id not in cache._cache  # type: ignore[attr-defined]
```

- [ ] **Step 3.2: 跑测试确认 fail**

```bash
cd services/gateway && uv run pytest tests/test_policy.py -v
```

期望：collection error，找不到 `gateway.policy`。

- [ ] **Step 3.3: 写 `policy.py`**

```python
import time
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mcpsys_shared.models import ServicePermission


@dataclass
class _Entry:
    allow_set: frozenset[int]
    expires_at: float


class PolicyCache:
    """Per-process service_id → frozenset[application_id] cache.

    On miss / expiry, reloads the *entire* allow set for one service in a single
    SELECT. Default-deny: app_id not in the set ⇒ False. application_id == None
    (user-owned key, not yet bound to an application) ⇒ always False — by V1-A
    design only application subjects are grantable."""

    def __init__(
        self, *, session_factory: async_sessionmaker[AsyncSession], ttl_seconds: int = 30
    ) -> None:
        self._sf = session_factory
        self._ttl = ttl_seconds
        self._cache: dict[int, _Entry] = {}

    def invalidate(self, *, service_id: int | None = None) -> None:
        if service_id is None:
            self._cache.clear()
        else:
            self._cache.pop(service_id, None)

    async def is_allowed(self, *, application_id: int | None, service_id: int) -> bool:
        if application_id is None:
            return False

        now = time.monotonic()
        entry = self._cache.get(service_id)
        if entry is None or entry.expires_at <= now:
            entry = await self._load(service_id, now)

        return application_id in entry.allow_set

    async def _load(self, service_id: int, now: float) -> _Entry:
        async with self._sf() as session:
            res = await session.execute(
                select(ServicePermission.application_id).where(
                    ServicePermission.service_id == service_id
                )
            )
            allow = frozenset(res.scalars().all())
        entry = _Entry(allow_set=allow, expires_at=now + self._ttl)
        self._cache[service_id] = entry
        return entry
```

- [ ] **Step 3.4: 跑测试确认全过**

```bash
cd services/gateway && uv run pytest tests/test_policy.py -v
```

期望：6 个 test PASS。

- [ ] **Step 3.5: 提交**

```bash
git add services/gateway/src/gateway/policy.py services/gateway/tests/test_policy.py
git commit -m "feat(gateway): PolicyCache for application→service whitelist with TTL"
```

---

## Task 4 · 接入 PolicyCache 到 mcp 路由

**Files:**
- Modify: `services/gateway/src/gateway/main.py`
- Modify: `services/gateway/src/gateway/routers/mcp.py`
- Modify: `services/gateway/tests/conftest.py`
- Modify: `services/gateway/tests/test_mcp_endpoint.py`（新增 403 用例）

- [ ] **Step 4.1: conftest 注入 policy fixture**

修改 `services/gateway/tests/conftest.py`，在 `app` fixture 里把 PolicyCache 注入 app.state：

```python
# 顶部 import 增加：
from gateway.policy import PolicyCache

# 在 app fixture 内、telemetry start 之前加：
fastapi_app.state.policy = PolicyCache(session_factory=session_factory, ttl_seconds=30)
```

- [ ] **Step 4.2: 写 403 测试到 `test_mcp_endpoint.py`**

参考既有用例，找到现有 fixture 创建 service + key 的样板，新增：

```python
async def test_unauthorized_application_returns_403(client, ...):
    """Issue an api key bound to application X; do NOT grant X→service.
    Hit /mcp/<slug> and expect 403 with detail."""
    # 1. create service via control_plane fixture pattern (already in conftest)
    # 2. create application + api key (no permission row)
    # 3. POST /mcp/<slug> with that key
    # 4. assert 403 + body["detail"] == "application not authorized for this service"
    # 5. assert no upstream call happened (mock not called)
```

> 实施时按 `test_mcp_endpoint.py` 现有 fixture 风格写完整测试代码——参考 `test_mcp_endpoint.py` 里其他 200 / 401 / 404 用例的样板。

- [ ] **Step 4.3: 跑测试确认 fail**

```bash
cd services/gateway && uv run pytest tests/test_mcp_endpoint.py::test_unauthorized_application_returns_403 -v
```

期望：FAIL（当前代码会 200，因为没有 permission 检查）。

- [ ] **Step 4.4: 修改 mcp.py 在 resolve 与 forward 之间插入 permission 检查**

`services/gateway/src/gateway/routers/mcp.py` 的 `proxy_mcp` 内，找到注释 `# 3. authz: MVP only checks key is active` 那一段，替换成：

```python
    # 3. authz: application → service whitelist
    policy = request.app.state.policy
    allowed = await policy.is_allowed(
        application_id=resolved_key.application_id,
        service_id=svc.service_id,
    )
    if not allowed:
        denied_entry = CallLogEntry(
            api_key_id=resolved_key.api_key_id,
            application_id=resolved_key.application_id,
            user_id=resolved_key.user_id,
            service_id=svc.service_id,
            service_version=None,
            tool_name=tool_label,
            request_id=jsonrpc_id or request_id,
            status=CallStatus.denied,    # NOTE: this enum value is added in PR2
            http_status=403,
            error_code="permission_denied",
            error_message="application not authorized",
            duration_ms=0,
            request_bytes=len(body),
            response_bytes=0,
            request_body=_truncate(body, settings.body_log_max_bytes),
            response_body=None,
            client_ip=client_ip,
        )
        await telemetry.enqueue(denied_entry)
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "application not authorized for this service"
        )
```

> ⚠️ `CallStatus.denied` 在 PR2 才扩。**PR1 测试时**直接复用 `CallStatus.error`；PR2 Task 9 同时更新 enum 和上面这行。在 PR1 里先用 `CallStatus.error` 占位并加注释，Task 9 步骤 9.5 会回头改成 `CallStatus.denied`。

实际 PR1 占位代码：

```python
            status=CallStatus.error,    # TODO(v1a-pr2): switch to CallStatus.denied once enum extends
            error_code="permission_denied",
```

- [ ] **Step 4.5: lifespan 注入 PolicyCache**

修改 `services/gateway/src/gateway/main.py` 的 `lifespan` 函数，在 resolver 创建后追加：

```python
from .policy import PolicyCache  # 顶部 import
# 在 resolver 之后：
app.state.policy = PolicyCache(
    session_factory=app.state.session_factory,
    ttl_seconds=settings.policy_cache_ttl_seconds,
)
```

并在 `services/gateway/src/gateway/settings.py` 加：

```python
policy_cache_ttl_seconds: int = 30
```

- [ ] **Step 4.6: 跑全部 gateway 测试**

```bash
cd services/gateway && uv run pytest -v
```

期望：之前所有用例 PASS + 新加的 403 用例 PASS。如果有原有 200 用例挂了（因为现在默认拒），把它们改成"先 grant permission 再调用"。

- [ ] **Step 4.7: 提交**

```bash
git add services/gateway/src/gateway/main.py \
  services/gateway/src/gateway/routers/mcp.py \
  services/gateway/src/gateway/settings.py \
  services/gateway/tests/conftest.py \
  services/gateway/tests/test_mcp_endpoint.py
git commit -m "feat(gateway): enforce application→service whitelist before forwarding"
```

---

## Task 5 · bootstrap 脚本

**Files:**
- Create: `scripts/bootstrap_permissions.py`

- [ ] **Step 5.1: 写脚本**

```python
"""Seed service_permissions with the cartesian product of (active app-owned api keys'
applications) × (active services).

This is the safe migration from MVP "any active key calls anything" to the V1-A
white-list model: after running this, behavior is unchanged. Operators then
collect down by deleting unwanted grants.

Usage:
    uv run python scripts/bootstrap_permissions.py [--dry-run]

Idempotent: re-running yields no-ops (UNIQUE constraint on (app_id, service_id)).

User-owned keys are skipped — V1-A only supports application as the grant subject."""

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mcpsys_shared.db import make_engine, make_session_factory
from mcpsys_shared.models import (
    ApiKey,
    ApiKeyOwnerType,
    McpService,
    ServicePermission,
    ServiceStatus,
)
from mcpsys_shared.settings import settings


async def main(dry_run: bool) -> int:
    engine = make_engine(settings.database_url)
    sf = make_session_factory(engine)

    async with sf() as s:
        keys = (
            (
                await s.execute(
                    select(ApiKey).where(
                        ApiKey.owner_type == ApiKeyOwnerType.application,
                        ApiKey.revoked_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        services = (
            (
                await s.execute(
                    select(McpService).where(McpService.status == ServiceStatus.active)
                )
            )
            .scalars()
            .all()
        )
        existing = (
            (
                await s.execute(
                    select(
                        ServicePermission.application_id, ServicePermission.service_id
                    )
                )
            )
            .all()
        )

        app_ids = sorted({k.owner_id for k in keys})
        existing_pairs = set(map(tuple, existing))
        to_create: list[tuple[int, int]] = []
        for app_id in app_ids:
            for svc in services:
                if (app_id, svc.id) not in existing_pairs:
                    to_create.append((app_id, svc.id))

        print(
            f"[bootstrap] active app-owned keys: {len(keys)} → {len(app_ids)} unique apps"
        )
        print(f"[bootstrap] active services: {len(services)}")
        print(f"[bootstrap] existing grants: {len(existing_pairs)}")
        print(f"[bootstrap] new grants to insert: {len(to_create)}")

        if dry_run:
            print("[bootstrap] dry run — no changes written")
            return 0

        for app_id, svc_id in to_create:
            s.add(
                ServicePermission(
                    application_id=app_id, service_id=svc_id, note="bootstrap v1a"
                )
            )

        try:
            await s.commit()
        except IntegrityError as e:
            print(f"[bootstrap] integrity error (likely concurrent run): {e}", file=sys.stderr)
            return 2

        print(f"[bootstrap] inserted {len(to_create)} grants")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(dry_run=args.dry_run)))
```

- [ ] **Step 5.2: 本地 dry-run 验证**

```bash
cd /dataspace/kqspace/MCPsys && uv run python scripts/bootstrap_permissions.py --dry-run
```

期望：打印 4 行计数，不报错。

- [ ] **Step 5.3: 提交**

```bash
git add scripts/bootstrap_permissions.py
git commit -m "feat(scripts): bootstrap_permissions.py for safe whitelist migration"
```

---

## Task 6 · Web UI · 「授权应用」面板 + 反向列表

**Files:**
- Create: `services/web/src/api/permissions.ts`
- Modify: `services/web/src/views/services/ServiceDetailPage.vue`
- Modify: `services/web/src/views/applications/ApplicationDetailPage.vue`

- [ ] **Step 6.1: 写 API 客户端 `permissions.ts`**

```typescript
import { client } from './client';

export interface Permission {
  id: number;
  application_id: number;
  service_id: number;
  granted_by: number | null;
  granted_at: string;
  note: string | null;
}

export interface PermissionList {
  items: Permission[];
  total: number;
}

export function listServicePermissions(slug: string): Promise<PermissionList> {
  return client.get(`/api/v1/services/${slug}/permissions`).then((r) => r.data);
}

export function grantPermission(
  slug: string,
  application_id: number,
  note?: string,
): Promise<Permission> {
  return client
    .post(`/api/v1/services/${slug}/permissions`, { application_id, note })
    .then((r) => r.data);
}

export function revokePermission(slug: string, application_id: number): Promise<void> {
  return client
    .delete(`/api/v1/services/${slug}/permissions/${application_id}`)
    .then(() => undefined);
}

export function listApplicationPermissions(application_id: number): Promise<PermissionList> {
  return client
    .get(`/api/v1/applications/${application_id}/permissions`)
    .then((r) => r.data);
}
```

- [ ] **Step 6.2: 在 ServiceDetailPage 加授权应用面板**

`services/web/src/views/services/ServiceDetailPage.vue` 在主信息面板下方新增一个 `<el-card>`：

```vue
<el-card class="mt-4" v-loading="permLoading">
  <template #header>
    <div class="flex justify-between items-center">
      <span>授权应用</span>
      <el-button type="primary" size="small" @click="openGrantDialog" :disabled="!canEdit">
        授权
      </el-button>
    </div>
  </template>

  <el-table :data="permissions" empty-text="暂无授权应用">
    <el-table-column prop="application_id" label="应用 ID" width="100" />
    <el-table-column label="应用名称">
      <template #default="{ row }">{{ appNameById(row.application_id) }}</template>
    </el-table-column>
    <el-table-column prop="granted_at" label="授权时间" width="200" />
    <el-table-column prop="note" label="备注" />
    <el-table-column label="操作" width="100">
      <template #default="{ row }">
        <el-button
          type="danger"
          size="small"
          link
          :disabled="!canEdit"
          @click="onRevoke(row.application_id)"
        >
          撤销
        </el-button>
      </template>
    </el-table-column>
  </el-table>
</el-card>

<el-dialog v-model="grantDialogOpen" title="授权应用调用此服务" width="480">
  <el-form :model="grantForm">
    <el-form-item label="应用">
      <el-select v-model="grantForm.application_id" filterable placeholder="选择应用">
        <el-option
          v-for="app in availableApps"
          :key="app.id"
          :label="`${app.id} · ${app.name}`"
          :value="app.id"
        />
      </el-select>
    </el-form-item>
    <el-form-item label="备注">
      <el-input v-model="grantForm.note" maxlength="200" />
    </el-form-item>
  </el-form>
  <template #footer>
    <el-button @click="grantDialogOpen = false">取消</el-button>
    <el-button type="primary" @click="onGrant" :loading="granting">确认授权</el-button>
  </template>
</el-dialog>
```

`<script setup lang="ts">` 内追加：

```typescript
import {
  listServicePermissions,
  grantPermission,
  revokePermission,
  type Permission,
} from '@/api/permissions';
import { listApplications, type Application } from '@/api/applications';
import { ElMessage, ElMessageBox } from 'element-plus';

const permissions = ref<Permission[]>([]);
const permLoading = ref(false);
const apps = ref<Application[]>([]);
const grantDialogOpen = ref(false);
const grantForm = ref<{ application_id: number | null; note: string }>({
  application_id: null,
  note: '',
});
const granting = ref(false);

const availableApps = computed(() => {
  const granted = new Set(permissions.value.map((p) => p.application_id));
  return apps.value.filter((a) => !granted.has(a.id));
});

const appNameById = (id: number) => apps.value.find((a) => a.id === id)?.name ?? '(unknown)';

async function reloadPermissions() {
  if (!service.value) return;
  permLoading.value = true;
  try {
    const list = await listServicePermissions(service.value.slug);
    permissions.value = list.items;
  } finally {
    permLoading.value = false;
  }
}

async function reloadApps() {
  const list = await listApplications();
  apps.value = list.items;
}

function openGrantDialog() {
  grantForm.value = { application_id: null, note: '' };
  grantDialogOpen.value = true;
}

async function onGrant() {
  if (!service.value || !grantForm.value.application_id) return;
  granting.value = true;
  try {
    await grantPermission(
      service.value.slug,
      grantForm.value.application_id,
      grantForm.value.note || undefined,
    );
    ElMessage.success('已授权');
    grantDialogOpen.value = false;
    await reloadPermissions();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '授权失败');
  } finally {
    granting.value = false;
  }
}

async function onRevoke(applicationId: number) {
  if (!service.value) return;
  try {
    await ElMessageBox.confirm('撤销后，该应用将立刻无法调用本服务（最长 30 秒生效）', '确认撤销', {
      type: 'warning',
    });
  } catch {
    return;
  }
  try {
    await revokePermission(service.value.slug, applicationId);
    ElMessage.success('已撤销');
    await reloadPermissions();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '撤销失败');
  }
}

// 入口（追加到现有 onMounted 内或独立 watch service）
onMounted(async () => {
  // 既有 load logic ...
  await Promise.all([reloadPermissions(), reloadApps()]);
});
```

> `canEdit`、`service` 这些已有的现成 ref 直接复用——参考文件里现有 `disableService` 按钮怎么取 `canEdit` 的。如果文件里还没有 `canEdit`，按既有 `useUserStore().role !== 'viewer'` 模式加。

- [ ] **Step 6.3: 在 ApplicationDetailPage 加「可调服务」反向列表**

如果文件存在，加一个类似的 card 展示该 app 能调的所有 service。如果没有 `ApplicationDetailPage.vue`，**跳过此步**，PR2 之前再补。

- [ ] **Step 6.4: 启动 web 自测**

```bash
cd services/web && pnpm dev
```

打开浏览器访问 service 详情页，验证：
- 授权列表正常加载
- 「授权」对话框能选 app，提交成功
- 列表立刻刷新
- 「撤销」按钮弹确认 + 调用成功 + 列表刷新

- [ ] **Step 6.5: 提交**

```bash
git add services/web/src/api/permissions.ts services/web/src/views/services/ServiceDetailPage.vue
# 如改了 ApplicationDetailPage 也加上
git commit -m "feat(web): service detail page — application permissions panel"
```

---

## Task 7 · 扩展 smoke 脚本

**Files:**
- Modify: `scripts/smoke.sh`

- [ ] **Step 7.1: 修改 smoke.sh 在「issue api key」后插入 grant，并在原 mcp 调用前/后增加 403 路径**

找到 smoke.sh 中 `[smoke] proxy through gateway` 那一段，前面加：

```bash
echo "[smoke] (negative) call before grant — expect 403"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/mcp/smoke-svc" \
    -H "Authorization: Bearer $APIKEY" -H "content-type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}')
test "$HTTP" = "403" || { echo "expected 403 got $HTTP"; exit 1; }

echo "[smoke] grant permission smoke-app → smoke-svc"
curl -fsS -X POST "$BASE/api/v1/services/smoke-svc/permissions" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d "{\"application_id\":$APP_ID}" >/dev/null
```

随后既有的 `[smoke] proxy through gateway` 才会成功。

- [ ] **Step 7.2: 跑 smoke**

```bash
cd /dataspace/kqspace/MCPsys && bash scripts/smoke.sh
```

期望：所有步骤打印 OK，最后 `[smoke] OK`。

- [ ] **Step 7.3: 提交**

```bash
git add scripts/smoke.sh
git commit -m "test(smoke): exercise 403 (no grant) and 200 (after grant) paths"
```

---

## Task 8 · PR1 收尾

- [ ] **Step 8.1: 跑全套测试 + smoke**

```bash
cd /dataspace/kqspace/MCPsys && uv run pytest services/control_plane/tests services/gateway/tests packages/mcpsys_shared/tests -v
bash scripts/smoke.sh
```

全绿才进下一步。

- [ ] **Step 8.2: 推分支 + 创建 PR**

```bash
git checkout -b feat/v1a-permissions
git push -u origin feat/v1a-permissions
gh pr create --title "feat: V1-A PR1 — service-level whitelist permissions" --body "$(cat <<'EOF'
## Summary
- 新表 service_permissions（application × service 白名单）
- control-plane CRUD：grant/list/revoke/反向查
- gateway PolicyCache（30s TTL）+ permission 强制
- bootstrap_permissions.py 用于上线时无损切换
- Web 服务详情页「授权应用」面板
- smoke.sh 覆盖 403 / 200 双路径

详见 docs/specs/2026-05-08-v1a-access-control-and-ratelimit-design.md PR1 节。

## Test plan
- [x] services/control_plane/tests/test_permissions.py 全部 PASS
- [x] services/gateway/tests 全部 PASS（含新增 403 用例）
- [x] scripts/smoke.sh 通过
- [ ] 部署测试服务器后跑 bootstrap_permissions.py --dry-run 检查输出
- [ ] 真实跑 bootstrap_permissions.py 后 smoke.sh 仍通

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

# Phase 2 (PR2) — ratelimit + 拒绝可观测

> 假设 PR1 已合入 main，此阶段在 main 之上拉 `feat/v1a-ratelimit` 分支。

## Task 9 · ratelimit schema + alembic

**Files:**
- Modify: `packages/mcpsys_shared/src/mcpsys_shared/models.py`
- Create: `services/control_plane/alembic/versions/0003_v1a_ratelimit.py`
- Modify: `services/gateway/src/gateway/routers/mcp.py`（把 PR1 的 `CallStatus.error` 占位换成 `CallStatus.denied`）

- [ ] **Step 9.1: 扩 CallStatus enum**

修改 `models.py` CallStatus：

```python
class CallStatus(str, enum.Enum):
    success = "success"
    error = "error"
    timeout = "timeout"
    denied = "denied"
    throttled = "throttled"
```

- [ ] **Step 9.2: 给 ApiKey 和 McpService 加 rate_limit_qps 列**

```python
class ApiKey(Base):
    ...
    rate_limit_qps: Mapped[int | None] = mapped_column(Integer, nullable=True)


class McpService(Base):
    ...
    rate_limit_qps: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

- [ ] **Step 9.3: 写 alembic 0003**

```python
"""v1a ratelimit + denied/throttled

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-08 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("rate_limit_qps", sa.Integer(), nullable=True))
    op.add_column("mcp_services", sa.Column("rate_limit_qps", sa.Integer(), nullable=True))
    op.execute("ALTER TYPE callstatus ADD VALUE IF NOT EXISTS 'denied'")
    op.execute("ALTER TYPE callstatus ADD VALUE IF NOT EXISTS 'throttled'")


def downgrade() -> None:
    op.drop_column("mcp_services", "rate_limit_qps")
    op.drop_column("api_keys", "rate_limit_qps")
    # NOTE: postgres does not support DROP VALUE on enums; rolling back means
    # recreating the type. Only enable if rollback is genuinely needed.
```

- [ ] **Step 9.4: 跑迁移**

```bash
cd services/control_plane && uv run alembic upgrade head
```

期望：`Running upgrade 0002 -> 0003`。

- [ ] **Step 9.5: 把 mcp.py 中 PR1 的占位改正**

`services/gateway/src/gateway/routers/mcp.py` 中找到 `# TODO(v1a-pr2): switch to CallStatus.denied`：

```python
# 改前
status=CallStatus.error,    # TODO(v1a-pr2): switch to CallStatus.denied once enum extends
# 改后
status=CallStatus.denied,
```

- [ ] **Step 9.6: 提交**

```bash
git add packages/mcpsys_shared/src/mcpsys_shared/models.py \
  services/control_plane/alembic/versions/0003_v1a_ratelimit.py \
  services/gateway/src/gateway/routers/mcp.py
git commit -m "feat(schema): rate_limit_qps + CallStatus.denied/throttled"
```

---

## Task 10 · control-plane 接受 rate_limit_qps

**Files:**
- Modify: `services/control_plane/src/control_plane/routers/services.py`
- Modify: `services/control_plane/src/control_plane/routers/api_keys.py`
- Modify: `services/control_plane/tests/test_services.py`、`test_api_keys.py`

- [ ] **Step 10.1: 扩展 services router schema**

`services/control_plane/src/control_plane/routers/services.py`：

```python
class ServiceCreate(BaseModel):
    ...
    rate_limit_qps: int | None = Field(default=None, ge=0)


class ServiceUpdate(BaseModel):
    ...
    rate_limit_qps: int | None = None  # null = NULL（不限）；不传 = 不动；0 = 全拒


class ServiceOut(BaseModel):
    ...
    rate_limit_qps: int | None
```

`create_service` 内 `McpService(...)` 添加 `rate_limit_qps=payload.rate_limit_qps`。
`update_service` 现有 `data = payload.model_dump(exclude_unset=True)` 已经能处理 PATCH 三态（`exclude_unset=True` 让"未传"和"传 null"区分开）。

- [ ] **Step 10.2: 扩展 api-keys router schema**

`services/control_plane/src/control_plane/routers/api_keys.py` 同样加 `rate_limit_qps` 字段（POST 和 PATCH，如果有 PATCH）。

- [ ] **Step 10.3: 写测试**

`test_services.py` 追加：

```python
async def test_create_service_with_qps(client, admin):
    resp = await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={
            "slug": "qps-svc",
            "display_name": "Q",
            "endpoint_url": "http://q/mcp",
            "rate_limit_qps": 5,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["rate_limit_qps"] == 5


async def test_patch_qps_to_null_clears(client, admin):
    await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={"slug": "qps-clear", "display_name": "Q", "endpoint_url": "http://q/mcp", "rate_limit_qps": 5},
    )
    resp = await client.patch(
        "/api/v1/services/qps-clear",
        headers=auth_header(admin),
        json={"rate_limit_qps": None},
    )
    assert resp.status_code == 200
    assert resp.json()["rate_limit_qps"] is None
```

- [ ] **Step 10.4: 跑测试**

```bash
cd services/control_plane && uv run pytest tests -v
```

全绿。

- [ ] **Step 10.5: 提交**

```bash
git add services/control_plane/src/control_plane/routers/services.py \
  services/control_plane/src/control_plane/routers/api_keys.py \
  services/control_plane/tests/test_services.py \
  services/control_plane/tests/test_api_keys.py
git commit -m "feat(control-plane): accept rate_limit_qps on services and api-keys"
```

---

## Task 11 · gateway TokenBucket（redis Lua）

**Files:**
- Create: `services/gateway/src/gateway/ratelimit.py`
- Create: `services/gateway/tests/test_ratelimit.py`

- [ ] **Step 11.1: 写测试**

```python
import asyncio

import pytest


async def test_check_passes_when_qps_none(redis_client):
    from gateway.ratelimit import TokenBucket

    bucket = TokenBucket(redis_client)
    res = await bucket.check("rl:test", qps=None)
    assert res.allowed is True
    assert res.retry_after_s == 0


async def test_check_passes_first_request(redis_client):
    from gateway.ratelimit import TokenBucket

    bucket = TokenBucket(redis_client)
    res = await bucket.check("rl:t1", qps=2)
    assert res.allowed is True


async def test_burst_allows_2x_then_blocks(redis_client):
    from gateway.ratelimit import TokenBucket

    bucket = TokenBucket(redis_client)
    # qps=1 → burst=2, so 2 immediate requests pass, 3rd fails
    r1 = await bucket.check("rl:burst", qps=1)
    r2 = await bucket.check("rl:burst", qps=1)
    r3 = await bucket.check("rl:burst", qps=1)
    assert r1.allowed and r2.allowed
    assert not r3.allowed
    assert r3.retry_after_s >= 1


async def test_qps_zero_always_blocks(redis_client):
    from gateway.ratelimit import TokenBucket

    bucket = TokenBucket(redis_client)
    res = await bucket.check("rl:zero", qps=0)
    assert res.allowed is False
    assert res.retry_after_s == 0  # no meaningful retry


async def test_redis_failure_fails_open(monkeypatch):
    from gateway.ratelimit import TokenBucket

    class BrokenRedis:
        async def eval(self, *a, **kw):
            raise ConnectionError("boom")

    bucket = TokenBucket(BrokenRedis())
    res = await bucket.check("rl:broken", qps=1)
    assert res.allowed is True  # fail-open
    assert res.retry_after_s == 0


async def test_refill_after_wait(redis_client):
    from gateway.ratelimit import TokenBucket

    bucket = TokenBucket(redis_client)
    # qps=10 → refill 1 token every 100ms
    for _ in range(20):  # exhaust burst (=20)
        await bucket.check("rl:refill", qps=10)
    blocked = await bucket.check("rl:refill", qps=10)
    assert not blocked.allowed
    await asyncio.sleep(0.25)
    refilled = await bucket.check("rl:refill", qps=10)
    assert refilled.allowed
```

并在 `services/gateway/tests/conftest.py` 的 `redis_url` 之后追加：

```python
@pytest.fixture
async def redis_client(redis_url):
    from redis.asyncio import Redis
    r = Redis.from_url(redis_url, decode_responses=True)
    await r.flushdb()
    yield r
    await r.aclose()
```

- [ ] **Step 11.2: 跑测试确认 fail**

```bash
cd services/gateway && uv run pytest tests/test_ratelimit.py -v
```

期望：collection error。

- [ ] **Step 11.3: 写 `ratelimit.py`**

```python
import logging
import math
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


_LUA = """
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
redis.call('PEXPIRE', KEYS[1], 60000)
return {allowed, tostring(tokens)}
"""


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: float
    retry_after_s: int


class TokenBucket:
    """Redis Lua-backed token bucket. burst = 2 × qps."""

    def __init__(self, redis) -> None:
        self._redis = redis

    async def check(self, key: str, *, qps: int | None) -> RateLimitResult:
        if qps is None:
            return RateLimitResult(allowed=True, remaining=float("inf"), retry_after_s=0)
        if qps == 0:
            return RateLimitResult(allowed=False, remaining=0.0, retry_after_s=0)

        burst = qps * 2
        now_ms = int(time.time() * 1000)
        try:
            res = await self._redis.eval(_LUA, 1, key, str(now_ms), str(qps), str(burst))
        except Exception as e:  # redis down / lua failure → fail-open
            logger.warning("ratelimit eval failed, fail-open: %s", e)
            return RateLimitResult(allowed=True, remaining=float("inf"), retry_after_s=0)

        allowed_int, remaining_str = res
        remaining = float(remaining_str)
        allowed = bool(int(allowed_int))
        retry_after_s = 0 if allowed else max(1, math.ceil((1 - remaining) / qps))
        return RateLimitResult(allowed=allowed, remaining=remaining, retry_after_s=retry_after_s)
```

- [ ] **Step 11.4: 跑测试确认全过**

```bash
cd services/gateway && uv run pytest tests/test_ratelimit.py -v
```

期望：6 个 test PASS。

- [ ] **Step 11.5: 提交**

```bash
git add services/gateway/src/gateway/ratelimit.py services/gateway/tests/test_ratelimit.py services/gateway/tests/conftest.py
git commit -m "feat(gateway): redis-lua TokenBucket with burst=2x and fail-open"
```

---

## Task 12 · 接入 ratelimit 到 mcp 路由 + 拒绝日志

**Files:**
- Modify: `services/gateway/src/gateway/main.py`
- Modify: `services/gateway/src/gateway/routers/mcp.py`
- Modify: `services/gateway/tests/conftest.py`
- Modify: `services/gateway/tests/test_mcp_endpoint.py`

- [ ] **Step 12.1: lifespan 注入 TokenBucket**

`services/gateway/src/gateway/main.py` 在 redis 初始化后追加：

```python
from .ratelimit import TokenBucket
...
app.state.ratelimit = TokenBucket(app.state.redis)
```

conftest 同步注入：`fastapi_app.state.ratelimit = TokenBucket(fastapi_app.state.redis)`。

- [ ] **Step 12.2: 写 429 测试到 `test_mcp_endpoint.py`**

测试需要复用现有 `test_mcp_endpoint.py` 的 `_seed_service_and_key` 风格。在文件里加 helper（如果还没有）：

```python
import asyncio

import pytest
from sqlalchemy import select

from mcpsys_shared.models import (
    ApiKey, ApiKeyOwnerType, Application, CallLog, CallStatus,
    McpService, ServicePermission, User, UserRole,
)
# 既有 mcp endpoint test 已经有 mocked upstream / build_key etc.
# 假设有 build_authed_app_and_key(session_factory, *, qps_service=None, qps_key=None) helper
# 参考 conftest 现有 service-creating fixture。如果没有就把下面 setup 内联。


async def _setup(session_factory, *, qps_service=None, qps_key=None):
    async with session_factory() as s:
        admin = User(username=f"u-{qps_service}-{qps_key}", password_hash="x", role=UserRole.admin)
        s.add(admin)
        await s.flush()
        app = Application(name=f"a-{admin.id}", owner_user_id=admin.id)
        s.add(app)
        svc = McpService(
            slug=f"svc-{admin.id}", display_name="x",
            endpoint_url="http://upstream/mcp", rate_limit_qps=qps_service,
        )
        s.add(svc)
        await s.flush()
        s.add(ServicePermission(application_id=app.id, service_id=svc.id, granted_by=admin.id))
        # api key:
        from control_plane.routers.api_keys import _hash_key  # or whatever the project uses
        plaintext = "mcpk_testing_xxxxxxxxxxxxxxxxxxxxxxxxxx"
        key = ApiKey(
            key_prefix=plaintext[5:13],
            key_hash=_hash_key(plaintext),  # bcrypt hash
            owner_type=ApiKeyOwnerType.application,
            owner_id=app.id,
            name="t",
            rate_limit_qps=qps_key,
        )
        s.add(key)
        await s.commit()
        return svc.slug, plaintext


async def test_service_qps_throttles(client, session_factory, mocked_upstream):
    slug, key = await _setup(session_factory, qps_service=1)

    async def call():
        return await client.post(
            f"/mcp/{slug}",
            headers={"Authorization": f"Bearer {key}"},
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        )

    r1, r2, r3 = await call(), await call(), await call()
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert r3.headers.get("Retry-After")
    assert r3.json()["detail"] == "service rate limit exceeded"

    # call_logs has at least one throttled row
    async with session_factory() as s:
        await asyncio.sleep(0.2)  # wait for telemetry batch flush
        rows = (
            await s.execute(select(CallLog).where(CallLog.status == CallStatus.throttled))
        ).scalars().all()
        assert len(rows) >= 1


async def test_key_qps_throttles(client, session_factory, mocked_upstream):
    slug, key = await _setup(session_factory, qps_key=1)
    headers = {"Authorization": f"Bearer {key}"}
    body = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

    r1 = await client.post(f"/mcp/{slug}", headers=headers, json=body)
    r2 = await client.post(f"/mcp/{slug}", headers=headers, json=body)
    r3 = await client.post(f"/mcp/{slug}", headers=headers, json=body)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r3.status_code == 429
    assert r3.json()["detail"] == "key rate limit exceeded"


async def test_qps_zero_blocks_all(client, session_factory, mocked_upstream):
    slug, key = await _setup(session_factory, qps_service=0)
    r = await client.post(
        f"/mcp/{slug}",
        headers={"Authorization": f"Bearer {key}"},
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
    )
    assert r.status_code == 429
    assert r.headers.get("Retry-After") is None  # qps==0 has no meaningful retry
```

> `mocked_upstream` 是既有 fixture（参考 `test_mcp_endpoint.py` 看叫什么、用 respx 还是 httpx mock）；`_hash_key` 用项目里 api_keys.py 里实际的哈希函数（一般是 bcrypt）。如果 helper 名称不同，跟着仓库现状改。

- [ ] **Step 12.3: 跑测试确认 fail**

```bash
cd services/gateway && uv run pytest tests/test_mcp_endpoint.py::test_service_qps_throttles -v
```

期望：FAIL。

- [ ] **Step 12.4: 在 mcp.py 接入双桶检查**

在 `# 3. authz` permission 检查通过之后、`# 4. forward` 之前插入：

```python
    # 3.5 ratelimit: key bucket then service bucket
    ratelimit = request.app.state.ratelimit

    rl_key = await ratelimit.check(
        f"rl:k:{resolved_key.api_key_id}", qps=resolved_key.rate_limit_qps
    )
    if not rl_key.allowed:
        await _write_throttled(
            telemetry, resolved_key, svc, body, tool_label, jsonrpc_id, request_id, client_ip
        )
        headers = {"Retry-After": str(rl_key.retry_after_s)} if rl_key.retry_after_s > 0 else {}
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "key rate limit exceeded", headers=headers
        )

    rl_svc = await ratelimit.check(f"rl:s:{svc.service_id}", qps=svc.rate_limit_qps)
    if not rl_svc.allowed:
        await _write_throttled(
            telemetry, resolved_key, svc, body, tool_label, jsonrpc_id, request_id, client_ip
        )
        headers = {"Retry-After": str(rl_svc.retry_after_s)} if rl_svc.retry_after_s > 0 else {}
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "service rate limit exceeded", headers=headers
        )
```

helper 在文件末尾：

```python
async def _write_throttled(
    telemetry, resolved_key, svc, body, tool_label, jsonrpc_id, request_id, client_ip
) -> None:
    entry = CallLogEntry(
        api_key_id=resolved_key.api_key_id,
        application_id=resolved_key.application_id,
        user_id=resolved_key.user_id,
        service_id=svc.service_id,
        service_version=None,
        tool_name=tool_label,
        request_id=jsonrpc_id or request_id,
        status=CallStatus.throttled,
        http_status=429,
        error_code="rate_limit_exceeded",
        error_message=None,
        duration_ms=0,
        request_bytes=len(body),
        response_bytes=0,
        request_body=_truncate(body, settings.body_log_max_bytes),
        response_body=None,
        client_ip=client_ip,
    )
    await telemetry.enqueue(entry)
```

> `resolved_key.rate_limit_qps` 和 `svc.rate_limit_qps` 需要在它们各自的 dataclass 上加字段，并在 `auth.py` / `resolver.py` 里把列读出来。具体：
> - `gateway/auth.py`：`ResolvedKey` 加 `rate_limit_qps: int | None = None`，从 `matched.rate_limit_qps` 读出来塞进缓存 payload，命中 cache 时也读回来。
> - `gateway/resolver.py`：`ResolvedService` 加 `rate_limit_qps: int | None = None`，`resolve()` 内填进去。

- [ ] **Step 12.5: 同步更新 ResolvedKey / ResolvedService 类**

按上面注释完成。注意 `auth.py` 缓存 payload 字段加 `"rate_limit_qps": matched.rate_limit_qps`。

- [ ] **Step 12.6: 跑测试**

```bash
cd services/gateway && uv run pytest -v
```

预期：所有用例 PASS。

- [ ] **Step 12.7: 提交**

```bash
git add services/gateway/src/gateway/main.py \
  services/gateway/src/gateway/routers/mcp.py \
  services/gateway/src/gateway/auth.py \
  services/gateway/src/gateway/resolver.py \
  services/gateway/tests/conftest.py \
  services/gateway/tests/test_mcp_endpoint.py
git commit -m "feat(gateway): per-key + per-service token bucket with throttled logging"
```

---

## Task 13 · Web · service / api-key 表单 QPS 字段

**Files:**
- Modify: `services/web/src/api/services.ts`
- Modify: `services/web/src/api/api-keys.ts`
- Modify: `services/web/src/views/services/ServiceDetailPage.vue` 和 `ServiceListPage.vue`（如有创建对话框）
- Modify: `services/web/src/views/api-keys/ApiKeyListPage.vue`（创建对话框）

- [ ] **Step 13.1: types**

`services.ts` 内：

```typescript
export interface McpService {
  ...
  rate_limit_qps: number | null;
}

export interface CreateServicePayload {
  ...
  rate_limit_qps?: number | null;
}

export interface UpdateServicePayload {
  endpoint_url?: string;
  status?: ServiceStatus;
  rate_limit_qps?: number | null;
}

export function updateService(slug: string, payload: UpdateServicePayload): Promise<McpService> {
  return client.patch(`/api/v1/services/${slug}`, payload).then((r) => r.data);
}
```

api-keys.ts 同理加 `rate_limit_qps`。

- [ ] **Step 13.2: ServiceDetailPage 加可编辑 QPS 输入框**

主信息面板内追加一行：

```vue
<el-form-item label="QPS 限流">
  <el-input-number
    v-model="qpsDraft"
    :min="0"
    :step="1"
    :placeholder="qpsDraft === null ? '不限' : ''"
    style="width: 200px"
  />
  <el-button type="primary" size="small" class="ml-2" @click="onSaveQps" :loading="savingQps">
    保存
  </el-button>
  <el-button size="small" link @click="qpsDraft = null">不限</el-button>
  <span class="ml-2 text-gray-500 text-sm">0 = 完全停用；空 = 不限</span>
</el-form-item>
```

`<script setup>` 加：

```typescript
const qpsDraft = ref<number | null>(service.value?.rate_limit_qps ?? null);
const savingQps = ref(false);

watch(service, (s) => {
  if (s) qpsDraft.value = s.rate_limit_qps;
});

async function onSaveQps() {
  if (!service.value) return;
  savingQps.value = true;
  try {
    await updateService(service.value.slug, { rate_limit_qps: qpsDraft.value });
    ElMessage.success('已保存');
    await reloadService();  // 既有的刷新函数
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败');
  } finally {
    savingQps.value = false;
  }
}
```

- [ ] **Step 13.3: ApiKey 创建对话框加 QPS 字段**

ApiKey 详情/列表页的创建表单加 `rate_limit_qps` 数字输入。同样写 0/null/正整数提示。

- [ ] **Step 13.4: 启动 web 自测**

```bash
cd services/web && pnpm dev
```

UI 验证：
- 服务详情页可看到/编辑 QPS
- 设为 1 后短时间内连续调用第 3 次返 429（结合 PR2 后端）
- 设为 0 后任何调用立刻 429
- 设回 "不限"（点链接清空）后调用恢复

- [ ] **Step 13.5: 提交**

```bash
git add services/web/src/api/services.ts services/web/src/api/api-keys.ts services/web/src/views/services services/web/src/views/api-keys
git commit -m "feat(web): rate_limit_qps editor on service and api-key forms"
```

---

## Task 14 · Web · 调用日志状态筛选扩展

**Files:**
- Modify: `services/web/src/api/call-logs.ts` 或 types
- Modify: `services/web/src/views/call-logs/CallLogsPage.vue`

- [ ] **Step 14.1: 把 CallStatus 类型加上 denied / throttled**

```typescript
export type CallStatus = 'success' | 'error' | 'timeout' | 'denied' | 'throttled';
```

- [ ] **Step 14.2: 状态下拉 / tag 渲染补 denied 红、throttled 橙**

CallLogsPage 内的 `el-select` filter options 增加两个值；`<el-tag>` 颜色映射加分支。

- [ ] **Step 14.3: 启动 web 自测**

筛选 denied 看到的就是被白名单挡住的请求，throttled 看到的是被限流挡住的请求。

- [ ] **Step 14.4: 提交**

```bash
git add services/web/src/api services/web/src/views/call-logs
git commit -m "feat(web): call-logs filter and tag for denied/throttled"
```

---

## Task 15 · 扩展 smoke.sh 加 429 路径

**Files:**
- Modify: `scripts/smoke.sh`

- [ ] **Step 15.1: 在原 [smoke] proxy through gateway 之后追加**

```bash
echo "[smoke] set service rate_limit_qps=1"
curl -fsS -X PATCH "$BASE/api/v1/services/smoke-svc" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"rate_limit_qps":1}' >/dev/null

echo "[smoke] burst 3 — expect at least one 429"
SUCC=0; THR=0
for i in 1 2 3; do
    H=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/mcp/smoke-svc" \
        -H "Authorization: Bearer $APIKEY" -H "content-type: application/json" \
        -d '{"jsonrpc":"2.0","method":"tools/list","id":'$i'}')
    case $H in
        200) SUCC=$((SUCC+1));;
        429) THR=$((THR+1));;
        *) echo "unexpected $H"; exit 1;;
    esac
done
echo "200=$SUCC 429=$THR"
test "$THR" -ge 1 || { echo "expected at least 1 throttled"; exit 1; }

echo "[smoke] reset rate_limit_qps to null"
curl -fsS -X PATCH "$BASE/api/v1/services/smoke-svc" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"rate_limit_qps":null}' >/dev/null
```

- [ ] **Step 15.2: 跑 smoke**

```bash
bash scripts/smoke.sh
```

全绿。

- [ ] **Step 15.3: 提交**

```bash
git add scripts/smoke.sh
git commit -m "test(smoke): exercise 429 ratelimit path"
```

---

## Task 16 · PR2 收尾

- [ ] **Step 16.1: 跑全套测试 + smoke**

```bash
cd /dataspace/kqspace/MCPsys && uv run pytest services/control_plane/tests services/gateway/tests packages/mcpsys_shared/tests -v
bash scripts/smoke.sh
```

- [ ] **Step 16.2: 推分支 + 创建 PR**

```bash
git push -u origin feat/v1a-ratelimit
gh pr create --title "feat: V1-A PR2 — ratelimit + denied/throttled visibility" --body "$(cat <<'EOF'
## Summary
- ApiKey/McpService 加 rate_limit_qps 列；CallStatus 加 denied/throttled
- gateway TokenBucket（redis Lua, burst=2x）双桶检查
- 拒绝事件入 call_logs（denied / throttled），可过滤
- control-plane services/api-keys 接受 rate_limit_qps（PATCH 三态）
- Web 服务/api-key 表单 QPS 字段；call-logs 筛选 denied/throttled
- smoke.sh 覆盖 429 burst 路径

详见 docs/specs/2026-05-08-v1a-access-control-and-ratelimit-design.md PR2 节。

## Test plan
- [x] services/gateway/tests 全过（含 throttled / fail-open / qps=0）
- [x] services/control_plane/tests 全过
- [x] scripts/smoke.sh 通过（含 429 路径）
- [ ] 部署测试：set service qps=5，agent 高频调用看 grafana 是否能区分 success / throttled

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

# 实施完成验收

执行 PR1+PR2 都合入 main 后，跑：

```bash
cd /dataspace/kqspace/MCPsys
uv run alembic -c services/control_plane/alembic.ini upgrade head
uv run python scripts/bootstrap_permissions.py --dry-run
uv run python scripts/bootstrap_permissions.py   # 真跑
bash scripts/smoke.sh
```

四个步骤都成功 = V1-A 上线就绪。
