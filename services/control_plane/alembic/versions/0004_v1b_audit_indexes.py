"""v1b audit_events 查询索引

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-11 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE INDEX ix_audit_events_ts ON audit_events (ts DESC)")
    op.execute("CREATE INDEX ix_audit_events_actor_ts ON audit_events (actor_user_id, ts DESC)")
    op.execute("CREATE INDEX ix_audit_events_target_ts ON audit_events (target_type, target_id, ts DESC)")
    op.execute("CREATE INDEX ix_audit_events_action_ts ON audit_events (action, ts DESC)")


def downgrade() -> None:
    op.drop_index("ix_audit_events_action_ts", table_name="audit_events")
    op.drop_index("ix_audit_events_target_ts", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_ts", table_name="audit_events")
    op.drop_index("ix_audit_events_ts", table_name="audit_events")
