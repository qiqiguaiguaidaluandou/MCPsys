"""drop api_keys.last_used_at

DB 列从 v1 起就存在但 gateway / control-plane 均未写入。UI 详情页"最近调用"
派生自 call_logs.MAX(ts)，与本列独立 —— 删除无回归。详见
docs/changes/2026-05-19-详情页统计窗口扩展.md §7。

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-19 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("api_keys", "last_used_at")


def downgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
