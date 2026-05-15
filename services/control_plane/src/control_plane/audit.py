"""Audit logging — manages writes to audit_events from control-plane handlers.

See docs/specs/2026-05-11-v1b-audit-events-design.md for the design.
"""
import re
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from fastapi import Request
from mcpsys_shared.models import AuditEvent, Base, User
from sqlalchemy.ext.asyncio import AsyncSession


class Action:
    """All audit action strings, format `target_type.verb`."""
    USER_CREATE          = "user.create"
    USER_DELETE          = "user.delete"
    USER_PASSWORD_CHANGE = "user.password_change"  # noqa: S105 — action string, not a password
    APPLICATION_CREATE   = "application.create"
    APPLICATION_UPDATE   = "application.update"
    API_KEY_ISSUE        = "api_key.issue"
    API_KEY_REVOKE       = "api_key.revoke"
    API_KEY_UPDATE       = "api_key.update"
    API_KEY_DELETE       = "api_key.delete"
    SERVICE_CREATE       = "service.create"
    SERVICE_UPDATE       = "service.update"
    SERVICE_DELETE       = "service.delete"


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
    """落一行 audit_events。同事务原子：不 commit / 不 flush / 不 try-except。

    提交交由 `get_db` 统一 commit；主写失败 → audit 一同回滚；
    audit 写失败 → 主写也回滚（可接受：AuditEvent 无 FK / unique / NOT NULL
    约束冲突来源）。**不要**在此函数内包 try/except——会破坏上述原子语义。
    """
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
