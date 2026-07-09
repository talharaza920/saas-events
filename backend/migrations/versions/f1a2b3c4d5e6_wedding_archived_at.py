"""wedding archived_at (purge window)

Adds `weddings.archived_at` — when the owner archived the wedding. Starts the
30-day undo window; the purge job (app/purge.py) hard-deletes weddings archived
longer ago than the window. Nullable + additive: existing archived rows (none in
production at migration time) keep NULL, which the purge deliberately skips —
a wedding with no archive timestamp is never auto-deleted.

Revision ID: f1a2b3c4d5e6
Revises: e0a1b2c3d4e5
Create Date: 2026-07-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "weddings",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("weddings", "archived_at")
