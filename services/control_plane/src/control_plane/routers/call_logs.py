from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
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


class CallLogDetail(CallLogOut):
    request_id: str | None
    error_message: str | None
    request_body: str | None
    response_body: str | None
    client_ip: str | None


# Restricted to admin/operator: viewer is global-read-only on metadata, but call_logs
# can contain request/response bodies and tool arguments that may be sensitive across
# applications. Per-tenant scoping for viewer is a v1 task (see spec §6).
@router.get(
    "",
    response_model=CallLogList,
    dependencies=[Depends(require_role("admin", "operator"))],
)
async def list_call_logs(
    db: AsyncSession = Depends(get_db),
    service_id: int | None = Query(default=None),
    application_id: int | None = Query(default=None),
    api_key_id: int | None = Query(default=None),
    status_filter: CallStatus | None = Query(default=None, alias="status"),
    tool: str | None = Query(default=None),
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
    if tool is not None and tool != "":
        where.append(CallLog.tool_name == tool)
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


@router.get(
    "/{call_id}",
    response_model=CallLogDetail,
    dependencies=[Depends(require_role("admin", "operator"))],
)
async def get_call_log(
    call_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CallLogDetail:
    row = await db.get(CallLog, call_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "调用日志不存在")
    return CallLogDetail.model_validate(row)
