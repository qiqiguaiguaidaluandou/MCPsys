from collections.abc import AsyncIterator

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpsys_shared.models import User, UserStatus

from .security import decode_jwt
from .settings import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing token")
    try:
        payload = decode_jwt(token, secret=settings.jwt_secret)
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing sub")
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError) as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token sub not numeric") from e

    res = await db.execute(select(User).where(User.id == user_id_int))
    user = res.scalar_one_or_none()
    if user is None or user.status != UserStatus.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user inactive or missing")
    return user


def require_role(*roles: str):
    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return user

    return _check
