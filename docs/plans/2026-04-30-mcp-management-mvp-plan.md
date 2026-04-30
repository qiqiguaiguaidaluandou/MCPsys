# MCP 管理系统 MVP 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付 MCP 服务管理系统的 MVP —— 用户登录、服务注册、API Key 管理、统一网关代理（Streamable HTTP）、调用日志采集与查询、Grafana 仪表盘、Docker Compose 一键部署。

**Architecture:** Monorepo + uv workspace 管理；Gateway 与 Control Plane 双 FastAPI 服务，共享 `mcpsys_shared` 包（含 ORM 模型、数据库会话、Settings 基类）；Postgres 存元数据与调用日志（按月分区）、Redis 做 API Key 缓存与失效通知；Grafana 直连 Postgres 渲染监控；Nginx 做反向代理与 TLS 终结。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.x async / asyncpg / Alembic / Pydantic v2 / httpx / redis-py async / bcrypt / PyJWT / cryptography(Fernet) / pytest + pytest-asyncio + testcontainers / Docker Compose v2 / Postgres 16 / Redis 7 / Grafana 10 / Nginx

**Spec 来源:** `docs/specs/2026-04-30-mcp-management-system-design.md`（§6 MVP 范围）

**预估周期:** 4–6 周（按本计划 22 个任务串行执行）

---

## 文件结构总览

实施完成后的仓库结构：

```
MCPsys/
├── compose.yaml                            # 顶层 Docker Compose
├── .env.example                            # 环境变量模板
├── README.md                               # 启动与开发说明
├── pyproject.toml                          # uv workspace 根
├── uv.lock
├── nginx/
│   └── nginx.conf                          # 反向代理：/mcp/* → gateway，其余 → control-plane
├── grafana/
│   └── provisioning/
│       ├── datasources/postgres.yaml
│       └── dashboards/
│           ├── dashboards.yaml
│           └── mcp-overview.json
├── packages/
│   └── mcpsys_shared/                      # 共享包：模型/会话/Settings 基类
│       ├── pyproject.toml
│       ├── src/mcpsys_shared/
│       │   ├── __init__.py
│       │   ├── settings.py                 # pydantic-settings 基类
│       │   ├── db.py                       # async engine + sessionmaker
│       │   └── models.py                   # 全部 SQLAlchemy 模型
│       └── tests/
│           └── test_models_smoke.py
├── services/
│   ├── control_plane/                      # 管理后台 API
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   ├── alembic.ini
│   │   ├── alembic/
│   │   │   ├── env.py
│   │   │   └── versions/
│   │   ├── src/control_plane/
│   │   │   ├── __init__.py
│   │   │   ├── main.py                     # FastAPI app + lifespan
│   │   │   ├── settings.py
│   │   │   ├── deps.py                     # FastAPI dependencies (DB, current user)
│   │   │   ├── security.py                 # JWT + bcrypt + API key gen
│   │   │   └── routers/
│   │   │       ├── __init__.py
│   │   │       ├── auth.py                 # /auth/login
│   │   │       ├── users.py                # /users
│   │   │       ├── applications.py         # /applications
│   │   │       ├── services.py             # /services (含版本)
│   │   │       ├── api_keys.py             # /api-keys
│   │   │       └── call_logs.py            # /call-logs (查询)
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── test_auth.py
│   │       ├── test_users.py
│   │       ├── test_applications.py
│   │       ├── test_services.py
│   │       ├── test_api_keys.py
│   │       └── test_call_logs.py
│   └── gateway/                            # MCP 流量网关
│       ├── pyproject.toml
│       ├── Dockerfile
│       ├── src/gateway/
│       │   ├── __init__.py
│       │   ├── main.py
│       │   ├── settings.py
│       │   ├── auth.py                     # API Key 校验 + Redis 缓存
│       │   ├── resolver.py                 # service slug → endpoint URL
│       │   ├── proxy.py                    # httpx 流式转发
│       │   ├── telemetry.py                # 内存队列 + 批量写 call_logs
│       │   └── routers/
│       │       └── mcp.py                  # POST /mcp/{slug}
│       └── tests/
│           ├── conftest.py
│           ├── test_auth.py
│           ├── test_resolver.py
│           ├── test_proxy.py
│           └── test_telemetry.py
└── docs/
    ├── specs/2026-04-30-mcp-management-system-design.md
    └── plans/2026-04-30-mcp-management-mvp-plan.md   ← 本文件
```

**前端**不在本 MVP 实施计划范围（前端框架待 §10 定）。所有管理 API 通过 OpenAPI（FastAPI 自动生成）暴露，前端团队可独立开发。

---

## 阶段一：基础设施与数据层（T1–T4）

### Task 1: 初始化 monorepo 与 uv workspace

**Files:**
- Create: `/dataspace/kqspace/MCPsys/pyproject.toml`
- Create: `/dataspace/kqspace/MCPsys/.gitignore`
- Create: `/dataspace/kqspace/MCPsys/.python-version`
- Create: `/dataspace/kqspace/MCPsys/README.md`
- Create: `/dataspace/kqspace/MCPsys/packages/mcpsys_shared/pyproject.toml`
- Create: `/dataspace/kqspace/MCPsys/packages/mcpsys_shared/src/mcpsys_shared/__init__.py`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/pyproject.toml`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/__init__.py`
- Create: `/dataspace/kqspace/MCPsys/services/gateway/pyproject.toml`
- Create: `/dataspace/kqspace/MCPsys/services/gateway/src/gateway/__init__.py`

- [ ] **Step 1: 创建仓库根 `pyproject.toml`（uv workspace）**

```toml
# /dataspace/kqspace/MCPsys/pyproject.toml
[project]
name = "mcpsys"
version = "0.1.0"
description = "Internal MCP service management system"
requires-python = ">=3.12"

[tool.uv.workspace]
members = ["packages/*", "services/*"]

[tool.uv.sources]
mcpsys-shared = { workspace = true }

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "ASYNC", "S"]
ignore = ["S101"]  # allow assert in tests

[tool.pytest.ini_options]
asyncio_mode = "auto"
addopts = "-ra -q"
```

- [ ] **Step 2: 创建 `.python-version` 与 `.gitignore`**

```
# /dataspace/kqspace/MCPsys/.python-version
3.12
```

```gitignore
# /dataspace/kqspace/MCPsys/.gitignore
__pycache__/
*.pyc
.venv/
.env
.env.local
*.db
*.sqlite
.coverage
.pytest_cache/
.ruff_cache/
.mypy_cache/
dist/
build/
*.egg-info/
.idea/
.vscode/
postgres-data/
redis-data/
grafana-data/
```

- [ ] **Step 3: 创建 `mcpsys_shared` 包元数据**

```toml
# /dataspace/kqspace/MCPsys/packages/mcpsys_shared/pyproject.toml
[project]
name = "mcpsys-shared"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncpg>=0.29",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/mcpsys_shared"]
```

```python
# /dataspace/kqspace/MCPsys/packages/mcpsys_shared/src/mcpsys_shared/__init__.py
__version__ = "0.1.0"
```

- [ ] **Step 4: 创建 `control_plane` 服务元数据**

```toml
# /dataspace/kqspace/MCPsys/services/control_plane/pyproject.toml
[project]
name = "control-plane"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "mcpsys-shared",
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "alembic>=1.13",
    "bcrypt>=4.1",
    "pyjwt>=2.8",
    "cryptography>=42",
    "redis>=5.0",
    "apscheduler>=3.10",
    "httpx>=0.27",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "testcontainers[postgres,redis]>=4.5",
    "httpx>=0.27",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/control_plane"]
```

```python
# /dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/__init__.py
__version__ = "0.1.0"
```

- [ ] **Step 5: 创建 `gateway` 服务元数据**

```toml
# /dataspace/kqspace/MCPsys/services/gateway/pyproject.toml
[project]
name = "gateway"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "mcpsys-shared",
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",
    "redis>=5.0",
    "bcrypt>=4.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "testcontainers[postgres,redis]>=4.5",
    "respx>=0.21",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/gateway"]
```

```python
# /dataspace/kqspace/MCPsys/services/gateway/src/gateway/__init__.py
__version__ = "0.1.0"
```

- [ ] **Step 6: 写顶层 README 占位**

```markdown
# MCPsys

Internal MCP (Model Context Protocol) service management system.

See `docs/specs/` for design and `docs/plans/` for implementation plans.

## Quick start

```bash
cp .env.example .env
docker compose up -d
```

Open http://localhost for the admin UI (after frontend is built).
```

- [ ] **Step 7: 安装依赖并验证 workspace 解析**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv sync
```
Expected: `Resolved N packages in ...` 且生成 `.venv/` 与 `uv.lock`。

- [ ] **Step 8: 初始化 git 并提交**

Run:
```bash
cd /dataspace/kqspace/MCPsys && git init && git add . && git commit -m "chore: initialize monorepo with uv workspace"
```

---

### Task 2: 配置 Postgres + Redis 的 Docker Compose（开发环境）

**Files:**
- Create: `/dataspace/kqspace/MCPsys/compose.yaml`
- Create: `/dataspace/kqspace/MCPsys/.env.example`

- [ ] **Step 1: 创建 `.env.example`**

```dotenv
# /dataspace/kqspace/MCPsys/.env.example
# Postgres
POSTGRES_USER=mcpsys
POSTGRES_PASSWORD=changeme_in_prod
POSTGRES_DB=mcpsys
POSTGRES_PORT=5432

# Redis
REDIS_PORT=6379

# Control plane
CONTROL_PLANE_PORT=8000
JWT_SECRET=replace_with_long_random_string_in_prod
JWT_EXPIRES_MINUTES=60
CONFIG_FERNET_KEY=replace_with_fernet_key_base64

# Gateway
GATEWAY_PORT=8080
GATEWAY_REPLICAS=2

# Grafana
GRAFANA_PORT=3000
GRAFANA_ADMIN_PASSWORD=admin

