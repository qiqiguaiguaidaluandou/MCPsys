"""Bootstrap a user with a given role. Idempotent.

用于建"自注册账号"（registrar，operator 角色），供 MCP 服务容器自注册时登录用。

Usage (inside control-plane container):
    python scripts/seed_user.py <username> <password> [role]

role ∈ {admin, operator, viewer}，默认 operator。
"""
import asyncio
import sys

from sqlalchemy import select

from mcpsys_shared.db import make_engine, make_session_factory
from mcpsys_shared.models import User, UserRole, UserStatus
from mcpsys_shared.settings import SharedSettings

from control_plane.security import hash_password


async def main(username: str, password: str, role: str) -> None:
    try:
        role_enum = UserRole(role)
    except ValueError:
        print(f"invalid role {role!r}; must be one of: admin, operator, viewer", file=sys.stderr)
        sys.exit(2)
    engine = make_engine(SharedSettings().database_url)
    sf = make_session_factory(engine)
    async with sf() as s:
        existing = (
            await s.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if existing is not None:
            print(f"user {username!r} already exists, skipping")
            return
        s.add(
            User(
                username=username,
                password_hash=hash_password(password),
                role=role_enum,
                status=UserStatus.active,
            )
        )
        await s.commit()
        print(f"created {role} user {username!r}")
    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print("usage: python scripts/seed_user.py <username> <password> [role]", file=sys.stderr)
        sys.exit(2)
    role_arg = sys.argv[3] if len(sys.argv) == 4 else "operator"
    asyncio.run(main(sys.argv[1], sys.argv[2], role_arg))
