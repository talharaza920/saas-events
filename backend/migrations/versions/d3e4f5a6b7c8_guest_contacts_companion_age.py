"""guest contacts + companion age

Adds invitee contact columns `guests.email` / `guests.phone` (set by the guest at
RSVP time and/or by the owner via admin / spreadsheet import) and `companions.age`
(required for children at RSVP time, null for adults). All additive + nullable —
no backfill needed. RLS already covers these tables.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("guests", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column("guests", sa.Column("phone", sa.String(length=32), nullable=True))
    op.add_column("companions", sa.Column("age", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("companions", "age")
    op.drop_column("guests", "phone")
    op.drop_column("guests", "email")
