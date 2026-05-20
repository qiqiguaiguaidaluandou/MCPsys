"""drop unused service-version scaffolding

服务版本管理（mcp_service_versions 表 + call_logs.service_version 列）从 v1 起
建好但从未实现：表无人读写、列被 gateway 写死 NULL、前端 tab/导航是禁用占位。
功能确认不做，按 api_keys.last_used_at 同样口径清掉死 schema。
详见 docs/changes/2026-05-20-移除服务版本死功能.md。

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-20 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("call_logs", "service_version")
    op.drop_table("mcp_service_versions")


def downgrade() -> None:
    op.create_table(
        "mcp_service_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("mcp_services.id"), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("endpoint_url", sa.String(512), nullable=False),
        sa.Column(
            "manifest", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint(
            "service_id", "version", name="uq_mcp_service_versions_service_version"
        ),
    )
    op.add_column("call_logs", sa.Column("service_version", sa.String(32), nullable=True))
