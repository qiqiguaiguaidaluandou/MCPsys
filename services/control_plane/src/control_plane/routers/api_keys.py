from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from mcpsys_shared.models import ApiKey, ApiKeyOwnerType, Application, User
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import Action, audit_log, model_to_dict
from ..deps import get_db, require_role
from ..security import generate_api_key

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    # Key 永远归属某个应用；调用权限由应用的可调用服务列表决定。
    application_id: int
    expires_at: datetime | None = None
    rate_limit_qps: int | None = Field(default=None, ge=0)


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
    revoked_at: datetime | None
    created_at: datetime
    rate_limit_qps: int | None


class ApiKeyUpdate(BaseModel):
    rate_limit_qps: int | None = None


class ApiKeyList(BaseModel):
    items: list[ApiKeyOut]
    total: int


async def _validate_application(db: AsyncSession, application_id: int) -> None:
    res = await db.execute(select(Application).where(Application.id == application_id))
    if res.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "application not found")


@router.post(
    "",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    payload: ApiKeyCreate,
    request: Request,
    current_user: User = Depends(require_role("admin", "operator")),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreated:
    await _validate_application(db, payload.application_id)
    plaintext, prefix, hashed = generate_api_key()
    key = ApiKey(
        name=payload.name,
        key_prefix=prefix,
        key_hash=hashed,
        owner_type=ApiKeyOwnerType.application,
        owner_id=payload.application_id,
        expires_at=payload.expires_at,
        rate_limit_qps=payload.rate_limit_qps,
    )
    db.add(key)
    await db.flush()
    await audit_log(
        db,
        action=Action.API_KEY_ISSUE,
        target_type="api_key",
        target_id=str(key.id),
        before=None,
        after=model_to_dict(key),
        actor=current_user,
        request=request,
    )
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


@router.get(
    "/{key_id}",
    response_model=ApiKeyOut,
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)
async def get_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiKeyOut:
    res = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    key = res.scalar_one_or_none()
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "api key not found")
    return ApiKeyOut.model_validate(key)


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_api_key(
    key_id: int,
    request: Request,
    current_user: User = Depends(require_role("admin", "operator")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    res = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    key = res.scalar_one_or_none()
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "api key not found")
    if key.revoked_at is None:
        before = model_to_dict(key)
        key.revoked_at = datetime.now(UTC)
        await db.flush()
        after = model_to_dict(key)
        await audit_log(
            db,
            action=Action.API_KEY_REVOKE,
            target_type="api_key",
            target_id=str(key.id),
            before=before,
            after=after,
            actor=current_user,
            request=request,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{key_id}/permanent",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_api_key_permanent(
    key_id: int,
    request: Request,
    current_user: User = Depends(require_role("admin", "operator")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    res = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    key = res.scalar_one_or_none()
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "api key not found")
    if key.revoked_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "key must be revoked before permanent delete")
    before = model_to_dict(key)
    await db.delete(key)
    await db.flush()
    await audit_log(
        db,
        action=Action.API_KEY_DELETE,
        target_type="api_key",
        target_id=str(key_id),
        before=before,
        after=None,
        actor=current_user,
        request=request,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{key_id}",
    response_model=ApiKeyOut,
)
async def update_api_key(
    key_id: int,
    payload: ApiKeyUpdate,
    request: Request,
    current_user: User = Depends(require_role("admin", "operator")),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyOut:
    res = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    key = res.scalar_one_or_none()
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "api key not found")

    before = model_to_dict(key)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(key, k, v)
    await db.flush()
    after = model_to_dict(key)
    await audit_log(
        db,
        action=Action.API_KEY_UPDATE,
        target_type="api_key",
        target_id=str(key.id),
        before=before,
        after=after,
        actor=current_user,
        request=request,
    )
    return ApiKeyOut.model_validate(key)