# Logging
LOG_LEVEL=INFO
```

- [ ] **Step 2: 创建初版 `compose.yaml`（仅 postgres + redis，应用容器后续任务加入）**

```yaml
# /dataspace/kqspace/MCPsys/compose.yaml
name: mcpsys

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "${POSTGRES_PORT}:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "${POSTGRES_USER}", "-d", "${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    ports:
      - "${REDIS_PORT}:6379"
    volumes:
      - redis-data:/data
    command: ["redis-server", "--appendonly", "yes"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  postgres-data:
  redis-data:
```

- [ ] **Step 3: 复制 `.env` 并启动**

Run:
```bash
cd /dataspace/kqspace/MCPsys && cp .env.example .env && docker compose up -d postgres redis
```
Expected: `Container mcpsys-postgres-1  Healthy` 与 `Container mcpsys-redis-1  Healthy`（约 10s 内）。

- [ ] **Step 4: 验证连通性**

Run:
```bash
docker compose exec postgres pg_isready -U mcpsys && docker compose exec redis redis-cli ping
```
Expected: `accepting connections` 和 `PONG`。

- [ ] **Step 5: 提交**

```bash
git add compose.yaml .env.example && git commit -m "feat: add postgres and redis to compose"
```

---

### Task 3: 定义共享 SQLAlchemy 模型与数据库会话工厂

**Files:**
- Create: `/dataspace/kqspace/MCPsys/packages/mcpsys_shared/src/mcpsys_shared/settings.py`
- Create: `/dataspace/kqspace/MCPsys/packages/mcpsys_shared/src/mcpsys_shared/db.py`
- Create: `/dataspace/kqspace/MCPsys/packages/mcpsys_shared/src/mcpsys_shared/models.py`
- Create: `/dataspace/kqspace/MCPsys/packages/mcpsys_shared/tests/__init__.py`
- Create: `/dataspace/kqspace/MCPsys/packages/mcpsys_shared/tests/test_models_smoke.py`
- Create: `/dataspace/kqspace/MCPsys/packages/mcpsys_shared/tests/conftest.py`

- [ ] **Step 1: 写 Settings 基类**

```python
# /dataspace/kqspace/MCPsys/packages/mcpsys_shared/src/mcpsys_shared/settings.py
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SharedSettings(BaseSettings):
    """Shared settings consumed by both control_plane and gateway."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = Field(default="mcpsys")
    postgres_password: str = Field(default="changeme")
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="mcpsys")

    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)

    log_level: str = Field(default="INFO")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"
```

- [ ] **Step 2: 写 DB 会话工厂**

```python
# /dataspace/kqspace/MCPsys/packages/mcpsys_shared/src/mcpsys_shared/db.py
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_engine(database_url: str, echo: bool = False) -> AsyncEngine:
    return create_async_engine(database_url, echo=echo, pool_pre_ping=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

- [ ] **Step 3: 写所有 ORM 模型**

```python
# /dataspace/kqspace/MCPsys/packages/mcpsys_shared/src/mcpsys_shared/models.py
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# --- enums ---


class UserRole(str, enum.Enum):
    admin = "admin"
    operator = "operator"
    viewer = "viewer"


class UserStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"


class ApiKeyOwnerType(str, enum.Enum):
    user = "user"
    application = "application"


class ServiceStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"


class HealthStatus(str, enum.Enum):
    healthy = "healthy"
    unhealthy = "unhealthy"
    unknown = "unknown"


class TransportType(str, enum.Enum):
    streamable_http = "streamable_http"


class CallStatus(str, enum.Enum):
    success = "success"
    error = "error"
    timeout = "timeout"


# --- tables ---


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.viewer)
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.active)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    team: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_type: Mapped[ApiKeyOwnerType] = mapped_column(Enum(ApiKeyOwnerType), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scopes: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class McpService(Base):
    __tablename__ = "mcp_services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_team: Mapped[str | None] = mapped_column(String(128))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    endpoint_url: Mapped[str] = mapped_column(String(512), nullable=False)
    transport: Mapped[TransportType] = mapped_column(
        Enum(TransportType), default=TransportType.streamable_http
    )
    status: Mapped[ServiceStatus] = mapped_column(
        Enum(ServiceStatus), default=ServiceStatus.active
    )
    health_status: Mapped[HealthStatus] = mapped_column(
        Enum(HealthStatus), default=HealthStatus.unknown
    )
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class McpServiceVersion(Base):
    __tablename__ = "mcp_service_versions"
    __table_args__ = (UniqueConstraint("service_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("mcp_services.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(512), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class CallLog(Base):
    """Per-request log written by the gateway. Body fields are nulled after 30 days."""

    __tablename__ = "call_logs"
    __table_args__ = (
        Index("ix_call_logs_ts", "ts"),
        Index("ix_call_logs_service_ts", "service_id", "ts"),
        Index("ix_call_logs_apikey_ts", "api_key_id", "ts"),
        Index("ix_call_logs_status_ts", "status", "ts"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    api_key_id: Mapped[int | None] = mapped_column(Integer)
    application_id: Mapped[int | None] = mapped_column(Integer)
    user_id: Mapped[int | None] = mapped_column(Integer)
    service_id: Mapped[int] = mapped_column(Integer, nullable=False)
    service_version: Mapped[str | None] = mapped_column(String(32))
    tool_name: Mapped[str | None] = mapped_column(String(128))
    request_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[CallStatus] = mapped_column(Enum(CallStatus), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    request_bytes: Mapped[int | None] = mapped_column(Integer)
    response_bytes: Mapped[int | None] = mapped_column(Integer)
    request_body: Mapped[str | None] = mapped_column(Text)
    response_body: Mapped[str | None] = mapped_column(Text)
    client_ip: Mapped[str | None] = mapped_column(String(64))


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(64))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(64))
```

> 注：本 MVP 不引入 `service_permissions` / `rate_limit_policies` / `service_configs`（属 v1 范围，按 spec §6 推迟）。

- [ ] **Step 4: 写 conftest 启动 testcontainers Postgres**

```python
# /dataspace/kqspace/MCPsys/packages/mcpsys_shared/tests/conftest.py
import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.postgres import PostgresContainer

from mcpsys_shared.db import make_engine, make_session_factory
from mcpsys_shared.models import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def pg_url() -> AsyncIterator[str]:
    with PostgresContainer("postgres:16-alpine") as pg:
        raw = pg.get_connection_url()
        # testcontainers returns "postgresql+psycopg2://..."; convert to asyncpg
        url = raw.replace("postgresql+psycopg2", "postgresql+asyncpg")
        yield url


@pytest.fixture(scope="session")
async def engine(pg_url) -> AsyncIterator[AsyncEngine]:
    eng = make_engine(pg_url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    factory = make_session_factory(engine)
    async with factory() as s:
        yield s
        await s.rollback()
```

- [ ] **Step 5: 写 smoke 测试**

```python
# /dataspace/kqspace/MCPsys/packages/mcpsys_shared/tests/test_models_smoke.py
from sqlalchemy import select

from mcpsys_shared.models import McpService, ServiceStatus, TransportType, User, UserRole


async def test_create_user(session):
    u = User(username="alice", role=UserRole.admin)
    session.add(u)
    await session.flush()
    res = await session.execute(select(User).where(User.username == "alice"))
    fetched = res.scalar_one()
    assert fetched.role == UserRole.admin


async def test_create_mcp_service(session):
    svc = McpService(
        slug="hr-bot",
        display_name="HR Bot",
        endpoint_url="http://hr-bot.internal:8000/mcp",
        transport=TransportType.streamable_http,
        status=ServiceStatus.active,
    )
    session.add(svc)
    await session.flush()
    res = await session.execute(select(McpService).where(McpService.slug == "hr-bot"))
    fetched = res.scalar_one()
    assert fetched.endpoint_url == "http://hr-bot.internal:8000/mcp"
```

- [ ] **Step 6: 运行测试，确认通过**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv run --package mcpsys-shared pytest packages/mcpsys_shared/tests -v
```
Expected: `2 passed`（首次会拉 postgres:16-alpine 镜像，可能耗时 1–2 分钟）。

- [ ] **Step 7: 提交**

```bash
git add packages/mcpsys_shared && git commit -m "feat(shared): add ORM models, db helpers, and smoke tests"
```

---

### Task 4: Alembic 初始化与首迁移

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/alembic.ini`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/alembic/env.py`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/alembic/script.py.mako`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/alembic/versions/.gitkeep`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/alembic/versions/0001_initial.py`（autogenerate 产物，本任务里手动微调）

- [ ] **Step 1: 写 `alembic.ini`**

```ini
# /dataspace/kqspace/MCPsys/services/control_plane/alembic.ini
[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url = driver://placeholder

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

- [ ] **Step 2: 写 `alembic/env.py`（异步、从 SharedSettings 读 URL）**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/alembic/env.py
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

from mcpsys_shared.models import Base
from mcpsys_shared.settings import SharedSettings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = SharedSettings()
# alembic uses sync driver for migrations; swap asyncpg → psycopg
sync_url = settings.database_url.replace("postgresql+asyncpg", "postgresql+psycopg")
config.set_main_option("sqlalchemy.url", sync_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: 写 `script.py.mako`**

```mako
# /dataspace/kqspace/MCPsys/services/control_plane/alembic/script.py.mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: 在 control_plane pyproject 中加 psycopg(同步驱动) 依赖（alembic 用）**

编辑 `/dataspace/kqspace/MCPsys/services/control_plane/pyproject.toml`，在 `dependencies` 数组中追加：
```
    "psycopg[binary]>=3.1",
```

然后：
```bash
cd /dataspace/kqspace/MCPsys && uv sync
```

- [ ] **Step 5: 让 alembic autogenerate 首迁移**

Run:
```bash
cd /dataspace/kqspace/MCPsys/services/control_plane && \
  uv run alembic revision --autogenerate -m "initial schema" -r 0001
```
Expected: 在 `alembic/versions/` 下生成 `0001_initial.py`，文件中包含 `op.create_table('users')` 等。

- [ ] **Step 6: 应用迁移**

Run:
```bash
cd /dataspace/kqspace/MCPsys/services/control_plane && uv run alembic upgrade head
```
Expected: `INFO  [alembic.runtime.migration] Running upgrade -> 0001, initial schema`。

- [ ] **Step 7: 在 Postgres 里验证表已建**

Run:
```bash
docker compose exec postgres psql -U mcpsys -d mcpsys -c "\dt"
```
Expected: 输出含 `users`, `applications`, `api_keys`, `mcp_services`, `mcp_service_versions`, `call_logs`, `audit_events`, `alembic_version`。

- [ ] **Step 8: 提交**

```bash
git add services/control_plane && git commit -m "feat(control_plane): bootstrap alembic with initial schema"
```

---

## 阶段二：Control Plane（T5–T11）

### Task 5: Control Plane FastAPI 骨架（settings + main + healthz）

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/settings.py`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/main.py`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/tests/__init__.py`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/tests/conftest.py`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/tests/test_healthz.py`

- [ ] **Step 1: 写 settings**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/settings.py
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from mcpsys_shared.settings import SharedSettings


class ControlPlaneSettings(SharedSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = Field(default="dev-only-secret-change-me")
    jwt_expires_minutes: int = Field(default=60)
    config_fernet_key: str | None = Field(default=None)


settings = ControlPlaneSettings()
```

- [ ] **Step 2: 写 main.py（暂只挂 healthz）**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mcpsys_shared.db import make_engine, make_session_factory

from .settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = make_engine(settings.database_url)
    app.state.session_factory = make_session_factory(app.state.engine)
    yield
    await app.state.engine.dispose()


app = FastAPI(title="MCPsys Control Plane", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 3: 写 conftest**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/tests/conftest.py
import asyncio
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from testcontainers.postgres import PostgresContainer

from mcpsys_shared.db import make_engine, make_session_factory
from mcpsys_shared.models import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def pg_url() -> AsyncIterator[str]:
    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url().replace("postgresql+psycopg2", "postgresql+asyncpg")
        yield url


@pytest.fixture(scope="session")
async def engine(pg_url) -> AsyncIterator[AsyncEngine]:
    eng = make_engine(pg_url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session_factory(engine) -> async_sessionmaker:
    return make_session_factory(engine)


@pytest.fixture
async def app(engine, session_factory):
    from control_plane.main import app as fastapi_app

    fastapi_app.state.engine = engine
    fastapi_app.state.session_factory = session_factory
    return fastapi_app


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

- [ ] **Step 4: 写 healthz 测试（先失败）**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/tests/test_healthz.py
async def test_healthz_returns_ok(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 5: 运行测试**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv run --package control-plane pytest services/control_plane/tests -v
```
Expected: `1 passed`。

- [ ] **Step 6: 提交**

```bash
git add services/control_plane/src services/control_plane/tests && \
  git commit -m "feat(control_plane): scaffold FastAPI app with healthz"
```

---

### Task 6: 安全工具（密码哈希、JWT、API Key 生成）

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/security.py`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/tests/test_security.py`

- [ ] **Step 1: 写测试（红）**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/tests/test_security.py
import time

import pytest

from control_plane.security import (
    decode_jwt,
    encode_jwt,
    generate_api_key,
    hash_password,
    verify_password,
)


def test_password_round_trip():
    h = hash_password("hunter2")
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_jwt_round_trip():
    token = encode_jwt({"sub": "alice", "role": "admin"}, secret="s", expires_minutes=5)
    payload = decode_jwt(token, secret="s")
    assert payload["sub"] == "alice"
    assert payload["role"] == "admin"


def test_jwt_expired_raises():
    token = encode_jwt({"sub": "alice"}, secret="s", expires_minutes=-1)
    with pytest.raises(Exception):
        decode_jwt(token, secret="s")


def test_generate_api_key_format():
    plaintext, prefix, hashed = generate_api_key()
    assert plaintext.startswith("mcpk_")
    assert len(prefix) == 8
    assert plaintext.startswith(prefix) is False  # prefix excludes the "mcpk_" tag bytes
    assert hashed != plaintext
    assert len(plaintext) >= 32
```

- [ ] **Step 2: 运行测试，确认失败**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv run --package control-plane pytest services/control_plane/tests/test_security.py -v
```
Expected: `ImportError` on `control_plane.security`。

- [ ] **Step 3: 写实现**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/security.py
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

API_KEY_TAG = "mcpk_"
API_KEY_RANDOM_BYTES = 24  # → 32 chars base64url
PREFIX_LEN = 8


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def encode_jwt(claims: dict[str, Any], *, secret: str, expires_minutes: int) -> str:
    now = datetime.now(UTC)
    payload = {**claims, "iat": now, "exp": now + timedelta(minutes=expires_minutes)}
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_jwt(token: str, *, secret: str) -> dict[str, Any]:
    return jwt.decode(token, secret, algorithms=["HS256"])


def generate_api_key() -> tuple[str, str, str]:
    """Return (plaintext, prefix_for_display, bcrypt_hash).

    plaintext format: "mcpk_<32-char base64url random>"
    prefix is the first PREFIX_LEN chars of the random portion (after the tag).
    """
    rand = secrets.token_urlsafe(API_KEY_RANDOM_BYTES)
    plaintext = f"{API_KEY_TAG}{rand}"
    prefix = rand[:PREFIX_LEN]
    hashed = bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt()).decode()
    return plaintext, prefix, hashed


def verify_api_key(plaintext: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plaintext.encode(), hashed.encode())
    except ValueError:
        return False
```

- [ ] **Step 4: 修正测试中关于 prefix 的断言（实现明确：prefix 是去掉 `mcpk_` 后的前 8 字符）**

编辑 `/dataspace/kqspace/MCPsys/services/control_plane/tests/test_security.py`，把 `test_generate_api_key_format` 改为：

```python
def test_generate_api_key_format():
    plaintext, prefix, hashed = generate_api_key()
    assert plaintext.startswith("mcpk_")
    assert len(prefix) == 8
    # prefix corresponds to the random portion after the tag
    assert plaintext[len("mcpk_"):].startswith(prefix)
    assert hashed != plaintext
    assert len(plaintext) >= 32
```

- [ ] **Step 5: 运行测试，确认通过**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv run --package control-plane pytest services/control_plane/tests/test_security.py -v
```
Expected: `4 passed`。

- [ ] **Step 6: 提交**

```bash
git add services/control_plane/src/control_plane/security.py services/control_plane/tests/test_security.py && \
  git commit -m "feat(control_plane): add password, jwt, and api key utilities"
```

---

### Task 7: 登录端点 + 当前用户依赖

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/deps.py`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/routers/__init__.py`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/routers/auth.py`
- Modify: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/main.py`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/tests/test_auth.py`

- [ ] **Step 1: 写 deps.py（DB 会话、当前用户）**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/deps.py
from collections.abc import AsyncIterator

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpsys_shared.models import User, UserStatus

from .security import decode_jwt
from .settings import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing token")
    try:
        payload = decode_jwt(token, secret=settings.jwt_secret)
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing sub")

    res = await db.execute(select(User).where(User.id == int(user_id)))
    user = res.scalar_one_or_none()
    if user is None or user.status != UserStatus.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user inactive or missing")
    return user


def require_role(*roles: str):
    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return user

    return _check
```

- [ ] **Step 2: 写 auth router**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/routers/__init__.py
```

```python
# /dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/routers/auth.py
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpsys_shared.models import User, UserStatus

from ..deps import get_db
from ..security import encode_jwt, verify_password
from ..settings import settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    res = await db.execute(select(User).where(User.username == form.username))
    user = res.scalar_one_or_none()
    if (
        user is None
        or user.password_hash is None
        or not verify_password(form.password, user.password_hash)
        or user.status != UserStatus.active
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    user.last_login_at = datetime.now(UTC)

    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value, "username": user.username},
        secret=settings.jwt_secret,
        expires_minutes=settings.jwt_expires_minutes,
    )
    return TokenResponse(access_token=token)
```

- [ ] **Step 3: 在 main.py 中注册 router**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mcpsys_shared.db import make_engine, make_session_factory

from .routers import auth as auth_router
from .settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = make_engine(settings.database_url)
    app.state.session_factory = make_session_factory(app.state.engine)
    yield
    await app.state.engine.dispose()


app = FastAPI(title="MCPsys Control Plane", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router.router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 4: 写 auth 测试**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/tests/test_auth.py
import pytest

from mcpsys_shared.models import User, UserRole, UserStatus

from control_plane.security import hash_password


@pytest.fixture
async def alice(session_factory):
    async with session_factory() as s:
        u = User(
            username="alice",
            password_hash=hash_password("hunter2"),
            role=UserRole.admin,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


async def test_login_success(client, alice):
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "alice", "password": "hunter2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]


async def test_login_wrong_password(client, alice):
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "alice", "password": "wrong"},
    )
    assert resp.status_code == 401


async def test_login_unknown_user(client):
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "nobody", "password": "x"},
    )
    assert resp.status_code == 401
```

- [ ] **Step 5: 运行测试**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv run --package control-plane pytest services/control_plane/tests/test_auth.py -v
```
Expected: `3 passed`。

- [ ] **Step 6: 提交**

```bash
git add services/control_plane && git commit -m "feat(control_plane): add login endpoint and auth dependencies"
```

---

### Task 8: User CRUD（仅 admin 可操作）

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/routers/users.py`
- Modify: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/main.py`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/tests/test_users.py`

- [ ] **Step 1: 写测试（覆盖：创建、列表、未授权拒绝）**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/tests/test_users.py
import pytest

from mcpsys_shared.models import User, UserRole, UserStatus

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as s:
        u = User(
            username="admin",
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
            username="viewer",
            password_hash=hash_password("p"),
            role=UserRole.viewer,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


def auth_header(user):
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


async def test_create_user_as_admin(client, admin):
    resp = await client.post(
        "/api/v1/users",
        headers=auth_header(admin),
        json={"username": "bob", "password": "secret123", "role": "operator"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "bob"
    assert body["role"] == "operator"
    assert "password_hash" not in body


async def test_create_user_as_viewer_forbidden(client, viewer):
    resp = await client.post(
        "/api/v1/users",
        headers=auth_header(viewer),
        json={"username": "bob", "password": "secret123", "role": "operator"},
    )
    assert resp.status_code == 403


async def test_list_users_as_admin(client, admin):
    resp = await client.get("/api/v1/users", headers=auth_header(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert any(u["username"] == "admin" for u in body["items"])


async def test_unauthenticated_rejected(client):
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 401
```

- [ ] **Step 2: 写实现**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/routers/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mcpsys_shared.models import User, UserRole, UserStatus

from ..deps import get_db, require_role
from ..security import hash_password

router = APIRouter(prefix="/api/v1/users", tags=["users"])


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    email: EmailStr | None = None
    role: UserRole = UserRole.viewer


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str | None
    role: UserRole
    status: UserStatus


class UserList(BaseModel):
    items: list[UserOut]
    total: int


@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin"))],
)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> UserOut:
    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "username already exists") from e
    return UserOut.model_validate(user)


@router.get(
    "",
    response_model=UserList,
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)
async def list_users(db: AsyncSession = Depends(get_db)) -> UserList:
    res = await db.execute(select(User).order_by(User.id))
    users = res.scalars().all()
    return UserList(items=[UserOut.model_validate(u) for u in users], total=len(users))
```

- [ ] **Step 3: 在 main.py 注册**

编辑 `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/main.py`，把 import 行改为：
```python
from .routers import auth as auth_router, users as users_router
```
并在 `app.include_router(auth_router.router)` 下面追加：
```python
app.include_router(users_router.router)
```

- [ ] **Step 4: 在 pyproject 增加 email-validator 依赖**

编辑 `/dataspace/kqspace/MCPsys/services/control_plane/pyproject.toml`，在 `dependencies` 数组追加：
```
    "email-validator>=2",
```
然后：
```bash
cd /dataspace/kqspace/MCPsys && uv sync
```

- [ ] **Step 5: 运行测试**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv run --package control-plane pytest services/control_plane/tests/test_users.py -v
```
Expected: `4 passed`。

- [ ] **Step 6: 提交**

```bash
git add services/control_plane && git commit -m "feat(control_plane): add user CRUD (create/list, admin-gated)"
```

---

### Task 9: Application CRUD（创建/列出，admin/operator 可写）

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/routers/applications.py`
- Modify: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/main.py`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/tests/test_applications.py`

- [ ] **Step 1: 写测试**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/tests/test_applications.py
import pytest

from mcpsys_shared.models import User, UserRole, UserStatus

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as s:
        u = User(
            username="admin2",
            password_hash=hash_password("p"),
            role=UserRole.admin,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


def auth_header(user):
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


async def test_create_application(client, admin):
    resp = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "billing-agent", "team": "finance", "description": "monthly billing"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "billing-agent"
    assert body["owner_user_id"] == admin.id


async def test_list_applications(client, admin):
    await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "ops-agent"},
    )
    resp = await client.get("/api/v1/applications", headers=auth_header(admin))
    assert resp.status_code == 200
    names = [a["name"] for a in resp.json()["items"]]
    assert "ops-agent" in names


async def test_create_duplicate_name_conflict(client, admin):
    await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "dup-app"},
    )
    resp = await client.post(
        "/api/v1/applications",
        headers=auth_header(admin),
        json={"name": "dup-app"},
    )
    assert resp.status_code == 409
```

- [ ] **Step 2: 写实现**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/routers/applications.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mcpsys_shared.models import Application, User

from ..deps import get_current_user, get_db, require_role

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])


class ApplicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    team: str | None = None
    description: str | None = None


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    owner_user_id: int
    team: str | None
    description: str | None


class ApplicationList(BaseModel):
    items: list[ApplicationOut]
    total: int


@router.post(
    "",
    response_model=ApplicationOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin", "operator"))],
)
async def create_application(
    payload: ApplicationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApplicationOut:
    app_obj = Application(
        name=payload.name,
        team=payload.team,
        description=payload.description,
        owner_user_id=current_user.id,
    )
    db.add(app_obj)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "name already exists") from e
    return ApplicationOut.model_validate(app_obj)


@router.get(
    "",
    response_model=ApplicationList,
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)
async def list_applications(db: AsyncSession = Depends(get_db)) -> ApplicationList:
    res = await db.execute(select(Application).order_by(Application.id))
    items = res.scalars().all()
    return ApplicationList(
        items=[ApplicationOut.model_validate(a) for a in items], total=len(items)
    )
```

- [ ] **Step 3: 注册 router**

编辑 `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/main.py`：
```python
from .routers import (
    applications as applications_router,
    auth as auth_router,
    users as users_router,
)
```
并追加：
```python
app.include_router(applications_router.router)
```

- [ ] **Step 4: 运行测试**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv run --package control-plane pytest services/control_plane/tests/test_applications.py -v
```
Expected: `3 passed`。

- [ ] **Step 5: 提交**

```bash
git add services/control_plane && git commit -m "feat(control_plane): add application CRUD"
```

---

### Task 10: MCP Service CRUD

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/routers/services.py`
- Modify: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/main.py`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/tests/test_services.py`

- [ ] **Step 1: 写测试**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/tests/test_services.py
import pytest

from mcpsys_shared.models import User, UserRole, UserStatus

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as s:
        u = User(
            username="svc-admin",
            password_hash=hash_password("p"),
            role=UserRole.admin,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


def auth_header(user):
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


async def test_create_service(client, admin):
    resp = await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={
            "slug": "hr-bot",
            "display_name": "HR Bot",
            "description": "internal HR mcp",
            "owner_team": "hr",
            "tags": ["internal"],
            "endpoint_url": "http://hr-bot.internal:8000/mcp",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "hr-bot"
    assert body["transport"] == "streamable_http"
    assert body["status"] == "active"
    assert body["health_status"] == "unknown"


async def test_invalid_slug_rejected(client, admin):
    resp = await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={
            "slug": "Has Spaces",
            "display_name": "x",
            "endpoint_url": "http://x/mcp",
        },
    )
    assert resp.status_code == 422


async def test_get_service_by_slug(client, admin):
    await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={"slug": "crm", "display_name": "CRM", "endpoint_url": "http://crm/mcp"},
    )
    resp = await client.get("/api/v1/services/crm", headers=auth_header(admin))
    assert resp.status_code == 200
    assert resp.json()["slug"] == "crm"


async def test_update_service_endpoint(client, admin):
    await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={"slug": "wiki", "display_name": "Wiki", "endpoint_url": "http://old/mcp"},
    )
    resp = await client.patch(
        "/api/v1/services/wiki",
        headers=auth_header(admin),
        json={"endpoint_url": "http://new/mcp", "status": "disabled"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["endpoint_url"] == "http://new/mcp"
    assert body["status"] == "disabled"


async def test_delete_service(client, admin):
    await client.post(
        "/api/v1/services",
        headers=auth_header(admin),
        json={"slug": "tmp", "display_name": "Tmp", "endpoint_url": "http://tmp/mcp"},
    )
    resp = await client.delete("/api/v1/services/tmp", headers=auth_header(admin))
    assert resp.status_code == 204
    resp2 = await client.get("/api/v1/services/tmp", headers=auth_header(admin))
    assert resp2.status_code == 404
```

- [ ] **Step 2: 写实现**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/routers/services.py
import re

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mcpsys_shared.models import (
    HealthStatus,
    McpService,
    ServiceStatus,
    TransportType,
)

from ..deps import get_db, require_role

router = APIRouter(prefix="/api/v1/services", tags=["services"])

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$")


class ServiceCreate(BaseModel):
    slug: str
    display_name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    owner_team: str | None = None
    tags: list[str] = Field(default_factory=list)
    endpoint_url: HttpUrl
    transport: TransportType = TransportType.streamable_http

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError("slug must be lowercase alphanumeric with hyphens, 2-64 chars")
        return v


class ServiceUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    owner_team: str | None = None
    tags: list[str] | None = None
    endpoint_url: HttpUrl | None = None
    status: ServiceStatus | None = None


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str
    display_name: str
    description: str | None
    owner_team: str | None
    tags: list
    endpoint_url: str
    transport: TransportType
    status: ServiceStatus
    health_status: HealthStatus


class ServiceList(BaseModel):
    items: list[ServiceOut]
    total: int


@router.post(
    "",
    response_model=ServiceOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin", "operator"))],
)
async def create_service(payload: ServiceCreate, db: AsyncSession = Depends(get_db)) -> ServiceOut:
    svc = McpService(
        slug=payload.slug,
        display_name=payload.display_name,
        description=payload.description,
        owner_team=payload.owner_team,
        tags=payload.tags,
        endpoint_url=str(payload.endpoint_url),
        transport=payload.transport,
    )
    db.add(svc)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "slug already exists") from e
    return ServiceOut.model_validate(svc)


@router.get(
    "",
    response_model=ServiceList,
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)
async def list_services(db: AsyncSession = Depends(get_db)) -> ServiceList:
    res = await db.execute(select(McpService).order_by(McpService.id))
    items = res.scalars().all()
    return ServiceList(items=[ServiceOut.model_validate(s) for s in items], total=len(items))


@router.get(
    "/{slug}",
    response_model=ServiceOut,
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)
async def get_service(slug: str, db: AsyncSession = Depends(get_db)) -> ServiceOut:
    res = await db.execute(select(McpService).where(McpService.slug == slug))
    svc = res.scalar_one_or_none()
    if svc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "service not found")
    return ServiceOut.model_validate(svc)


@router.patch(
    "/{slug}",
    response_model=ServiceOut,
    dependencies=[Depends(require_role("admin", "operator"))],
)
async def update_service(
    slug: str, payload: ServiceUpdate, db: AsyncSession = Depends(get_db)
) -> ServiceOut:
    res = await db.execute(select(McpService).where(McpService.slug == slug))
    svc = res.scalar_one_or_none()
    if svc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "service not found")

    data = payload.model_dump(exclude_unset=True)
    if "endpoint_url" in data and data["endpoint_url"] is not None:
        data["endpoint_url"] = str(data["endpoint_url"])
    for k, v in data.items():
        setattr(svc, k, v)
    await db.flush()
    return ServiceOut.model_validate(svc)


@router.delete(
    "/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("admin"))],
)
async def delete_service(slug: str, db: AsyncSession = Depends(get_db)) -> Response:
    res = await db.execute(select(McpService).where(McpService.slug == slug))
    svc = res.scalar_one_or_none()
    if svc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "service not found")
    await db.delete(svc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 3: 注册 router**

编辑 `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/main.py`，update imports:
```python
from .routers import (
    applications as applications_router,
    auth as auth_router,
    services as services_router,
    users as users_router,
)
```
并追加：
```python
app.include_router(services_router.router)
```

- [ ] **Step 4: 运行测试**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv run --package control-plane pytest services/control_plane/tests/test_services.py -v
```
Expected: `5 passed`。

- [ ] **Step 5: 提交**

```bash
git add services/control_plane && git commit -m "feat(control_plane): add MCP service CRUD with slug validation"
```

---

### Task 11: API Key 签发与吊销

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/routers/api_keys.py`
- Modify: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/main.py`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/tests/test_api_keys.py`

- [ ] **Step 1: 写测试**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/tests/test_api_keys.py
import pytest

from mcpsys_shared.models import Application, User, UserRole, UserStatus

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings


@pytest.fixture
async def admin_and_app(session_factory):
    async with session_factory() as s:
        u = User(
            username="key-admin",
            password_hash=hash_password("p"),
            role=UserRole.admin,
            status=UserStatus.active,
        )
        s.add(u)
        await s.flush()
        a = Application(name="agent-x", owner_user_id=u.id)
        s.add(a)
        await s.commit()
        await s.refresh(u)
        await s.refresh(a)
        return u, a


def auth_header(user):
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


async def test_create_api_key_returns_plaintext_once(client, admin_and_app):
    admin, app_obj = admin_and_app
    resp = await client.post(
        "/api/v1/api-keys",
        headers=auth_header(admin),
        json={
            "name": "agent-x main",
            "owner_type": "application",
            "owner_id": app_obj.id,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["plaintext"].startswith("mcpk_")
    assert body["key_prefix"] and len(body["key_prefix"]) == 8
    assert body["id"]


async def test_list_api_keys_no_plaintext(client, admin_and_app):
    admin, app_obj = admin_and_app
    await client.post(
        "/api/v1/api-keys",
        headers=auth_header(admin),
        json={"name": "k1", "owner_type": "application", "owner_id": app_obj.id},
    )
    resp = await client.get("/api/v1/api-keys", headers=auth_header(admin))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all("plaintext" not in i for i in items)
    assert all("key_hash" not in i for i in items)
    assert any(i["name"] == "k1" for i in items)


async def test_revoke_api_key(client, admin_and_app):
    admin, app_obj = admin_and_app
    create = await client.post(
        "/api/v1/api-keys",
        headers=auth_header(admin),
        json={"name": "k2", "owner_type": "application", "owner_id": app_obj.id},
    )
    key_id = create.json()["id"]
    resp = await client.delete(f"/api/v1/api-keys/{key_id}", headers=auth_header(admin))
    assert resp.status_code == 204
    listing = await client.get("/api/v1/api-keys", headers=auth_header(admin))
    target = next(i for i in listing.json()["items"] if i["id"] == key_id)
    assert target["revoked_at"] is not None
```

- [ ] **Step 2: 写实现**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/routers/api_keys.py
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpsys_shared.models import ApiKey, ApiKeyOwnerType, Application, User

from ..deps import get_db, require_role
from ..security import generate_api_key

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    owner_type: ApiKeyOwnerType
    owner_id: int
    expires_at: datetime | None = None


class ApiKeyCreated(BaseModel):
    id: int
    name: str
    plaintext: str
    key_prefix: str


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    key_prefix: str
    owner_type: ApiKeyOwnerType
    owner_id: int
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyList(BaseModel):
    items: list[ApiKeyOut]
    total: int


async def _validate_owner(db: AsyncSession, owner_type: ApiKeyOwnerType, owner_id: int) -> None:
    if owner_type == ApiKeyOwnerType.user:
        res = await db.execute(select(User).where(User.id == owner_id))
    else:
        res = await db.execute(select(Application).where(Application.id == owner_id))
    if res.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{owner_type.value} not found")


@router.post(
    "",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin", "operator"))],
)
async def create_api_key(payload: ApiKeyCreate, db: AsyncSession = Depends(get_db)) -> ApiKeyCreated:
    await _validate_owner(db, payload.owner_type, payload.owner_id)
    plaintext, prefix, hashed = generate_api_key()
    key = ApiKey(
        name=payload.name,
        key_prefix=prefix,
        key_hash=hashed,
        owner_type=payload.owner_type,
        owner_id=payload.owner_id,
        expires_at=payload.expires_at,
    )
    db.add(key)
    await db.flush()
    return ApiKeyCreated(id=key.id, name=key.name, plaintext=plaintext, key_prefix=prefix)


@router.get(
    "",
    response_model=ApiKeyList,
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)
async def list_api_keys(db: AsyncSession = Depends(get_db)) -> ApiKeyList:
    res = await db.execute(select(ApiKey).order_by(ApiKey.id))
    items = res.scalars().all()
    return ApiKeyList(items=[ApiKeyOut.model_validate(k) for k in items], total=len(items))


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("admin", "operator"))],
)
async def revoke_api_key(key_id: int, db: AsyncSession = Depends(get_db)) -> Response:
    res = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    key = res.scalar_one_or_none()
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "api key not found")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 3: 注册 router**

编辑 `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/main.py`，update imports：
```python
from .routers import (
    api_keys as api_keys_router,
    applications as applications_router,
    auth as auth_router,
    services as services_router,
    users as users_router,
)
```
追加：
```python
app.include_router(api_keys_router.router)
```

- [ ] **Step 4: 运行测试**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv run --package control-plane pytest services/control_plane/tests/test_api_keys.py -v
```
Expected: `3 passed`。

- [ ] **Step 5: 提交**

```bash
git add services/control_plane && git commit -m "feat(control_plane): add API key issuance and revocation"
```

---

## 阶段三：Gateway（T12–T17）

### Task 12: Gateway FastAPI 骨架（settings + main + healthz）

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/gateway/src/gateway/settings.py`
- Create: `/dataspace/kqspace/MCPsys/services/gateway/src/gateway/main.py`
- Create: `/dataspace/kqspace/MCPsys/services/gateway/tests/__init__.py`
- Create: `/dataspace/kqspace/MCPsys/services/gateway/tests/conftest.py`
- Create: `/dataspace/kqspace/MCPsys/services/gateway/tests/test_healthz.py`

- [ ] **Step 1: 写 settings**

```python
# /dataspace/kqspace/MCPsys/services/gateway/src/gateway/settings.py
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from mcpsys_shared.settings import SharedSettings


class GatewaySettings(SharedSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    proxy_timeout_seconds: float = Field(default=30.0)
    api_key_cache_ttl_seconds: int = Field(default=60)
    service_cache_ttl_seconds: int = Field(default=60)
    telemetry_flush_interval_seconds: float = Field(default=1.0)
    telemetry_batch_size: int = Field(default=100)
    body_log_max_bytes: int = Field(default=64 * 1024)


settings = GatewaySettings()
```

- [ ] **Step 2: 写 main.py（暂只挂 healthz）**

```python
# /dataspace/kqspace/MCPsys/services/gateway/src/gateway/main.py
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from mcpsys_shared.db import make_engine, make_session_factory

from .settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = make_engine(settings.database_url)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.state.http = httpx.AsyncClient(timeout=settings.proxy_timeout_seconds)
    yield
    await app.state.http.aclose()
    await app.state.engine.dispose()


app = FastAPI(title="MCPsys Gateway", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 3: 写 conftest（共用 testcontainers postgres + redis）**

```python
# /dataspace/kqspace/MCPsys/services/gateway/tests/conftest.py
import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from mcpsys_shared.db import make_engine, make_session_factory
from mcpsys_shared.models import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def pg_url() -> AsyncIterator[str]:
    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url().replace("postgresql+psycopg2", "postgresql+asyncpg")
        yield url


@pytest.fixture(scope="session")
def redis_url() -> AsyncIterator[str]:
    with RedisContainer("redis:7-alpine") as r:
        host = r.get_container_host_ip()
        port = r.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


@pytest.fixture(scope="session")
async def engine(pg_url) -> AsyncIterator[AsyncEngine]:
    eng = make_engine(pg_url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session_factory(engine) -> async_sessionmaker:
    return make_session_factory(engine)


@pytest.fixture
async def app(engine, session_factory):
    from gateway.main import app as fastapi_app

    fastapi_app.state.engine = engine
    fastapi_app.state.session_factory = session_factory
    fastapi_app.state.http = httpx.AsyncClient()
    return fastapi_app


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await app.state.http.aclose()
```

- [ ] **Step 4: 写 healthz 测试**

```python
# /dataspace/kqspace/MCPsys/services/gateway/tests/test_healthz.py
async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 5: 运行测试**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv run --package gateway pytest services/gateway/tests/test_healthz.py -v
```
Expected: `1 passed`。

- [ ] **Step 6: 提交**

```bash
git add services/gateway && git commit -m "feat(gateway): scaffold FastAPI app with healthz"
```

---

### Task 13: API Key 校验（带 Redis 缓存）

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/gateway/src/gateway/auth.py`
- Create: `/dataspace/kqspace/MCPsys/services/gateway/tests/test_auth.py`

- [ ] **Step 1: 写测试**

```python
# /dataspace/kqspace/MCPsys/services/gateway/tests/test_auth.py
import pytest
from redis.asyncio import Redis

from mcpsys_shared.models import ApiKey, ApiKeyOwnerType, Application, User, UserRole

from gateway.auth import AuthError, ResolvedKey, validate_api_key


def hash_plain(plain: str) -> str:
    import bcrypt
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


@pytest.fixture
async def redis(redis_url):
    r = Redis.from_url(redis_url, decode_responses=True)
    await r.flushdb()
    yield r
    await r.aclose()


@pytest.fixture
async def seed_key(session_factory):
    async with session_factory() as s:
        u = User(username="owner", role=UserRole.viewer)
        s.add(u)
        await s.flush()
        a = Application(name="seed-app", owner_user_id=u.id)
        s.add(a)
        await s.flush()
        plain = "mcpk_testkey_abc"
        k = ApiKey(
            name="t",
            key_prefix=plain[5:13],
            key_hash=hash_plain(plain),
            owner_type=ApiKeyOwnerType.application,
            owner_id=a.id,
        )
        s.add(k)
        await s.commit()
        await s.refresh(k)
        return plain, k.id, a.id


async def test_validate_known_key(session_factory, redis, seed_key):
    plain, key_id, app_id = seed_key
    resolved = await validate_api_key(plain, session_factory=session_factory, redis=redis)
    assert isinstance(resolved, ResolvedKey)
    assert resolved.api_key_id == key_id
    assert resolved.application_id == app_id


async def test_validate_unknown_key_raises(session_factory, redis):
    with pytest.raises(AuthError):
        await validate_api_key(
            "mcpk_doesnotexist_x", session_factory=session_factory, redis=redis
        )


async def test_revoked_key_raises(session_factory, redis, seed_key):
    plain, key_id, _ = seed_key
    from datetime import UTC, datetime

    from sqlalchemy import select
    from mcpsys_shared.models import ApiKey

    async with session_factory() as s:
        res = await s.execute(select(ApiKey).where(ApiKey.id == key_id))
        k = res.scalar_one()
        k.revoked_at = datetime.now(UTC)
        await s.commit()

    # bypass cache for this test
    await redis.flushdb()
    with pytest.raises(AuthError):
        await validate_api_key(plain, session_factory=session_factory, redis=redis)


async def test_cache_returns_same_result(session_factory, redis, seed_key):
    plain, key_id, _ = seed_key
    r1 = await validate_api_key(plain, session_factory=session_factory, redis=redis)
    r2 = await validate_api_key(plain, session_factory=session_factory, redis=redis)
    assert r1.api_key_id == r2.api_key_id == key_id
```

- [ ] **Step 2: 写实现**

```python
# /dataspace/kqspace/MCPsys/services/gateway/src/gateway/auth.py
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import bcrypt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from mcpsys_shared.models import ApiKey, ApiKeyOwnerType

CACHE_PREFIX = "gw:apikey:"
NEGATIVE_TTL = 30  # cache "unknown" briefly to avoid hammering DB
TAG = "mcpk_"


class AuthError(Exception):
    pass


@dataclass
class ResolvedKey:
    api_key_id: int
    application_id: int | None
    user_id: int | None


def _extract_prefix(plaintext: str) -> str:
    if not plaintext.startswith(TAG):
        raise AuthError("malformed key")
    return plaintext[len(TAG) : len(TAG) + 8]


def _cache_key(prefix: str) -> str:
    return f"{CACHE_PREFIX}{prefix}"


async def validate_api_key(
    plaintext: str,
    *,
    session_factory: async_sessionmaker,
    redis: Redis,
    ttl_seconds: int = 60,
) -> ResolvedKey:
    prefix = _extract_prefix(plaintext)
    ck = _cache_key(prefix)

    cached = await redis.get(ck)
    if cached is not None:
        data = json.loads(cached)
        if data.get("ok") is False:
            raise AuthError("unknown key (cached)")
        # re-verify against the cached hash to ensure correct key matched (collision unlikely
        # but plaintext may differ within same prefix bucket)
        if bcrypt.checkpw(plaintext.encode(), data["hash"].encode()):
            return ResolvedKey(
                api_key_id=data["api_key_id"],
                application_id=data.get("application_id"),
                user_id=data.get("user_id"),
            )

    async with session_factory() as session:
        res = await session.execute(select(ApiKey).where(ApiKey.key_prefix == prefix))
        candidates = res.scalars().all()

    matched: ApiKey | None = None
    for k in candidates:
        if bcrypt.checkpw(plaintext.encode(), k.key_hash.encode()):
            matched = k
            break

    if matched is None:
        await redis.setex(ck, NEGATIVE_TTL, json.dumps({"ok": False}))
        raise AuthError("unknown key")

    if matched.revoked_at is not None:
        raise AuthError("revoked key")
    if matched.expires_at is not None and matched.expires_at < datetime.now(UTC):
        raise AuthError("expired key")

    payload = {
        "ok": True,
        "api_key_id": matched.id,
        "hash": matched.key_hash,
        "application_id": (
            matched.owner_id if matched.owner_type == ApiKeyOwnerType.application else None
        ),
        "user_id": matched.owner_id if matched.owner_type == ApiKeyOwnerType.user else None,
    }
    await redis.setex(ck, ttl_seconds, json.dumps(payload))

    return ResolvedKey(
        api_key_id=matched.id,
        application_id=payload["application_id"],
        user_id=payload["user_id"],
    )
```

- [ ] **Step 3: 运行测试**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv run --package gateway pytest services/gateway/tests/test_auth.py -v
```
Expected: `4 passed`（首次会拉 redis:7-alpine 镜像）。

- [ ] **Step 4: 提交**

```bash
git add services/gateway && git commit -m "feat(gateway): add api key validator with redis cache"
```

---

### Task 14: 服务解析（slug → endpoint）+ 简单内存 LRU

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/gateway/src/gateway/resolver.py`
- Create: `/dataspace/kqspace/MCPsys/services/gateway/tests/test_resolver.py`

- [ ] **Step 1: 写测试**

```python
# /dataspace/kqspace/MCPsys/services/gateway/tests/test_resolver.py
import pytest

from mcpsys_shared.models import McpService, ServiceStatus, TransportType

from gateway.resolver import ServiceNotFound, ServiceResolver


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as s:
        s.add(
            McpService(
                slug="active-svc",
                display_name="A",
                endpoint_url="http://a.internal/mcp",
                transport=TransportType.streamable_http,
                status=ServiceStatus.active,
            )
        )
        s.add(
            McpService(
                slug="disabled-svc",
                display_name="D",
                endpoint_url="http://d.internal/mcp",
                transport=TransportType.streamable_http,
                status=ServiceStatus.disabled,
            )
        )
        await s.commit()


async def test_resolves_active_service(session_factory, seeded):
    r = ServiceResolver(session_factory=session_factory, ttl_seconds=60)
    info = await r.resolve("active-svc")
    assert info.endpoint_url == "http://a.internal/mcp"
    assert info.service_id is not None


async def test_disabled_service_raises(session_factory, seeded):
    r = ServiceResolver(session_factory=session_factory, ttl_seconds=60)
    with pytest.raises(ServiceNotFound):
        await r.resolve("disabled-svc")


async def test_unknown_service_raises(session_factory, seeded):
    r = ServiceResolver(session_factory=session_factory, ttl_seconds=60)
    with pytest.raises(ServiceNotFound):
        await r.resolve("nope")


async def test_invalidate_clears_cache(session_factory, seeded):
    r = ServiceResolver(session_factory=session_factory, ttl_seconds=60)
    info1 = await r.resolve("active-svc")

    # mutate underlying record
    from sqlalchemy import select

    async with session_factory() as s:
        res = await s.execute(select(McpService).where(McpService.slug == "active-svc"))
        svc = res.scalar_one()
        svc.endpoint_url = "http://a.internal/mcp/v2"
        await s.commit()

    # cached value still old
    info2 = await r.resolve("active-svc")
    assert info2.endpoint_url == info1.endpoint_url

    r.invalidate("active-svc")
    info3 = await r.resolve("active-svc")
    assert info3.endpoint_url == "http://a.internal/mcp/v2"
```

- [ ] **Step 2: 写实现**

```python
# /dataspace/kqspace/MCPsys/services/gateway/src/gateway/resolver.py
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from mcpsys_shared.models import McpService, ServiceStatus


class ServiceNotFound(Exception):
    pass


@dataclass
class ResolvedService:
    service_id: int
    slug: str
    endpoint_url: str
    transport: str


class ServiceResolver:
    """Slug → service info, with simple per-process TTL cache.

    External invalidation should call `invalidate(slug)` (driven by control plane
    via redis pub/sub in a future task)."""

    def __init__(self, *, session_factory: async_sessionmaker, ttl_seconds: int = 60) -> None:
        self._sf = session_factory
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, ResolvedService]] = {}

    def invalidate(self, slug: str | None = None) -> None:
        if slug is None:
            self._cache.clear()
        else:
            self._cache.pop(slug, None)

    async def resolve(self, slug: str) -> ResolvedService:
        now = time.monotonic()
        hit = self._cache.get(slug)
        if hit and hit[0] > now:
            return hit[1]

        async with self._sf() as session:
            res = await session.execute(select(McpService).where(McpService.slug == slug))
            svc = res.scalar_one_or_none()

        if svc is None or svc.status != ServiceStatus.active:
            raise ServiceNotFound(slug)

        info = ResolvedService(
            service_id=svc.id,
            slug=svc.slug,
            endpoint_url=svc.endpoint_url,
            transport=svc.transport.value,
        )
        self._cache[slug] = (now + self._ttl, info)
        return info
```

- [ ] **Step 3: 运行测试**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv run --package gateway pytest services/gateway/tests/test_resolver.py -v
```
Expected: `4 passed`。

- [ ] **Step 4: 提交**

```bash
git add services/gateway && git commit -m "feat(gateway): add service slug resolver with TTL cache"
```

---

### Task 15: HTTP 代理（httpx 流式转发）

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/gateway/src/gateway/proxy.py`
- Create: `/dataspace/kqspace/MCPsys/services/gateway/tests/test_proxy.py`

- [ ] **Step 1: 写测试（用 respx 拦截 httpx）**

```python
# /dataspace/kqspace/MCPsys/services/gateway/tests/test_proxy.py
import httpx
import pytest
import respx

from gateway.proxy import ProxyResult, forward


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as c:
        yield c


@respx.mock
async def test_forward_returns_upstream_body(client):
    respx.post("http://upstream/mcp").respond(
        200, json={"jsonrpc": "2.0", "result": {"ok": True}, "id": 1}
    )
    result = await forward(
        client=client,
        upstream_url="http://upstream/mcp",
        body=b'{"jsonrpc":"2.0","method":"tools/call","id":1}',
        headers={"content-type": "application/json"},
    )
    assert isinstance(result, ProxyResult)
    assert result.status == 200
    assert b'"ok"' in result.body
    assert result.duration_ms >= 0


@respx.mock
async def test_forward_upstream_5xx_passes_through(client):
    respx.post("http://upstream/mcp").respond(503, text="upstream busy")
    result = await forward(
        client=client,
        upstream_url="http://upstream/mcp",
        body=b"{}",
        headers={"content-type": "application/json"},
    )
    assert result.status == 503
    assert b"upstream busy" in result.body


@respx.mock
async def test_forward_timeout_raises(client):
    respx.post("http://upstream/mcp").mock(side_effect=httpx.ReadTimeout("slow"))
    from gateway.proxy import ProxyTimeout

    with pytest.raises(ProxyTimeout):
        await forward(
            client=client,
            upstream_url="http://upstream/mcp",
            body=b"{}",
            headers={"content-type": "application/json"},
        )
```

- [ ] **Step 2: 写实现**

```python
# /dataspace/kqspace/MCPsys/services/gateway/src/gateway/proxy.py
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
```

- [ ] **Step 3: 运行测试**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv run --package gateway pytest services/gateway/tests/test_proxy.py -v
```
Expected: `3 passed`。

- [ ] **Step 4: 提交**

```bash
git add services/gateway && git commit -m "feat(gateway): add httpx-based MCP proxy with timeout handling"
```

---

### Task 16: Telemetry 批量写入器

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/gateway/src/gateway/telemetry.py`
- Create: `/dataspace/kqspace/MCPsys/services/gateway/tests/test_telemetry.py`

- [ ] **Step 1: 写测试**

```python
# /dataspace/kqspace/MCPsys/services/gateway/tests/test_telemetry.py
import asyncio

import pytest
from sqlalchemy import func, select

from mcpsys_shared.models import CallLog, CallStatus

from gateway.telemetry import CallLogEntry, TelemetryWriter


def make_entry(service_id: int, status: CallStatus = CallStatus.success) -> CallLogEntry:
    return CallLogEntry(
        api_key_id=1,
        application_id=2,
        user_id=None,
        service_id=service_id,
        service_version=None,
        tool_name="echo",
        request_id="42",
        status=status,
        http_status=200,
        error_code=None,
        error_message=None,
        duration_ms=12,
        request_bytes=10,
        response_bytes=20,
        request_body='{"a":1}',
        response_body='{"b":2}',
        client_ip="127.0.0.1",
    )


async def _count(session_factory) -> int:
    async with session_factory() as s:
        res = await s.execute(select(func.count()).select_from(CallLog))
        return res.scalar_one()


async def test_writes_after_batch_size(session_factory):
    w = TelemetryWriter(session_factory=session_factory, batch_size=3, flush_interval=10)
    await w.start()
    try:
        for _ in range(3):
            await w.enqueue(make_entry(service_id=1))
        # give the loop a tick
        await asyncio.sleep(0.2)
        assert await _count(session_factory) == 3
    finally:
        await w.stop()


async def test_writes_after_interval(session_factory):
    w = TelemetryWriter(session_factory=session_factory, batch_size=100, flush_interval=0.2)
    await w.start()
    try:
        await w.enqueue(make_entry(service_id=2))
        await asyncio.sleep(0.5)
        # at least the one we enqueued should be flushed by now
        assert await _count(session_factory) >= 1
    finally:
        await w.stop()


async def test_stop_flushes_pending(session_factory):
    w = TelemetryWriter(session_factory=session_factory, batch_size=100, flush_interval=10)
    await w.start()
    await w.enqueue(make_entry(service_id=3))
    await w.stop()
    # after stop(), enqueued items must be persisted
    async with session_factory() as s:
        res = await s.execute(
            select(func.count()).select_from(CallLog).where(CallLog.service_id == 3)
        )
        assert res.scalar_one() == 1
```

- [ ] **Step 2: 写实现**

```python
# /dataspace/kqspace/MCPsys/services/gateway/src/gateway/telemetry.py
import asyncio
import logging
from dataclasses import asdict, dataclass

from sqlalchemy.ext.asyncio import async_sessionmaker

from mcpsys_shared.models import CallLog, CallStatus

logger = logging.getLogger(__name__)


@dataclass
class CallLogEntry:
    api_key_id: int | None
    application_id: int | None
    user_id: int | None
    service_id: int
    service_version: str | None
    tool_name: str | None
    request_id: str | None
    status: CallStatus
    http_status: int | None
    error_code: str | None
    error_message: str | None
    duration_ms: int
    request_bytes: int | None
    response_bytes: int | None
    request_body: str | None
    response_body: str | None
    client_ip: str | None


class TelemetryWriter:
    """In-memory queue + background flusher.

    Trade-off: small risk of log loss on hard crash; kept for main-path latency.
    Writes are batched by size or interval, whichever comes first.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker,
        batch_size: int = 100,
        flush_interval: float = 1.0,
    ) -> None:
        self._sf = session_factory
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._queue: asyncio.Queue[CallLogEntry] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="telemetry-flusher")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def enqueue(self, entry: CallLogEntry) -> None:
        await self._queue.put(entry)

    async def _run(self) -> None:
        while not self._stopping.is_set():
            batch = await self._collect_batch()
            if batch:
                await self._flush(batch)
        # drain remaining
        remaining: list[CallLogEntry] = []
        while not self._queue.empty():
            remaining.append(self._queue.get_nowait())
        if remaining:
            await self._flush(remaining)

    async def _collect_batch(self) -> list[CallLogEntry]:
        deadline = asyncio.get_running_loop().time() + self._flush_interval
        batch: list[CallLogEntry] = []
        while len(batch) < self._batch_size:
            timeout = max(0.0, deadline - asyncio.get_running_loop().time())
            if timeout == 0.0 and batch:
                break
            try:
                if self._stopping.is_set():
                    # short timeout to drain quickly
                    timeout = min(timeout, 0.05)
                item = await asyncio.wait_for(self._queue.get(), timeout=timeout or 0.05)
                batch.append(item)
            except asyncio.TimeoutError:
                break
        return batch

    async def _flush(self, batch: list[CallLogEntry]) -> None:
        rows = []
        for e in batch:
            data = asdict(e)
            # asdict converts CallStatus enum to its value; restore for ORM
            data["status"] = e.status
            rows.append(CallLog(**data))
        try:
            async with self._sf() as session:
                session.add_all(rows)
                await session.commit()
        except Exception as ex:  # log loss is acceptable per design (NFR §7)
            logger.error("telemetry flush failed: %s (dropped %d entries)", ex, len(rows))
