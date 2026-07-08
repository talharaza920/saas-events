"""guest greeting name

Adds `guests.greeting_name` — an invitee-level override for the invite cover's
"Dear …" greeting (e.g. "John & Jane"). When NULL/empty the cover falls back to
the first word of `name`. Party-level (never per-companion). Additive + nullable,
no backfill needed; RLS already covers the `guests` table.

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-06-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("guests", sa.Column("greeting_name", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("guests", "greeting_name")
