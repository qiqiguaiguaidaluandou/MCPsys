"""v1-d 应用驱动授权：吊销 user-owned key、移除 service_permissions.note

授权关系改由应用侧统一管理：
- API Key 只归属应用，历史 owner_type='user' 的 key 全部吊销；
- service_permissions 由应用配置自动增删，备注（note）失去意义，移除该列。

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-15 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 历史 user-owned key 不再受支持：吊销所有仍生效的 user key。
    # 保留 owner_type 枚举与列本身（Postgres 删除枚举值代价高），仅在应用层禁止再签发。
    op.execute(
        "UPDATE api_keys SET revoked_at = now() "
        "WHERE owner_type = 'user' AND revoked_at IS NULL"
    )
    op.drop_column("service_permissions", "note")


def downgrade() -> None:
    # 无法还原被本迁移吊销的 key（无法区分历史吊销）；仅恢复 note 列。
    op.add_column(
        "service_permissions",
        sa.Column("note", sa.Text(), nullable=True),
    )
