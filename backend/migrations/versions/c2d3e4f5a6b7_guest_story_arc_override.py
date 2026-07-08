"""guest story-arc override

Adds `guests.story_arc_ids` (nullable JSON). NULL/empty = the guest sees every
`visible` story arc (the default); a non-empty list targets exactly those arc
ids. Per-invitee story targeting is by arc id only — never the invite_tier — so
this column never leaks the tier.

Revision ID: c2d3e4f5a6b7
Revises: b1f2c3d4e5f6
Create Date: 2026-06-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1f2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("guests", sa.Column("story_arc_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("guests", "story_arc_ids")
