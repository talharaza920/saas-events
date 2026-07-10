"""AI creation wizard tables (AI_WIZARD_PLAN Phase 8.0).

Adds `ai_jobs`, `ai_inputs`, `ai_usage_ledger`, `ai_variants` (tenant-scoped,
wedding_id) and `ai_prompts` (platform-owned prompt overrides). Additive only.

Notable shapes:
- `uq_ai_jobs_one_active`: PARTIAL unique index on ai_jobs(wedding_id) WHERE
  status IN ('queued','running') — the one-running-job-per-wedding ceiling,
  enforced in the DB so it holds under N concurrent serverless instances.
- `ai_usage_ledger.wedding_id` / `job_id` are ON DELETE SET NULL: the spend
  record outlives the tenant (same discipline as audit_log).
- `ai_prompts.provider` is '' (not NULL) for the shared fallback row —
  Postgres forbids NULL primary-key columns.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_TABLES = ("ai_jobs", "ai_inputs", "ai_usage_ledger", "ai_variants", "ai_prompts")


def upgrade() -> None:
    op.create_table(
        "ai_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("wedding_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("steps_total", sa.Integer(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("proposal", sa.JSON(), nullable=True),
        sa.Column("credits_held", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["wedding_id"], ["weddings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wedding_id", "idempotency_key", name="uq_ai_jobs_idempotency"),
    )
    op.create_index(op.f("ix_ai_jobs_wedding_id"), "ai_jobs", ["wedding_id"], unique=False)
    op.create_index(op.f("ix_ai_jobs_status"), "ai_jobs", ["status"], unique=False)
    op.create_index(
        "uq_ai_jobs_one_active",
        "ai_jobs",
        ["wedding_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
        sqlite_where=sa.text("status IN ('queued','running')"),
    )

    op.create_table(
        "ai_inputs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("wedding_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("storage_url", sa.String(length=500), nullable=True),
        sa.Column("mime", sa.String(length=100), nullable=True),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["wedding_id"], ["weddings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["ai_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_inputs_wedding_id"), "ai_inputs", ["wedding_id"], unique=False)
    op.create_index(op.f("ix_ai_inputs_job_id"), "ai_inputs", ["job_id"], unique=False)

    op.create_table(
        "ai_usage_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("wedding_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("images", sa.Integer(), nullable=True),
        sa.Column("cost_usd_micros", sa.BigInteger(), nullable=False),
        sa.Column("provider_request_id", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["wedding_id"], ["weddings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["ai_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_usage_ledger_wedding_id"), "ai_usage_ledger", ["wedding_id"], unique=False)
    op.create_index(op.f("ix_ai_usage_ledger_job_id"), "ai_usage_ledger", ["job_id"], unique=False)
    op.create_index(op.f("ix_ai_usage_ledger_created_at"), "ai_usage_ledger", ["created_at"], unique=False)

    op.create_table(
        "ai_variants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("wedding_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("artifact", sa.String(length=80), nullable=False),
        sa.Column("content", sa.JSON(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=True),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("prompt_key", sa.String(length=80), nullable=True),
        sa.Column("prompt_version", sa.Integer(), nullable=True),
        sa.Column("seed", sa.String(length=40), nullable=True),
        sa.Column("steer", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["wedding_id"], ["weddings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["ai_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_variants_wedding_id"), "ai_variants", ["wedding_id"], unique=False)
    op.create_index(op.f("ix_ai_variants_job_id"), "ai_variants", ["job_id"], unique=False)

    op.create_table(
        "ai_prompts",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=20), server_default=sa.text("''"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("effort", sa.String(length=10), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("json_schema", sa.JSON(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key", "provider", "version"),
    )

    # RLS backstop, same stance as every prior migration: enabled with NO
    # policies — the backend (table owner) bypasses it; Supabase anon/
    # authenticated roles are denied everything. Postgres-only.
    if op.get_bind().dialect.name == "postgresql":
        for _t in _NEW_TABLES:
            op.execute(f'ALTER TABLE "{_t}" ENABLE ROW LEVEL SECURITY;')


def downgrade() -> None:
    for _t in reversed(_NEW_TABLES):
        op.drop_table(_t)
