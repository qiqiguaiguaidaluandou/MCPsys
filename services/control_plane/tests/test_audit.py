from datetime import UTC, datetime
from types import SimpleNamespace

from control_plane.audit import (
    _SENSITIVE_COLUMNS,
    SENSITIVE_PATTERN,
    Action,
    audit_log,
    model_to_dict,
)
from mcpsys_shared.models import AuditEvent, Base, User, UserRole, UserStatus
from sqlalchemy import select


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
    u = User(id=1, username="x", password_hash="bcrypt$$$secret", role=UserRole.viewer)  # noqa: S106 — fake hash for sensitivity-guard test
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


def test_model_to_dict_uuid_to_str():
    """Hit the UUID → str branch in model_to_dict (CallLog.id is UUID)."""
    import uuid

    from mcpsys_shared.models import CallLog, CallStatus

    log_id = uuid.uuid4()
    log = CallLog(
        id=log_id,
        service_id=1,
        status=CallStatus.success,
        duration_ms=10,
    )
    d = model_to_dict(log)
    assert d["id"] == str(log_id)
    assert isinstance(d["id"], str)


def test_model_to_dict_skips_relationships():
    """Relationships must NOT appear in output. Currently impossible via __mapper__.columns,
    but pin the contract so a future refactor doesn't silently leak related objects."""
    u = User(id=1, username="x", role=UserRole.viewer)
    d = model_to_dict(u)
    # User has no relationships defined currently; if any future relationship is added
    # (e.g., applications = relationship("Application", back_populates="owner")),
    # its attribute name must not appear in the dict. This guards against the day
    # model_to_dict is rewritten using inspect(obj).attrs or similar.
    for key in d:
        col_names = {c.name for c in u.__mapper__.columns}
        assert key in col_names, f"{key} 不是 column 字段，疑似关系对象泄露到 audit before/after"