```

- [ ] **Step 3: 运行测试**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv run --package gateway pytest services/gateway/tests/test_telemetry.py -v
```
Expected: `3 passed`。

- [ ] **Step 4: 提交**

```bash
git add services/gateway && git commit -m "feat(gateway): add batched telemetry writer"
```

---

### Task 17: 把所有部件接到 `/mcp/{slug}` 端点

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/gateway/src/gateway/routers/__init__.py`
- Create: `/dataspace/kqspace/MCPsys/services/gateway/src/gateway/routers/mcp.py`
- Modify: `/dataspace/kqspace/MCPsys/services/gateway/src/gateway/main.py`
- Create: `/dataspace/kqspace/MCPsys/services/gateway/tests/test_mcp_endpoint.py`

- [ ] **Step 1: 写 router**

```python
# /dataspace/kqspace/MCPsys/services/gateway/src/gateway/routers/__init__.py
```

```python
# /dataspace/kqspace/MCPsys/services/gateway/src/gateway/routers/mcp.py
import json
import uuid

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from mcpsys_shared.models import CallStatus

from ..auth import AuthError, validate_api_key
from ..proxy import ProxyTimeout, forward
from ..resolver import ServiceNotFound
from ..settings import settings
from ..telemetry import CallLogEntry

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _truncate(b: bytes | None, limit: int) -> str | None:
    if b is None:
        return None
    if len(b) <= limit:
        try:
            return b.decode("utf-8", errors="replace")
        except Exception:
            return None
    head = b[:limit]
    return head.decode("utf-8", errors="replace") + f"\n...[truncated {len(b) - limit} bytes]"


