"""call_logs body-retention partial index

支撑 control_plane.retention worker：只索引 body 尚未置 NULL 的行，使
`ts < cutoff AND body IS NOT NULL` 的清理扫描代价正比于待清理行数而非全表。

CONCURRENTLY 建索引——call_logs 是 gateway 高频写入的表，普通 CREATE INDEX 的
SHARE 锁会阻塞 telemetry 写入。CONCURRENTLY 不能在事务里跑，用 autocommit_block。

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-20 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_call_logs_body_unpurged "
            "ON call_logs (ts) "
            "WHERE request_body IS NOT NULL OR response_body IS NOT NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_call_logs_body_unpurged")
