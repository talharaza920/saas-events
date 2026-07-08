"""guest invite_sent (Invited status)

Adds `guests.invite_sent` — whether the owner has SENT this guest their invite.
Drives the new "Invited" status between Pending (created, not yet contacted) and a
real RSVP reply. Set manually by the owner; distinct from `invited` ("on the list").
Additive, NOT NULL with a server default of false so existing rows backfill to
"not sent yet". RLS already covers the `guests` table.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-06-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "guests",
        sa.Column(
            "invite_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("guests", "invite_sent")