def _extract_method_and_id(body: bytes) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(body)
    except (ValueError, json.JSONDecodeError):
        return None, None
    if not isinstance(payload, dict):
        return None, None
    method = payload.get("method")
    if method == "tools/call":
        params = payload.get("params") or {}
        method = f"tools/call:{params.get('name')}" if isinstance(params, dict) else method
    rid = payload.get("id")
    return method, str(rid) if rid is not None else None


@router.post("/{slug}")
async def proxy_mcp(
    slug: str,
    request: Request,
    response: Response,
    authorization: str | None = Header(default=None),
) -> Response:
    request_id = str(uuid.uuid4())
    body = await request.body()
    client_ip = request.client.host if request.client else None
    tool_label, jsonrpc_id = _extract_method_and_id(body)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    plaintext = authorization.split(None, 1)[1].strip()

    sf = request.app.state.session_factory
    redis = request.app.state.redis
    resolver = request.app.state.resolver
    http = request.app.state.http
    telemetry = request.app.state.telemetry

    # 1. authn
    try:
        resolved_key = await validate_api_key(
            plaintext,
            session_factory=sf,
            redis=redis,
            ttl_seconds=settings.api_key_cache_ttl_seconds,
        )
    except AuthError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e

    # 2. resolve
    try:
        svc = await resolver.resolve(slug)
    except ServiceNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"service not found: {slug}") from e

    # 3. authz: MVP only checks key is active (already enforced in step 1)

    # 4. forward
    extra = {
        "x-request-id": request_id,
        "x-mcpsys-application": str(resolved_key.application_id or ""),
        "x-mcpsys-user": str(resolved_key.user_id or ""),
    }
    call_status = CallStatus.success
    http_status: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    proxy_body: bytes = b""
    duration_ms = 0
    try:
        result = await forward(
            client=http,
            upstream_url=svc.endpoint_url,
            body=body,
            headers=dict(request.headers),
            extra_headers=extra,
        )
        http_status = result.status
        proxy_body = result.body
        duration_ms = result.duration_ms
        if result.status >= 500:
            call_status = CallStatus.error
            error_code = f"upstream_{result.status}"
        elif result.status >= 400:
            call_status = CallStatus.error
            error_code = f"client_{result.status}"
        response_obj = Response(
            content=result.body,
            status_code=result.status,
            headers={
                k: v
                for k, v in result.headers.items()
                if k.lower() not in {"content-length", "transfer-encoding", "connection"}
            },
            media_type=result.headers.get("content-type"),
        )
    except ProxyTimeout as e:
        call_status = CallStatus.timeout
        http_status = 504
        error_code = "timeout"
        error_message = str(e)
        response_obj = Response(
            content=json.dumps({"error": {"code": "timeout", "message": str(e)}}).encode(),
            status_code=504,
            media_type="application/json",
        )
    except Exception as e:
        call_status = CallStatus.error
        http_status = 502
        error_code = "proxy_error"
        error_message = str(e)
        response_obj = Response(
            content=json.dumps({"error": {"code": "proxy_error", "message": str(e)}}).encode(),
            status_code=502,
            media_type="application/json",
        )

    # 5. telemetry (fire and forget)
    entry = CallLogEntry(
        api_key_id=resolved_key.api_key_id,
        application_id=resolved_key.application_id,
        user_id=resolved_key.user_id,
        service_id=svc.service_id,
        service_version=None,
        tool_name=tool_label,
        request_id=jsonrpc_id or request_id,
        status=call_status,
        http_status=http_status,
        error_code=error_code,
        error_message=error_message,
        duration_ms=duration_ms,
        request_bytes=len(body),
        response_bytes=len(proxy_body),
        request_body=_truncate(body, settings.body_log_max_bytes),
        response_body=_truncate(proxy_body, settings.body_log_max_bytes),
        client_ip=client_ip,
    )
    await telemetry.enqueue(entry)

    response_obj.headers["x-request-id"] = request_id
    return response_obj
