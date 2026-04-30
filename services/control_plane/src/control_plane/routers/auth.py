from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpsys_shared.models import User, UserRole, UserStatus

from ..deps import get_current_user, get_db
from ..security import encode_jwt, verify_password
from ..settings import settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str | None
    role: UserRole
    status: UserStatus


@router.post("/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    res = await db.execute(select(User).where(User.username == form.username))
    user = res.scalar_one_or_none()
    if (
        user is None
        or user.password_hash is None
        or not verify_password(form.password, user.password_hash)
        or user.status != UserStatus.active
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    user.last_login_at = datetime.now(UTC)

    token = encode_jwt(
        {"sub": str(user.id), "role": user.role.value, "username": user.username},
        secret=settings.jwt_secret,
        expires_minutes=settings.jwt_expires_minutes,
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
async def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse.model_validate(current_user)
