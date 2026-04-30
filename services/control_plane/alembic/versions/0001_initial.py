"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-30 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enums
    user_role = postgresql.ENUM("admin", "operator", "viewer", name="userrole")
    user_status = postgresql.ENUM("active", "disabled", name="userstatus")
    api_key_owner = postgresql.ENUM("user", "application", name="apikeyownertype")
    service_status = postgresql.ENUM("active", "disabled", name="servicestatus")
    health_status = postgresql.ENUM("healthy", "unhealthy", "unknown", name="healthstatus")
    transport_type = postgresql.ENUM("streamable_http", name="transporttype")
    call_status = postgresql.ENUM("success", "error", "timeout", name="callstatus")

    bind = op.get_bind()
    for e in (user_role, user_status, api_key_owner, service_status, health_status, transport_type, call_status):
        e.create(bind, checkfirst=True)

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("role", postgresql.ENUM("admin", "operator", "viewer", name="userrole", create_type=False), nullable=False, server_default="viewer"),
        sa.Column("status", postgresql.ENUM("active", "disabled", name="userstatus", create_type=False), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )

    # applications
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("team", sa.String(128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_applications_name"),
    )

    # api_keys
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("owner_type", postgresql.ENUM("user", "application", name="apikeyownertype", create_type=False), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("scopes", postgresql.JSONB(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])
    op.create_index("ix_api_keys_owner", "api_keys", ["owner_type", "owner_id"])

    # mcp_services
    op.create_table(
        "mcp_services",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_team", sa.String(128), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column("endpoint_url", sa.String(512), nullable=False),
        sa.Column("transport", postgresql.ENUM("streamable_http", name="transporttype", create_type=False), nullable=False, server_default="streamable_http"),
        sa.Column("status", postgresql.ENUM("active", "disabled", name="servicestatus", create_type=False), nullable=False, server_default="active"),
        sa.Column("health_status", postgresql.ENUM("healthy", "unhealthy", "unknown", name="healthstatus", create_type=False), nullable=False, server_default="unknown"),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_mcp_services_slug"),
    )

    # mcp_service_versions
    op.create_table(
        "mcp_service_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("mcp_services.id"), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("endpoint_url", sa.String(512), nullable=False),
        sa.Column("manifest", postgresql.JSONB(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("service_id", "version", name="uq_mcp_service_versions_service_version"),
    )

    # call_logs
    op.create_table(
        "call_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("api_key_id", sa.Integer(), nullable=True),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("service_version", sa.String(32), nullable=True),
        sa.Column("tool_name", sa.String(128), nullable=True),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("status", postgresql.ENUM("success", "error", "timeout", name="callstatus", create_type=False), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("request_bytes", sa.Integer(), nullable=True),
        sa.Column("response_bytes", sa.Integer(), nullable=True),
        sa.Column("request_body", sa.Text(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("client_ip", sa.String(64), nullable=True),
    )
    op.create_index("ix_call_logs_ts", "call_logs", ["ts"])
    op.create_index("ix_call_logs_service_ts", "call_logs", ["service_id", "ts"])
    op.create_index("ix_call_logs_apikey_ts", "call_logs", ["api_key_id", "ts"])
    op.create_index("ix_call_logs_status_ts", "call_logs", ["status", "ts"])

    # audit_events
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_index("ix_call_logs_status_ts", table_name="call_logs")
    op.drop_index("ix_call_logs_apikey_ts", table_name="call_logs")
    op.drop_index("ix_call_logs_service_ts", table_name="call_logs")
    op.drop_index("ix_call_logs_ts", table_name="call_logs")
    op.drop_table("call_logs")
    op.drop_table("mcp_service_versions")
    op.drop_table("mcp_services")
    op.drop_index("ix_api_keys_owner", table_name="api_keys")
    op.drop_index("ix_api_keys_key_prefix", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("applications")
    op.drop_table("users")

    bind = op.get_bind()
    for name in ("callstatus", "transporttype", "healthstatus", "servicestatus", "apikeyownertype", "userstatus", "userrole"):
        bind.execute(sa.text(f"DROP TYPE IF EXISTS {name}"))