```

- [ ] **Step 2: 更新 main.py 把 redis / resolver / telemetry 接进 lifespan**

```python
# /dataspace/kqspace/MCPsys/services/gateway/src/gateway/main.py
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from redis.asyncio import Redis

from mcpsys_shared.db import make_engine, make_session_factory

from .resolver import ServiceResolver
from .routers import mcp as mcp_router
from .settings import settings
from .telemetry import TelemetryWriter


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = make_engine(settings.database_url)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.state.http = httpx.AsyncClient(timeout=settings.proxy_timeout_seconds)
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.resolver = ServiceResolver(
        session_factory=app.state.session_factory,
        ttl_seconds=settings.service_cache_ttl_seconds,
    )
    app.state.telemetry = TelemetryWriter(
        session_factory=app.state.session_factory,
        batch_size=settings.telemetry_batch_size,
        flush_interval=settings.telemetry_flush_interval_seconds,
    )
    await app.state.telemetry.start()
    try:
        yield
    finally:
        await app.state.telemetry.stop()
        await app.state.http.aclose()
        await app.state.redis.aclose()
        await app.state.engine.dispose()


app = FastAPI(title="MCPsys Gateway", version="0.1.0", lifespan=lifespan)
app.include_router(mcp_router.router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 3: 更新 conftest.py 注入 redis / resolver / telemetry**

替换 `/dataspace/kqspace/MCPsys/services/gateway/tests/conftest.py` 中 `app` fixture 为：

```python
@pytest.fixture
async def app(engine, session_factory, redis_url):
    from redis.asyncio import Redis

    from gateway.main import app as fastapi_app
    from gateway.resolver import ServiceResolver
    from gateway.telemetry import TelemetryWriter

    fastapi_app.state.engine = engine
    fastapi_app.state.session_factory = session_factory
    fastapi_app.state.http = httpx.AsyncClient()
    fastapi_app.state.redis = Redis.from_url(redis_url, decode_responses=True)
    await fastapi_app.state.redis.flushdb()
    fastapi_app.state.resolver = ServiceResolver(session_factory=session_factory, ttl_seconds=60)
    fastapi_app.state.telemetry = TelemetryWriter(
        session_factory=session_factory, batch_size=10, flush_interval=0.1
    )
    await fastapi_app.state.telemetry.start()
    yield fastapi_app
    await fastapi_app.state.telemetry.stop()
    await fastapi_app.state.redis.aclose()
```

并把 `client` fixture 末尾的 `await app.state.http.aclose()` 保留。

- [ ] **Step 4: 写端到端 mcp 端点测试（用 respx 拦截上游）**

```python
# /dataspace/kqspace/MCPsys/services/gateway/tests/test_mcp_endpoint.py
import asyncio
import json

import bcrypt
import pytest
import respx
from httpx import Response as HxResponse
from sqlalchemy import func, select

from mcpsys_shared.models import (
    ApiKey,
    ApiKeyOwnerType,
    Application,
    CallLog,
    McpService,
    ServiceStatus,
    TransportType,
    User,
    UserRole,
)


@pytest.fixture
async def seed(session_factory):
    async with session_factory() as s:
        u = User(username="agent-owner", role=UserRole.viewer)
        s.add(u)
        await s.flush()
        a = Application(name="agent-z", owner_user_id=u.id)
        s.add(a)
        await s.flush()
        plain = "mcpk_e2etestkey_zzz"
        k = ApiKey(
            name="e2e",
            key_prefix=plain[5:13],
            key_hash=bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode(),
            owner_type=ApiKeyOwnerType.application,
            owner_id=a.id,
        )
        s.add(k)
        svc = McpService(
            slug="echo",
            display_name="Echo",
            endpoint_url="http://upstream-echo/mcp",
            transport=TransportType.streamable_http,
            status=ServiceStatus.active,
        )
        s.add(svc)
        await s.commit()
        await s.refresh(svc)
        return plain, svc.id


@respx.mock
async def test_proxy_success_path(client, seed, session_factory):
    plain, svc_id = seed
    upstream = respx.post("http://upstream-echo/mcp").respond(
        200, json={"jsonrpc": "2.0", "result": {"echo": "hi"}, "id": 7}
    )
    resp = await client.post(
        "/mcp/echo",
        headers={"Authorization": f"Bearer {plain}", "content-type": "application/json"},
        content=json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "echo", "arguments": {"msg": "hi"}},
                "id": 7,
            }
        ),
    )
    assert resp.status_code == 200
    assert resp.json()["result"]["echo"] == "hi"
    assert upstream.called
    assert resp.headers.get("x-request-id")

    # wait briefly for telemetry flush
    await asyncio.sleep(0.3)
    async with session_factory() as s:
        n = (
            await s.execute(
                select(func.count()).select_from(CallLog).where(CallLog.service_id == svc_id)
            )
        ).scalar_one()
        assert n == 1


async def test_missing_auth_returns_401(client):
    resp = await client.post("/mcp/echo", content=b"{}")
    assert resp.status_code == 401


async def test_unknown_service_returns_404(client, seed):
    plain, _ = seed
    resp = await client.post(
        "/mcp/no-such-service",
        headers={"Authorization": f"Bearer {plain}"},
        content=b"{}",
    )
    assert resp.status_code == 404


@respx.mock
async def test_upstream_5xx_passes_through_and_logged_as_error(client, seed, session_factory):
    plain, svc_id = seed
    respx.post("http://upstream-echo/mcp").mock(return_value=HxResponse(503, text="busy"))
    resp = await client.post(
        "/mcp/echo",
        headers={"Authorization": f"Bearer {plain}", "content-type": "application/json"},
        content=b'{"jsonrpc":"2.0","method":"tools/list","id":1}',
    )
    assert resp.status_code == 503
    await asyncio.sleep(0.3)
    async with session_factory() as s:
        from mcpsys_shared.models import CallStatus
        res = await s.execute(
            select(CallLog).where(CallLog.service_id == svc_id, CallLog.http_status == 503)
        )
        log = res.scalars().first()
        assert log is not None
        assert log.status == CallStatus.error
```

- [ ] **Step 5: 运行测试**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv run --package gateway pytest services/gateway/tests/test_mcp_endpoint.py -v
```
Expected: `4 passed`。

- [ ] **Step 6: 提交**

```bash
git add services/gateway && git commit -m "feat(gateway): wire /mcp/{slug} endpoint with full auth+proxy+telemetry"
```

---

## 阶段四：监控查询、Grafana、部署（T18–T22）

### Task 18: Control Plane 调用日志查询端点

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/routers/call_logs.py`
- Modify: `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/main.py`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/tests/test_call_logs.py`

- [ ] **Step 1: 写测试**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/tests/test_call_logs.py
from datetime import UTC, datetime, timedelta

import pytest

from mcpsys_shared.models import (
    CallLog,
    CallStatus,
    McpService,
    ServiceStatus,
    TransportType,
    User,
    UserRole,
    UserStatus,
)

from control_plane.security import encode_jwt, hash_password
from control_plane.settings import settings


@pytest.fixture
async def viewer(session_factory):
    async with session_factory() as s:
        u = User(
            username="logs-viewer",
            password_hash=hash_password("p"),
            role=UserRole.viewer,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


@pytest.fixture
async def seeded_logs(session_factory):
    async with session_factory() as s:
        svc = McpService(
            slug="logs-svc",
            display_name="LS",
            endpoint_url="http://x/mcp",
            transport=TransportType.streamable_http,
            status=ServiceStatus.active,
        )
        s.add(svc)
        await s.flush()
        now = datetime.now(UTC)
        for i in range(5):
            s.add(
                CallLog(
                    ts=now - timedelta(minutes=i),
                    service_id=svc.id,
                    status=CallStatus.success if i % 2 == 0 else CallStatus.error,
                    duration_ms=10 + i,
                )
            )
        await s.commit()
        return svc.id


def auth_header(user):
    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value},
        secret=settings.jwt_secret,
        expires_minutes=5,
    )
    return {"Authorization": f"Bearer {token}"}


async def test_list_logs(client, viewer, seeded_logs):
    resp = await client.get(
        f"/api/v1/call-logs?service_id={seeded_logs}",
        headers=auth_header(viewer),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 5


async def test_filter_by_status(client, viewer, seeded_logs):
    resp = await client.get(
        f"/api/v1/call-logs?service_id={seeded_logs}&status=error",
        headers=auth_header(viewer),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert all(i["status"] == "error" for i in body["items"])


async def test_pagination(client, viewer, seeded_logs):
    resp = await client.get(
        f"/api/v1/call-logs?service_id={seeded_logs}&limit=2",
        headers=auth_header(viewer),
    )
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5
```

- [ ] **Step 2: 写实现**

```python
# /dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/routers/call_logs.py
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpsys_shared.models import CallLog, CallStatus

from ..deps import get_db, require_role

router = APIRouter(prefix="/api/v1/call-logs", tags=["call-logs"])


class CallLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    ts: datetime
    api_key_id: int | None
    application_id: int | None
    user_id: int | None
    service_id: int
    tool_name: str | None
    status: CallStatus
    http_status: int | None
    error_code: str | None
    duration_ms: int
    request_bytes: int | None
    response_bytes: int | None


class CallLogList(BaseModel):
    items: list[CallLogOut]
    total: int


@router.get(
    "",
    response_model=CallLogList,
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)
async def list_call_logs(
    db: AsyncSession = Depends(get_db),
    service_id: int | None = Query(default=None),
    application_id: int | None = Query(default=None),
    api_key_id: int | None = Query(default=None),
    status_filter: CallStatus | None = Query(default=None, alias="status"),
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> CallLogList:
    where = []
    if service_id is not None:
        where.append(CallLog.service_id == service_id)
    if application_id is not None:
        where.append(CallLog.application_id == application_id)
    if api_key_id is not None:
        where.append(CallLog.api_key_id == api_key_id)
    if status_filter is not None:
        where.append(CallLog.status == status_filter)
    if from_ts is not None:
        where.append(CallLog.ts >= from_ts)
    if to_ts is not None:
        where.append(CallLog.ts <= to_ts)

    total_q = select(func.count()).select_from(CallLog)
    items_q = select(CallLog).order_by(CallLog.ts.desc())
    for w in where:
        total_q = total_q.where(w)
        items_q = items_q.where(w)

    total = (await db.execute(total_q)).scalar_one()
    items = (await db.execute(items_q.limit(limit).offset(offset))).scalars().all()
    return CallLogList(items=[CallLogOut.model_validate(i) for i in items], total=total)
```

- [ ] **Step 3: 注册 router**

编辑 `/dataspace/kqspace/MCPsys/services/control_plane/src/control_plane/main.py`，update imports：
```python
from .routers import (
    api_keys as api_keys_router,
    applications as applications_router,
    auth as auth_router,
    call_logs as call_logs_router,
    services as services_router,
    users as users_router,
)
```
追加：
```python
app.include_router(call_logs_router.router)
```

- [ ] **Step 4: 运行测试**

Run:
```bash
cd /dataspace/kqspace/MCPsys && uv run --package control-plane pytest services/control_plane/tests/test_call_logs.py -v
```
Expected: `3 passed`。

- [ ] **Step 5: 提交**

```bash
git add services/control_plane && git commit -m "feat(control_plane): add call logs query endpoint with filters and pagination"
```

---

### Task 19: Grafana 自动 Provisioning（数据源 + 仪表盘）

**Files:**
- Create: `/dataspace/kqspace/MCPsys/grafana/provisioning/datasources/postgres.yaml`
- Create: `/dataspace/kqspace/MCPsys/grafana/provisioning/dashboards/dashboards.yaml`
- Create: `/dataspace/kqspace/MCPsys/grafana/provisioning/dashboards/mcp-overview.json`

- [ ] **Step 1: 数据源**

```yaml
# /dataspace/kqspace/MCPsys/grafana/provisioning/datasources/postgres.yaml
apiVersion: 1
datasources:
  - name: MCPsys Postgres
    type: postgres
    access: proxy
    url: postgres:5432
    database: ${POSTGRES_DB}
    user: ${POSTGRES_USER}
    secureJsonData:
      password: ${POSTGRES_PASSWORD}
    jsonData:
      sslmode: disable
      postgresVersion: 1600
      timescaledb: false
    isDefault: true
```

- [ ] **Step 2: dashboard provider**

```yaml
# /dataspace/kqspace/MCPsys/grafana/provisioning/dashboards/dashboards.yaml
apiVersion: 1
providers:
  - name: mcpsys
    folder: MCPsys
    type: file
    options:
      path: /etc/grafana/provisioning/dashboards
```

- [ ] **Step 3: 仪表盘 JSON（3 个面板：总调用、错误率、Top 服务）**

```json
{
  "title": "MCP Overview",
  "schemaVersion": 39,
  "version": 1,
  "refresh": "30s",
  "time": { "from": "now-24h", "to": "now" },
  "panels": [
    {
      "id": 1,
      "type": "stat",
      "title": "Total calls (24h)",
      "gridPos": { "h": 5, "w": 6, "x": 0, "y": 0 },
      "datasource": { "type": "postgres", "uid": "mcpsys-postgres" },
      "targets": [
        {
          "format": "table",
          "rawQuery": true,
          "rawSql": "SELECT count(*) AS value FROM call_logs WHERE ts > now() - interval '24 hours';"
        }
      ]
    },
    {
      "id": 2,
      "type": "stat",
      "title": "Error rate (24h)",
      "gridPos": { "h": 5, "w": 6, "x": 6, "y": 0 },
      "datasource": { "type": "postgres", "uid": "mcpsys-postgres" },
      "fieldConfig": { "defaults": { "unit": "percentunit" } },
      "targets": [
        {
          "format": "table",
          "rawQuery": true,
          "rawSql": "SELECT (count(*) FILTER (WHERE status != 'success'))::float / NULLIF(count(*),0) AS value FROM call_logs WHERE ts > now() - interval '24 hours';"
        }
      ]
    },
    {
      "id": 3,
      "type": "barchart",
      "title": "Top services by calls (24h)",
      "gridPos": { "h": 9, "w": 12, "x": 0, "y": 5 },
      "datasource": { "type": "postgres", "uid": "mcpsys-postgres" },
      "targets": [
        {
          "format": "table",
          "rawQuery": true,
          "rawSql": "SELECT s.slug AS service, count(*) AS calls FROM call_logs c JOIN mcp_services s ON s.id = c.service_id WHERE c.ts > now() - interval '24 hours' GROUP BY s.slug ORDER BY calls DESC LIMIT 10;"
        }
      ]
    },
    {
      "id": 4,
      "type": "timeseries",
      "title": "Calls per minute (24h)",
      "gridPos": { "h": 9, "w": 24, "x": 0, "y": 14 },
      "datasource": { "type": "postgres", "uid": "mcpsys-postgres" },
      "targets": [
        {
          "format": "time_series",
          "rawQuery": true,
          "rawSql": "SELECT date_trunc('minute', ts) AS time, count(*) AS calls FROM call_logs WHERE ts > now() - interval '24 hours' GROUP BY 1 ORDER BY 1;"
        }
      ]
    }
  ]
}
```

把上面的 JSON 写入 `/dataspace/kqspace/MCPsys/grafana/provisioning/dashboards/mcp-overview.json`。

> 注：仪表盘 datasource 的 `uid` 与数据源文件中名称的关系由 Grafana 自动生成；首次加载后可在 UI 校准。手动设置 `uid` 见步骤 4。

- [ ] **Step 4: 在数据源 yaml 增加显式 `uid` 与 dashboard 对齐**

编辑 `/dataspace/kqspace/MCPsys/grafana/provisioning/datasources/postgres.yaml`，在 `name:` 下方加：
```yaml
    uid: mcpsys-postgres
```

- [ ] **Step 5: 提交**

```bash
git add grafana && git commit -m "feat(grafana): add postgres datasource and overview dashboard provisioning"
```

> 这一任务无单元测试；T22 的 e2e smoke 会通过 `curl http://localhost:3000` 间接验证。

---

### Task 20: Nginx 反向代理配置

**Files:**
- Create: `/dataspace/kqspace/MCPsys/nginx/nginx.conf`

- [ ] **Step 1: 写 nginx.conf**

```nginx
# /dataspace/kqspace/MCPsys/nginx/nginx.conf
user nginx;
worker_processes auto;
events { worker_connections 1024; }

http {
    sendfile on;
    keepalive_timeout 65;

    upstream gateway_upstream {
        server gateway:8080;
        # docker compose --scale gateway=N will register additional addrs via DNS
        # nginx resolves "gateway" to all replicas at startup; for dynamic scaling use
        # nginx-plus or sidecar.
    }

    upstream control_plane_upstream {
        server control-plane:8000;
    }

    server {
        listen 80 default_server;
        server_name _;

        client_max_body_size 10m;

        # MCP traffic → gateway
        location /mcp/ {
            proxy_pass http://gateway_upstream;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_buffering off;          # streaming responses
            proxy_read_timeout 300s;
            proxy_send_timeout 300s;
        }

        # Gateway healthz (for ops)
        location /gw/healthz {
            proxy_pass http://gateway_upstream/healthz;
        }

        # Control Plane API + healthz
        location /api/ {
            proxy_pass http://control_plane_upstream;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }

        location /healthz {
            proxy_pass http://control_plane_upstream/healthz;
        }

        # Grafana (admin only — protect via SSO/basic-auth in prod)
        location /grafana/ {
            proxy_pass http://grafana:3000/;
            proxy_set_header Host $host;
        }
    }
}
```

- [ ] **Step 2: 提交**

```bash
git add nginx && git commit -m "feat(nginx): add reverse proxy config routing /mcp,/api,/grafana"
```

---

### Task 21: Dockerfile + 完整 compose.yaml

**Files:**
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/Dockerfile`
- Create: `/dataspace/kqspace/MCPsys/services/gateway/Dockerfile`
- Create: `/dataspace/kqspace/MCPsys/services/control_plane/entrypoint.sh`
- Modify: `/dataspace/kqspace/MCPsys/compose.yaml`

- [ ] **Step 1: control-plane Dockerfile**

```dockerfile
# /dataspace/kqspace/MCPsys/services/control_plane/Dockerfile
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir uv==0.4.18

WORKDIR /app
# Copy workspace metadata first for layer caching
COPY pyproject.toml uv.lock /app/
COPY packages /app/packages
COPY services/control_plane /app/services/control_plane

RUN uv sync --frozen --package control-plane --no-dev
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app/services/control_plane
COPY services/control_plane/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "control_plane.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: control-plane entrypoint（先跑 alembic upgrade）**

```bash
# /dataspace/kqspace/MCPsys/services/control_plane/entrypoint.sh
#!/bin/sh
set -e
echo "[entrypoint] running alembic upgrade head"
alembic upgrade head
exec "$@"
```

- [ ] **Step 3: gateway Dockerfile**

```dockerfile
# /dataspace/kqspace/MCPsys/services/gateway/Dockerfile
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir uv==0.4.18

WORKDIR /app
COPY pyproject.toml uv.lock /app/
COPY packages /app/packages
COPY services/gateway /app/services/gateway

RUN uv sync --frozen --package gateway --no-dev
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080
CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 4: 在 compose.yaml 增加应用 + nginx + grafana**

完全替换 `/dataspace/kqspace/MCPsys/compose.yaml` 为：

```yaml
# /dataspace/kqspace/MCPsys/compose.yaml
name: mcpsys

x-app-env: &app-env
  POSTGRES_USER: ${POSTGRES_USER}
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  POSTGRES_DB: ${POSTGRES_DB}
  POSTGRES_HOST: postgres
  POSTGRES_PORT: 5432
  REDIS_HOST: redis
  REDIS_PORT: 6379
  LOG_LEVEL: ${LOG_LEVEL}

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "${POSTGRES_USER}", "-d", "${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    command: ["redis-server", "--appendonly", "yes"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 10

  control-plane:
    build:
      context: .
      dockerfile: services/control_plane/Dockerfile
    environment:
      <<: *app-env
      JWT_SECRET: ${JWT_SECRET}
      JWT_EXPIRES_MINUTES: ${JWT_EXPIRES_MINUTES}
      CONFIG_FERNET_KEY: ${CONFIG_FERNET_KEY}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"]
      interval: 10s
      timeout: 5s
      retries: 5

  gateway:
    build:
      context: .
      dockerfile: services/gateway/Dockerfile
    environment:
      <<: *app-env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      control-plane:
        condition: service_healthy
    deploy:
      replicas: ${GATEWAY_REPLICAS}

  grafana:
    image: grafana/grafana:10.4.5
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD}
      GF_SERVER_ROOT_URL: "%(protocol)s://%(domain)s/grafana/"
      GF_SERVER_SERVE_FROM_SUB_PATH: "true"
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
    depends_on:
      postgres:
        condition: service_healthy

  nginx:
    image: nginx:1.27-alpine
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    ports:
      - "80:80"
    depends_on:
      - control-plane
      - gateway
      - grafana

