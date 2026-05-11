from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mcpsys_shared.models import User, UserRole, UserStatus

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


@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin"))],
)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> UserOut:
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


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("admin"))],
)
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if user_id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能删除当前登录账号")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    await db.delete(user)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "无法删除：用户被应用 / 审计 / 服务版本 / 权限授予记录引用，请先转移或考虑禁用账号",
        ) from e
