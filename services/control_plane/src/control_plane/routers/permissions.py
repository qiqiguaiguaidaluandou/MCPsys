from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mcpsys_shared.models import Application, McpService, ServicePermission

from ..deps import get_current_user, get_db, require_role

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


def _serialize(p: ServicePermission) -> dict:
    return {
        "id": p.id,
        "application_id": p.application_id,
        "service_id": p.service_id,
        "granted_by": p.granted_by,
        "granted_at": p.granted_at.isoformat() if p.granted_at else None,
        "note": p.note,
    }


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
    except IntegrityError:
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

    await db.refresh(perm)
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