volumes:
  postgres-data:
  redis-data:
  grafana-data:
```

- [ ] **Step 5: 构建 + 启动**

Run:
```bash
cd /dataspace/kqspace/MCPsys && docker compose build && docker compose up -d
```
Expected: 所有服务最终 `Started`，约 30–60s 内 control-plane / gateway 通过健康检查。

- [ ] **Step 6: 验证端点**

Run:
```bash
curl -s http://localhost/healthz
curl -s http://localhost/gw/healthz
curl -sI http://localhost/grafana/login
```
Expected: 前两个 `{"status":"ok"}`；第三个 `200 OK` 或 `302`。

- [ ] **Step 7: 提交**

```bash
git add services/control_plane/Dockerfile services/control_plane/entrypoint.sh \
        services/gateway/Dockerfile compose.yaml && \
  git commit -m "feat: add Dockerfiles and full compose.yaml with nginx + grafana"
```

---

### Task 22: 端到端 smoke 测试 + README

**Files:**
- Create: `/dataspace/kqspace/MCPsys/scripts/smoke.sh`
- Create: `/dataspace/kqspace/MCPsys/scripts/seed_admin.py`
- Modify: `/dataspace/kqspace/MCPsys/README.md`

- [ ] **Step 1: 写 admin 种子脚本（首次启动后创建一个 admin 用户）**

```python
# /dataspace/kqspace/MCPsys/scripts/seed_admin.py
"""Bootstrap an initial admin user. Idempotent.

Usage (inside control-plane container):
    python scripts/seed_admin.py admin SuperSecret123
"""
import asyncio
import sys

