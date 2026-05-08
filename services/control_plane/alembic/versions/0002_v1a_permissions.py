"""v1a permissions

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-08 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "service_id",
            sa.Integer(),
            sa.ForeignKey("mcp_services.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("granted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.UniqueConstraint("application_id", "service_id", name="uq_service_permissions_app_service"),
    )
    op.create_index("ix_service_permissions_service", "service_permissions", ["service_id"])


def downgrade() -> None:
    op.drop_index("ix_service_permissions_service", table_name="service_permissions")
    op.drop_table("service_permissions")
