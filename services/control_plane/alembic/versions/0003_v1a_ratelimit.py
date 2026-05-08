"""v1a ratelimit + denied/throttled

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-08 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("rate_limit_qps", sa.Integer(), nullable=True))
    op.add_column("mcp_services", sa.Column("rate_limit_qps", sa.Integer(), nullable=True))
    op.execute("ALTER TYPE callstatus ADD VALUE IF NOT EXISTS 'denied'")
    op.execute("ALTER TYPE callstatus ADD VALUE IF NOT EXISTS 'throttled'")


def downgrade() -> None:
    op.drop_column("mcp_services", "rate_limit_qps")
    op.drop_column("api_keys", "rate_limit_qps")
    # NOTE: postgres 不支持 enum 删值，回滚需要重建类型；只在确实需要时启用。