from sqlalchemy import select

from mcpsys_shared.db import make_engine, make_session_factory
from mcpsys_shared.models import User, UserRole, UserStatus
from mcpsys_shared.settings import SharedSettings

from control_plane.security import hash_password


async def main(username: str, password: str) -> None:
    engine = make_engine(SharedSettings().database_url)
    sf = make_session_factory(engine)
    async with sf() as s:
        existing = (await s.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if existing is not None:
            print(f"user {username!r} already exists, skipping")
            return
        s.add(
            User(
                username=username,
                password_hash=hash_password(password),
                role=UserRole.admin,
                status=UserStatus.active,
            )
        )
        await s.commit()
        print(f"created admin {username!r}")
    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python scripts/seed_admin.py <username> <password>", file=sys.stderr)
        sys.exit(2)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
```

- [ ] **Step 2: 写 smoke 脚本**

```bash
# /dataspace/kqspace/MCPsys/scripts/smoke.sh
#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://localhost}"
USERNAME="${USERNAME:-admin}"
PASSWORD="${PASSWORD:-SuperSecret123}"

echo "[smoke] healthz"
curl -fsS "$BASE/healthz" | grep -q '"ok"'

echo "[smoke] login"
TOKEN=$(curl -fsS -X POST "$BASE/api/v1/auth/login" \
    -H "content-type: application/x-www-form-urlencoded" \
    --data-urlencode "username=$USERNAME" --data-urlencode "password=$PASSWORD" \
    | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "got token: ${TOKEN:0:20}..."

echo "[smoke] create application"
curl -fsS -X POST "$BASE/api/v1/applications" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"name":"smoke-app"}' >/dev/null || true

echo "[smoke] register service"
curl -fsS -X POST "$BASE/api/v1/services" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"slug":"smoke-svc","display_name":"Smoke","endpoint_url":"http://httpbin.org/anything"}' >/dev/null || true

