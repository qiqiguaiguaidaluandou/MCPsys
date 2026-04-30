from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mcpsys_shared.models import User, UserRole, UserStatus

from ..deps import get_db, require_role
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
