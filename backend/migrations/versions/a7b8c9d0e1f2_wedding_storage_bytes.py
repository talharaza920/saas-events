"""wedding storage_bytes_used (max_storage_mb enforcement)

Adds `weddings.storage_bytes_used` — bytes of uploaded media attributed to the
wedding. Incremented on each upload so `max_storage_mb` can be enforced at
upload time; periodically reconciled against the storage bucket by the cron
job (app/usage.py), since a pure counter drifts. Additive, NOT NULL default 0:
existing weddings start at zero and converge on truth at the first reconcile.

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-07-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "weddings",
        sa.Column(
            "storage_bytes_used",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("weddings", "storage_bytes_used")