echo "[smoke] issue api key"
APIKEY=$(curl -fsS -X POST "$BASE/api/v1/api-keys" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"name":"smoke","owner_type":"application","owner_id":1}' \
    | python -c "import sys,json; print(json.load(sys.stdin)['plaintext'])")
echo "got api key: ${APIKEY:0:12}..."

echo "[smoke] proxy through gateway"
curl -fsS -X POST "$BASE/mcp/smoke-svc" \
    -H "Authorization: Bearer $APIKEY" -H "content-type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' >/dev/null

echo "[smoke] query call logs"
curl -fsS "$BASE/api/v1/call-logs?limit=5" \
    -H "Authorization: Bearer $TOKEN" | python -m json.tool | head -20

echo "[smoke] OK"
```

设置可执行：
```bash
chmod +x /dataspace/kqspace/MCPsys/scripts/smoke.sh
```

- [ ] **Step 3: 更新 README**

替换 `/dataspace/kqspace/MCPsys/README.md` 为：

````markdown
# MCPsys

Internal MCP (Model Context Protocol) service management system.

- Spec: `docs/specs/2026-04-30-mcp-management-system-design.md`
- MVP plan: `docs/plans/2026-04-30-mcp-management-mvp-plan.md`

## Quick start

```bash
cp .env.example .env
# edit .env: set strong JWT_SECRET and CONFIG_FERNET_KEY (generate with:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

docker compose build
docker compose up -d

# wait ~30s for healthchecks, then create the initial admin user
docker compose exec control-plane python scripts/seed_admin.py admin SuperSecret123

# run end-to-end smoke
./scripts/smoke.sh
```

Endpoints:

| URL | Purpose |
|---|---|
| `http://localhost/healthz` | Control-plane health |
| `http://localhost/gw/healthz` | Gateway health |
| `http://localhost/api/v1/...` | Management API (JWT) |
| `http://localhost/mcp/{slug}` | MCP traffic gateway (API Key) |
| `http://localhost/grafana/` | Monitoring dashboard |

## Development

```bash
# install workspace
uv sync

# run tests for a specific package
uv run --package control-plane pytest services/control_plane/tests
uv run --package gateway        pytest services/gateway/tests
uv run --package mcpsys-shared  pytest packages/mcpsys_shared/tests
```

## Architecture

See `docs/specs/2026-04-30-mcp-management-system-design.md` §2 for the architecture diagram.
````

- [ ] **Step 4: 跑 smoke**

Run:
```bash
cd /dataspace/kqspace/MCPsys && \
  docker compose exec control-plane python scripts/seed_admin.py admin SuperSecret123 && \
  ./scripts/smoke.sh
```
Expected: 输出以 `[smoke] OK` 结尾。

- [ ] **Step 5: 跑全量 pytest 一次确认无回归**

Run:
```bash
cd /dataspace/kqspace/MCPsys && \
  uv run --package mcpsys-shared pytest packages/mcpsys_shared/tests && \
  uv run --package control-plane pytest services/control_plane/tests && \
  uv run --package gateway       pytest services/gateway/tests
```
Expected: 三段全部 `passed`。

- [ ] **Step 6: 提交**

```bash
git add scripts README.md && \
  git commit -m "feat: add smoke test and admin bootstrap, document quick start"
```

---

## 验收清单（MVP 完成标准）

执行完 T1–T22 后，逐项手工验证：

- [ ] `docker compose up -d` 一键启动后，所有容器 healthy
- [ ] `scripts/smoke.sh` 全流程通过（登录 → 注册服务 → 签发 key → 通过网关调用 → 查日志）
- [ ] `http://localhost/grafana/` 可登录并看到 "MCP Overview" 仪表盘渲染数据
- [ ] OpenAPI 在 `http://localhost/api/v1/openapi.json` 可访问，前端团队可基于此独立开发
- [ ] `uv run pytest` 三个包共全绿；测试覆盖核心路径（auth、CRUD、proxy、telemetry）
- [ ] 旧 token / 吊销过的 API Key 调用网关返回 401
- [ ] 未注册或 disabled 的 service slug 返回 404
- [ ] 上游 5xx 透传给调用方，且 call_logs 记录 `status=error`

---

## 后续（v1 工作，本计划不涉及）

按 spec §6，下一阶段：

- 细粒度权限 `service_permissions`
- 限流 per-key + per-service（Redis Token Bucket Lua）
- 配置中心 `service_configs`（Fernet 加密 + Redis pub/sub 热下发）
- `audit_events` 全量管理动作记录
- 调用日志详情页（含 body）
- 监控仪表盘扩展（P50/P95/P99 延迟、按调用方分布）
- 服务版本管理 `mcp_service_versions`

每一项都应通过新一轮 brainstorming → spec → plan 流程展开。
