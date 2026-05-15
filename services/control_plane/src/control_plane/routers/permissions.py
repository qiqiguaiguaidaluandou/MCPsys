"""Read-only views over service_permissions.

Grants are managed exclusively from the application side (see routers/applications.py:
create / update). These endpoints just expose the resulting (application × service)
white-list from both directions:
  - GET /services/{slug}/permissions       → who can call this service
  - GET /applications/{id}/permissions      → what this application can call
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from mcpsys_shared.models import McpService, ServicePermission
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db, require_role

router = APIRouter(tags=["permissions"])


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    application_id: int
    service_id: int
    granted_by: int | None
    granted_at: datetime


class PermissionList(BaseModel):
    items: list[PermissionOut]
    total: int


async def _get_service_by_slug(slug: str, db: AsyncSession) -> McpService:
    res = await db.execute(select(McpService).where(McpService.slug == slug))
    svc = res.scalar_one_or_none()
    if svc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "service not found")
    return svc


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
    items = [PermissionOut.model_validate(r) for r in rows]
    return PermissionList(items=items, total=len(items))


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
    items = [PermissionOut.model_validate(r) for r in rows]
    return PermissionList(items=items, total=len(items))
