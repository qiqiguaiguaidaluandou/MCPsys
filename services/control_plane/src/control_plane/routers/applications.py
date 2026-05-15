from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from mcpsys_shared.models import Application, McpService, ServicePermission, User
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import Action, audit_log, model_to_dict
from ..deps import get_db, get_redis, require_role
from ..invalidator import publish_policy_invalidate

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])


class ApplicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    team: str | None = None
    description: str | None = None
    # 应用可调用的服务 id 列表；驱动 service_permissions 白名单。
    service_ids: list[int] = Field(default_factory=list)


class ApplicationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    team: str | None = None
    description: str | None = None
    # 省略该字段 ⇒ 不改授权；给出列表 ⇒ 作为新的完整授权集合（含空列表=清空）。
    service_ids: list[int] | None = None


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    owner_user_id: int
    team: str | None
    description: str | None
    created_at: datetime | None = None
    service_ids: list[int] = Field(default_factory=list)


class ApplicationList(BaseModel):
    items: list[ApplicationOut]
    total: int


async def _validate_services_exist(db: AsyncSession, service_ids: set[int]) -> None:
    """所有 service_id 必须存在，否则 400。"""
    if not service_ids:
        return
    res = await db.execute(select(McpService.id).where(McpService.id.in_(service_ids)))
    found = set(res.scalars().all())
    missing = sorted(service_ids - found)
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown service ids: {missing}")


async def _service_ids_for(db: AsyncSession, application_id: int) -> list[int]:
    res = await db.execute(
        select(ServicePermission.service_id)
        .where(ServicePermission.application_id == application_id)
        .order_by(ServicePermission.service_id)
    )
    return list(res.scalars().all())


def _to_out(app_obj: Application, service_ids: list[int]) -> ApplicationOut:
    return ApplicationOut(
        id=app_obj.id,
        name=app_obj.name,
        owner_user_id=app_obj.owner_user_id,
        team=app_obj.team,
        description=app_obj.description,
        created_at=app_obj.created_at,
        service_ids=service_ids,
    )


@router.post(
    "",
    response_model=ApplicationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_application(
    payload: ApplicationCreate,
    request: Request,
    current_user: User = Depends(require_role("admin", "operator")),
    db: AsyncSession = Depends(get_db),
    redis: Redis | None = Depends(get_redis),
) -> ApplicationOut:
    service_ids = sorted(set(payload.service_ids))
    await _validate_services_exist(db, set(service_ids))

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

    for sid in service_ids:
        db.add(
            ServicePermission(
                application_id=app_obj.id,
                service_id=sid,
                granted_by=current_user.id,
            )
        )
    await db.flush()

    await audit_log(
        db,
        action=Action.APPLICATION_CREATE,
        target_type="application",
        target_id=str(app_obj.id),
        before=None,
        after=model_to_dict(app_obj) | {"service_ids": service_ids},
        actor=current_user,
        request=request,
    )
    out = _to_out(app_obj, service_ids)
    # commit 主写 + audit 后再发失效通知（V1-A.1 不变式：publish 必须在 commit 之后）
    await db.commit()
    for sid in service_ids:
        await publish_policy_invalidate(redis, sid)
    return out


@router.get(
    "",
    response_model=ApplicationList,
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)
async def list_applications(db: AsyncSession = Depends(get_db)) -> ApplicationList:
    res = await db.execute(select(Application).order_by(Application.id))
    apps = res.scalars().all()

    perm_res = await db.execute(
        select(ServicePermission.application_id, ServicePermission.service_id)
    )
    by_app: dict[int, list[int]] = {}
    for app_id, svc_id in perm_res.all():
        by_app.setdefault(app_id, []).append(svc_id)

    items = [_to_out(a, sorted(by_app.get(a.id, []))) for a in apps]
    return ApplicationList(items=items, total=len(items))


@router.get(
    "/{application_id}",
    response_model=ApplicationOut,
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)
async def get_application(
    application_id: int, db: AsyncSession = Depends(get_db)
) -> ApplicationOut:
    res = await db.execute(select(Application).where(Application.id == application_id))
    app_obj = res.scalar_one_or_none()
    if app_obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "application not found")
    return _to_out(app_obj, await _service_ids_for(db, application_id))


@router.patch(
    "/{application_id}",
    response_model=ApplicationOut,
)
async def update_application(
    application_id: int,
    payload: ApplicationUpdate,
    request: Request,
    current_user: User = Depends(require_role("admin", "operator")),
    db: AsyncSession = Depends(get_db),
    redis: Redis | None = Depends(get_redis),
) -> ApplicationOut:
    res = await db.execute(select(Application).where(Application.id == application_id))
    app_obj = res.scalar_one_or_none()
    if app_obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "application not found")

    current_ids = set(await _service_ids_for(db, application_id))
    before = model_to_dict(app_obj) | {"service_ids": sorted(current_ids)}

    data = payload.model_dump(exclude_unset=True)

    affected: set[int] = set()
    final_ids = current_ids
    if "service_ids" in data:
        desired = set(data.pop("service_ids"))
        await _validate_services_exist(db, desired)
        to_add = desired - current_ids
        to_remove = current_ids - desired
        if to_remove:
            await db.execute(
                delete(ServicePermission).where(
                    ServicePermission.application_id == application_id,
                    ServicePermission.service_id.in_(to_remove),
                )
            )
        for sid in to_add:
            db.add(
                ServicePermission(
                    application_id=application_id,
                    service_id=sid,
                    granted_by=current_user.id,
                )
            )
        affected = to_add | to_remove
        final_ids = desired

    for key, value in data.items():
        setattr(app_obj, key, value)

    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "name already exists") from e

    sorted_final = sorted(final_ids)
    await audit_log(
        db,
        action=Action.APPLICATION_UPDATE,
        target_type="application",
        target_id=str(app_obj.id),
        before=before,
        after=model_to_dict(app_obj) | {"service_ids": sorted_final},
        actor=current_user,
        request=request,
    )
    out = _to_out(app_obj, sorted_final)
    # commit 主写 + audit 后再发失效通知（V1-A.1 不变式：publish 必须在 commit 之后）
    await db.commit()
    for sid in affected:
        await publish_policy_invalidate(redis, sid)
    return out
