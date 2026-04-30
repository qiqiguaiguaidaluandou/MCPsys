#!/bin/sh
set -e
echo "[entrypoint] running alembic upgrade head"
alembic upgrade head
exec "$@"
