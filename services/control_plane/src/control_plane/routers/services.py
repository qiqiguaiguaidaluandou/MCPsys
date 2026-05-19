import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from mcpsys_shared.models import (
    HealthStatus,
    McpService,
    ServiceStatus,
    TransportType,
    User,
)
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import Action, audit_log, model_to_dict
from ..deps import get_db, get_redis, require_role
from ..invalidator import publish_service_invalidate

router = APIRouter(prefix="/api/v1/services", tags=["services"])

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$")


class ServiceCreate(BaseModel):
    slug: str
    display_name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    owner_team: str | None = None
    tags: list[str] = Field(default_factory=list)
    # endpoint_url is structurally validated only. Admin role is trusted to choose
    # safe destinations; v1 should add an SSRF deny-list (link-local, loopback ranges).
    endpoint_url: HttpUrl
    transport: TransportType = TransportType.streamable_http
    rate_limit_qps: int | None = Field(default=None, ge=0)

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
    rate_limit_qps: int | None = None


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
    rate_limit_qps: int | None
    last_health_check_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ServiceList(BaseModel):
    items: list[ServiceOut]
    total: int


@router.post(
    "",
    response_model=ServiceOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_service(
    payload: ServiceCreate,
    request: Request,
    current_user: User = Depends(require_role("admin", "operator")),
    db: AsyncSession = Depends(get_db),
) -> ServiceOut:
    svc = McpService(
        slug=payload.slug,
        display_name=payload.display_name,
        description=payload.description,
        owner_team=payload.owner_team,
        tags=payload.tags,
        endpoint_url=str(payload.endpoint_url),
        transport=payload.transport,
        rate_limit_qps=payload.rate_limit_qps,
    )
    db.add(svc)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "slug already exists") from e
    await audit_log(
        db,
        action=Action.SERVICE_CREATE,
        target_type="mcp_service",
        target_id=str(svc.id),
        before=None,
        after=model_to_dict(svc),
        actor=current_user,
        request=request,
    )
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
)
async def update_service(
    slug: str,
    payload: ServiceUpdate,
    request: Request,
    current_user: User = Depends(require_role("admin", "operator")),
    db: AsyncSession = Depends(get_db),
    redis: Redis | None = Depends(get_redis),
) -> ServiceOut:
    res = await db.execute(select(McpService).where(McpService.slug == slug))
    svc = res.scalar_one_or_none()
    if svc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "service not found")

    before = model_to_dict(svc)
    data = payload.model_dump(exclude_unset=True)
    if "endpoint_url" in data and data["endpoint_url"] is not None:
        data["endpoint_url"] = str(data["endpoint_url"])
    for k, v in data.items():
        setattr(svc, k, v)
    await db.flush()
    await db.refresh(svc)  # onupdate=func.now() expires updated_at; refresh repopulates
    after = model_to_dict(svc)
    await audit_log(
        db,
        action=Action.SERVICE_UPDATE,
        target_type="mcp_service",
        target_id=str(svc.id),
        before=before,
        after=after,
        actor=current_user,
        request=request,
    )
    # commit main write + audit row atomically; publish MUST follow commit (V1-A.1 invariant)
    await db.commit()
    await publish_service_invalidate(redis, svc.slug)
    return ServiceOut.model_validate(svc)


@router.delete(
    "/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_service(
    slug: str,
    request: Request,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
    redis: Redis | None = Depends(get_redis),
) -> Response:
    """Archive: status=disabled + slug 改写为 __archived_{id}。
    保留 call_logs 历史（无 FK），同时释放原 slug 以便重建同名服务；
    audit before 快照保留原始 slug/display_name。"""
    res = await db.execute(select(McpService).where(McpService.slug == slug))
    svc = res.scalar_one_or_none()
    if svc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "service not found")
    before = model_to_dict(svc)
    svc.status = ServiceStatus.disabled
    svc.slug = f"__archived_{svc.id}"
    await db.flush()
    await db.refresh(svc)  # onupdate=func.now() expires updated_at; refresh repopulates
    after = model_to_dict(svc)
    await audit_log(
        db,
        action=Action.SERVICE_DELETE,
        target_type="mcp_service",
        target_id=str(svc.id),
        before=before,
        after=after,
        actor=current_user,
        request=request,
    )
    # commit main write + audit row atomically; publish MUST follow commit (V1-A.1 invariant)
    await db.commit()
    # 失效用原始 slug（gateway / 缓存仍按它索引）
    await publish_service_invalidate(redis, before["slug"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)
