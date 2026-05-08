"""Seed service_permissions with the cartesian product of (active app-owned api keys'
applications) × (active services).

This is the safe migration from MVP "any active key calls anything" to the V1-A
white-list model: after running this, behavior is unchanged. Operators then
collect down by deleting unwanted grants.

Usage:
    uv run python scripts/bootstrap_permissions.py [--dry-run]

Idempotent: re-running yields no-ops (UNIQUE constraint on (app_id, service_id)).

User-owned keys are skipped — V1-A only supports application as the grant subject."""

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mcpsys_shared.db import make_engine, make_session_factory
from mcpsys_shared.models import (
    ApiKey,
    ApiKeyOwnerType,
    McpService,
    ServicePermission,
    ServiceStatus,
)
from mcpsys_shared.settings import SharedSettings


async def main(dry_run: bool) -> int:
    engine = make_engine(SharedSettings().database_url)
    sf = make_session_factory(engine)

    async with sf() as s:
        keys = (
            (
                await s.execute(
                    select(ApiKey).where(
                        ApiKey.owner_type == ApiKeyOwnerType.application,
                        ApiKey.revoked_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        services = (
            (
                await s.execute(
                    select(McpService).where(McpService.status == ServiceStatus.active)
                )
            )
            .scalars()
            .all()
        )
        existing = (
            (
                await s.execute(
                    select(
                        ServicePermission.application_id, ServicePermission.service_id
                    )
                )
            )
            .all()
        )

        app_ids = sorted({k.owner_id for k in keys})
        existing_pairs = set(map(tuple, existing))
        to_create: list[tuple[int, int]] = []
        for app_id in app_ids:
            for svc in services:
                if (app_id, svc.id) not in existing_pairs:
                    to_create.append((app_id, svc.id))

        print(
            f"[bootstrap] active app-owned keys: {len(keys)} → {len(app_ids)} unique apps"
        )
        print(f"[bootstrap] active services: {len(services)}")
        print(f"[bootstrap] existing grants: {len(existing_pairs)}")
        print(f"[bootstrap] new grants to insert: {len(to_create)}")

        if dry_run:
            print("[bootstrap] dry run — no changes written")
            return 0

        for app_id, svc_id in to_create:
            s.add(
                ServicePermission(
                    application_id=app_id, service_id=svc_id, note="bootstrap v1a"
                )
            )

        try:
            await s.commit()
        except IntegrityError as e:
            print(f"[bootstrap] integrity error (likely concurrent run): {e}", file=sys.stderr)
            return 2

        print(f"[bootstrap] inserted {len(to_create)} grants")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(dry_run=args.dry_run)))
