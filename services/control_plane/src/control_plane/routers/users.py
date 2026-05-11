from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mcpsys_shared.models import User, UserRole, UserStatus

from ..audit import Action, audit_log, model_to_dict
from ..deps import get_current_user, get_db, require_role
from ..security import hash_password

router = APIRouter(prefix="/api/v1/users", tags=["users"])


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    email: EmailStr | None = None
    role: UserRole = UserRole.viewer


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str | None
    role: UserRole
    status: UserStatus


class UserList(BaseModel):
    items: list[UserOut]
    total: int


class UserUpdate(BaseModel):
    password: str = Field(min_length=8, max_length=128)


@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    payload: UserCreate,
    request: Request,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "username already exists") from e
    await audit_log(
        db,
        action=Action.USER_CREATE,
        target_type="user",
        target_id=str(user.id),
        before=None,
        after=model_to_dict(user),
        actor=current_user,
        request=request,
    )
    return UserOut.model_validate(user)


@router.get(
    "",
    response_model=UserList,
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)
async def list_users(db: AsyncSession = Depends(get_db)) -> UserList:
    res = await db.execute(select(User).order_by(User.id))
    users = res.scalars().all()
    return UserList(items=[UserOut.model_validate(u) for u in users], total=len(users))


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    if user_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权修改其他用户")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    before = model_to_dict(user)
    user.password_hash = hash_password(payload.password)
    await db.flush()
    after = model_to_dict(user)
    await audit_log(
        db,
        action=Action.USER_PASSWORD_CHANGE,
        target_type="user",
        target_id=str(user.id),
        before=before,
        after=after,
        actor=current_user,
        request=request,
    )
    return UserOut.model_validate(user)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> None:
    if user_id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能删除当前登录账号")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    before = model_to_dict(user)
    await db.delete(user)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "无法删除：用户被应用 / 审计 / 服务版本 / 权限授予记录引用，请先转移或考虑禁用账号",
        ) from e
    await audit_log(
        db,
        action=Action.USER_DELETE,
        target_type="user",
        target_id=str(user_id),
        before=before,
        after=None,
        actor=current_user,
        request=request,
    )
