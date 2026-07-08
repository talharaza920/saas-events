"""Identity & tenancy core (SAAS_PLAN Phase 1) + platform settings (Phase 2).

Adds accounts/membership/audit tables, `weddings.published` + `weddings.settings`,
and the key-value `platform_settings` table. Additive only. Backfills
`published = true` for already-active weddings so a pre-platform tenant's guest
links keep working once publication becomes a required switch.

Revision ID: e0a1b2c3d4e5
Revises: d9e0f1a2b3c4
Create Date: 2026-07-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e0a1b2c3d4e5"
down_revision: Union[str, None] = "d9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_TABLES = ("profiles", "wedding_members", "platform_admins", "audit_log", "platform_settings")


def upgrade() -> None:
    op.add_column(
        "weddings",
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("weddings", sa.Column("settings", sa.JSON(), nullable=True))
    # Pre-platform tenants were live the moment they were 'active'.
    op.execute("UPDATE weddings SET published = true WHERE status = 'active'")

    op.create_table(
        "profiles",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(op.f("ix_profiles_email"), "profiles", ["email"], unique=False)

    op.create_table(
        "wedding_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("wedding_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("invited_email", sa.String(length=254), nullable=True),
        sa.Column("role", sa.Enum("owner", "admin", name="member_role"), nullable=False),
        sa.Column("status", sa.Enum("invited", "active", "revoked", name="member_status"), nullable=False),
        sa.Column("invited_by", sa.String(length=64), nullable=True),
        sa.Column("invite_token_hash", sa.String(length=64), nullable=True),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["wedding_id"], ["weddings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wedding_id", "user_id", name="uq_member_wedding_user"),
        sa.UniqueConstraint("wedding_id", "invited_email", name="uq_member_wedding_email"),
    )
    op.create_index(op.f("ix_wedding_members_wedding_id"), "wedding_members", ["wedding_id"], unique=False)
    op.create_index(op.f("ix_wedding_members_user_id"), "wedding_members", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_wedding_members_invite_token_hash"), "wedding_members", ["invite_token_hash"], unique=False
    )

    op.create_table(
        "platform_admins",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("granted_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("wedding_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.String(length=64), nullable=True),
        sa.Column("actor_email", sa.String(length=254), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=40), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["wedding_id"], ["weddings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_log_wedding_id"), "audit_log", ["wedding_id"], unique=False)
    op.create_index(op.f("ix_audit_log_actor_user_id"), "audit_log", ["actor_user_id"], unique=False)
    op.create_index(op.f("ix_audit_log_action"), "audit_log", ["action"], unique=False)

    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    # RLS backstop, same stance as the initial schema: enabled with NO policies —
    # the backend (table owner) bypasses it; Supabase anon/authenticated roles are
    # denied everything. Postgres-only; skipped on SQLite.
    if op.get_bind().dialect.name == "postgresql":
        for _t in _NEW_TABLES:
            op.execute(f'ALTER TABLE "{_t}" ENABLE ROW LEVEL SECURITY;')


def downgrade() -> None:
    for _t in reversed(_NEW_TABLES):
        op.drop_table(_t)
    op.drop_column("weddings", "settings")
    op.drop_column("weddings", "published")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS member_role")
        op.execute("DROP TYPE IF EXISTS member_status")
