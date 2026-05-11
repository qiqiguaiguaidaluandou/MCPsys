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
