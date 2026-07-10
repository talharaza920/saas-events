"""P2 hot-path indexes (REVIEW_BACKLOG P2-16)

Three additive indexes for query paths that scan today:
  • wishes(wedding_id, approved) — the public guest wall filters on both.
  • audit_log(created_at)        — the console tails ORDER BY created_at DESC.
  • rsvps(updated_at)            — /responses sorts most-recently-changed first.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_wishes_wedding_approved", "wishes", ["wedding_id", "approved"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])
    op.create_index("ix_rsvps_updated_at", "rsvps", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_rsvps_updated_at", table_name="rsvps")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index("ix_wishes_wedding_approved", table_name="wishes")
