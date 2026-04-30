"""Bootstrap an initial admin user. Idempotent.

Usage (inside control-plane container):
    python scripts/seed_admin.py admin SuperSecret123
"""
import asyncio
import sys

from sqlalchemy import select

from mcpsys_shared.db import make_engine, make_session_factory
from mcpsys_shared.models import User, UserRole, UserStatus
from mcpsys_shared.settings import SharedSettings

from control_plane.security import hash_password


async def main(username: str, password: str) -> None:
    engine = make_engine(SharedSettings().database_url)
    sf = make_session_factory(engine)
    async with sf() as s:
        existing = (await s.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if existing is not None:
            print(f"user {username!r} already exists, skipping")
            return
        s.add(
            User(
                username=username,
                password_hash=hash_password(password),
                role=UserRole.admin,
                status=UserStatus.active,
            )
        )
        await s.commit()
        print(f"created admin {username!r}")
    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python scripts/seed_admin.py <username> <password>", file=sys.stderr)
        sys.exit(2)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
