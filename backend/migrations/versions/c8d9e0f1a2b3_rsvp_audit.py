"""rsvp audit trail (updated_at + source/actor)

Adds the RSVP provenance columns used by app/audit.py: `updated_at` (latest
change, distinct from the first-reply `responded_at`), `first_source`/`last_source`
("guest" | "admin" | "import"), and `last_actor` (admin email for owner/import
writes, NULL for a guest's own submission). All additive + nullable.

Existing rows are backfilled: `updated_at` = `responded_at`, and both source
columns to "guest" (every pre-existing RSVP came in through a guest's signed link
— the admin override/import paths are newer than any stored response). RLS already
covers the `rsvps` table.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-06-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rsvps",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.add_column("rsvps", sa.Column("first_source", sa.String(length=20), nullable=True))
    op.add_column("rsvps", sa.Column("last_source", sa.String(length=20), nullable=True))
    op.add_column("rsvps", sa.Column("last_actor", sa.String(length=254), nullable=True))
    # Backfill: pre-existing responses all arrived via the guest link.
    op.execute(
        "UPDATE rsvps SET updated_at = responded_at, "
        "first_source = 'guest', last_source = 'guest'"
    )


def downgrade() -> None:
    op.drop_column("rsvps", "last_actor")
    op.drop_column("rsvps", "last_source")
    op.drop_column("rsvps", "first_source")
    op.drop_column("rsvps", "updated_at")
