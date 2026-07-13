"""ai_inputs: upload role + consent record (AI_WIZARD_PLAN 8.5d, likeness)

A photo of the couple is a different KIND of submission from a voice note about
their venue: it is never transcribed, never read for facts, and only ever
handed to the image model as a reference for what they look like. That makes it
a distinct `role` on the row rather than a flag somewhere in job state —
and the consent that permits it is recorded ON the same row (who ticked the
box, and when), because a consent you cannot produce later is not a consent.

Additive. Existing rows are `role='source'` (what every input was until now)
with no consent, which is exactly right: nothing uploaded before this migration
was ever offered as a likeness reference.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_inputs",
        sa.Column(
            "role",
            sa.String(length=10),
            nullable=False,
            server_default=sa.text("'source'"),
        ),
    )
    op.add_column(
        "ai_inputs",
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_inputs", sa.Column("consent_by", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("ai_inputs", "consent_by")
    op.drop_column("ai_inputs", "consent_at")
    op.drop_column("ai_inputs", "role")
