from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from mcpsys_shared.models import Application, McpService, ServicePermission, User
from pydantic import BaseModel, ConfigDict
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import Action, audit_log, model_to_dict
from ..deps import get_db, get_redis, require_role
from ..invalidator import publish_policy_invalidate

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
    granted_at: datetime
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
)
async def grant_permission(
    slug: str,
    payload: PermissionCreate,
    response: Response,
    request: Request,
    current_user: User = Depends(require_role("admin", "operator")),
    db: AsyncSession = Depends(get_db),
    redis: Redis | None = Depends(get_redis),
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
        return PermissionOut.model_validate(existing)

    perm = ServicePermission(
        application_id=payload.application_id,
        service_id=svc.id,
        granted_by=current_user.id,
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
        return PermissionOut.model_validate(existing)

    await db.refresh(perm)
    await audit_log(
        db,
        action=Action.SERVICE_PERMISSION_GRANT,
        target_type="service_permission",
        target_id=str(perm.id),
        before=None,
        after=model_to_dict(perm),
        actor=current_user,
        request=request,
    )
    # commit main write + audit row atomically; publish MUST follow commit (V1-A.1 invariant)
    await db.commit()
    await publish_policy_invalidate(redis, svc.id)
    response.status_code = status.HTTP_201_CREATED
    return PermissionOut.model_validate(perm)


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


@router.delete(
    "/api/v1/services/{slug}/permissions/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_permission(
    slug: str,
    application_id: int,
    request: Request,
    current_user: User = Depends(require_role("admin", "operator")),
    db: AsyncSession = Depends(get_db),
    redis: Redis | None = Depends(get_redis),
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
        before = model_to_dict(row)
        perm_id = row.id  # capture before delete (object becomes detached after delete)
        await db.delete(row)
        await db.flush()
        await audit_log(
            db,
            action=Action.SERVICE_PERMISSION_REVOKE,
            target_type="service_permission",
            target_id=str(perm_id),
            before=before,
            after=None,
            actor=current_user,
            request=request,
        )
        # commit main write + audit row atomically; publish MUST follow commit (V1-A.1 invariant)
        await db.commit()
        await publish_policy_invalidate(redis, svc.id)
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
    items = [PermissionOut.model_validate(r) for r in rows]
    return PermissionList(items=items, total=len(items))
