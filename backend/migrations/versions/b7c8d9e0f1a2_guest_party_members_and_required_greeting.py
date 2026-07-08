"""guest party_members + required greeting

Two coupled changes to the invite/guest model:

* Adds `guests.party_members` (JSON, nullable) — the admin-curated PREFILL party
  (`[{"kind","name"}]`) used to seed the RSVP's +1/kids before the guest responds.
* Makes `guests.greeting_name` **NOT NULL** — it is now the mandatory invite label
  and the only thing shown in the cover's "Dear …" line. Existing rows are
  backfilled from the first word of `name` (or "Guest" when there's no name) before
  the constraint is applied, so the migration is safe on populated databases.

RLS already covers the `guests` table; these are additive/constraint-only.

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-06-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("guests", sa.Column("party_members", sa.JSON(), nullable=True))
    # Backfill the greeting from the first word of the name (fall back to "Guest"),
    # then lock it NOT NULL so an invite can never lose its label.
    op.execute(
        """
        UPDATE guests
        SET greeting_name = COALESCE(
            NULLIF(split_part(trim(COALESCE(name, '')), ' ', 1), ''),
            'Guest'
        )
        WHERE greeting_name IS NULL OR greeting_name = ''
        """
    )
    op.alter_column(
        "guests",
        "greeting_name",
        existing_type=sa.String(length=120),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "guests",
        "greeting_name",
        existing_type=sa.String(length=120),
        nullable=True,
    )
    op.drop_column("guests", "party_members")
