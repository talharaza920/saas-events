"""generic question engine + per-person answers

M12. Generalizes the RSVP so the only universal per-person field is Name and
everything else is an admin-defined question:

- `questions.scope` (invitee | person) + `questions.applies_to` (everyone | adults
  | children) — `person` questions are asked of each attendee; `applies_to` narrows
  which attendees (children-only is how "age, required for kids" is expressed).
- `question_type` gains `number` + `multi_choice`.
- `answers.companion_id` (FK → companions) attributes an answer to a specific
  person; NULL = the primary invitee / an invitee-scope answer.
- Drops the now-redundant special columns `rsvps.dietary`, `companions.dietary`,
  `companions.age` — dietary and age are ordinary questions now.

RLS already covers these tables (additive). On Postgres `ALTER TYPE … ADD VALUE`
cannot remove values again, so the downgrade leaves the two new enum values in
place (harmless).

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SCOPE = sa.Enum("invitee", "person", name="question_scope")
_APPLIES = sa.Enum("everyone", "adults", "children", name="question_applies")


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        # New enum types must exist before columns reference them; widen the
        # existing question_type enum with the two new values.
        _SCOPE.create(bind, checkfirst=True)
        _APPLIES.create(bind, checkfirst=True)
        op.execute("ALTER TYPE question_type ADD VALUE IF NOT EXISTS 'multi_choice'")
        op.execute("ALTER TYPE question_type ADD VALUE IF NOT EXISTS 'number'")

    op.add_column(
        "questions",
        sa.Column("scope", _SCOPE, nullable=False, server_default="invitee"),
    )
    op.add_column(
        "questions",
        sa.Column("applies_to", _APPLIES, nullable=False, server_default="everyone"),
    )

    with op.batch_alter_table("answers") as batch:
        batch.add_column(sa.Column("companion_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_answers_companion_id", "companions", ["companion_id"], ["id"], ondelete="CASCADE"
        )
    op.create_index(op.f("ix_answers_companion_id"), "answers", ["companion_id"], unique=False)

    # Dietary + age are questions now — drop the special columns.
    with op.batch_alter_table("companions") as batch:
        batch.drop_column("dietary")
        batch.drop_column("age")
    op.drop_column("rsvps", "dietary")


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.add_column("rsvps", sa.Column("dietary", sa.String(length=300), nullable=True))
    with op.batch_alter_table("companions") as batch:
        batch.add_column(sa.Column("dietary", sa.String(length=300), nullable=True))
        batch.add_column(sa.Column("age", sa.Integer(), nullable=True))

    op.drop_index(op.f("ix_answers_companion_id"), table_name="answers")
    with op.batch_alter_table("answers") as batch:
        batch.drop_constraint("fk_answers_companion_id", type_="foreignkey")
        batch.drop_column("companion_id")

    op.drop_column("questions", "applies_to")
    op.drop_column("questions", "scope")
    if is_pg:
        _APPLIES.drop(bind, checkfirst=True)
        _SCOPE.drop(bind, checkfirst=True)
    # Note: the 'multi_choice' / 'number' values added to question_type are left in
    # place — Postgres can't remove enum values.
