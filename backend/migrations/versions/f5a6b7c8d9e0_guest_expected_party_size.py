"""guest expected party size

Adds `guests.expected_party_size` — the owner's pre-RSVP estimate of how many
people an invite will bring (incl. the invitee). Admin-only planning aid, never
exposed to the guest or the RSVP flow. Additive + nullable, no backfill needed;
RLS already covers the `guests` table.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-06-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("guests", sa.Column("expected_party_size", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("guests", "expected_party_size")
