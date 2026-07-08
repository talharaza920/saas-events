"""story arcs

Adds the `story_arcs` table (one configurable, numbered story arc per row) and
migrates each wedding's existing `content.story` blob into a single seeded arc.

Revision ID: b1f2c3d4e5f6
Revises: 9a4e0c2acead
Create Date: 2026-06-10

"""
import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b1f2c3d4e5f6"
down_revision: Union[str, None] = "9a4e0c2acead"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _arc_content_from_story(story: dict) -> dict:
    """Same transform as app.seed_data._arc_content_from_story (kept inline so the
    migration is self-contained and doesn't drift with app code)."""
    return {
        "kicker": story.get("kicker"),
        "heading": story.get("heading"),
        "intro": story.get("intro"),
        "beats": [
            {k: v for k, v in beat.items() if k != "n"} for beat in story.get("beats", [])
        ],
        "climax": story.get("climax"),
    }


def upgrade() -> None:
    op.create_table(
        "story_arcs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("wedding_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["wedding_id"], ["weddings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_story_arcs_wedding_id"), "story_arcs", ["wedding_id"], unique=False
    )

    # RLS backstop (Postgres only) — same rationale as the initial migration:
    # enable with no policies so the owner role keeps access and anon is denied.
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "story_arcs" ENABLE ROW LEVEL SECURITY;')

    # --- Data migration: content.story -> one seeded arc per wedding ----------
    conn = op.get_bind()
    weddings = sa.table(
        "weddings", sa.column("id", sa.Uuid()), sa.column("content", sa.JSON())
    )
    arcs = sa.table(
        "story_arcs",
        sa.column("id", sa.Uuid()),
        sa.column("wedding_id", sa.Uuid()),
        sa.column("title", sa.String()),
        sa.column("visible", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
        sa.column("content", sa.JSON()),
    )
    for wid, content in conn.execute(sa.select(weddings.c.id, weddings.c.content)):
        if isinstance(content, str):  # SQLite returns JSON as text
            content = json.loads(content) if content else {}
        story = (content or {}).get("story")
        if not story:
            continue
        conn.execute(
            arcs.insert().values(
                id=uuid.uuid4(),
                wedding_id=wid,
                title="Chapter Two",
                visible=True,
                sort_order=0,
                content=_arc_content_from_story(story),
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "story_arcs" DISABLE ROW LEVEL SECURITY;')
    op.drop_index(op.f("ix_story_arcs_wedding_id"), table_name="story_arcs")
    op.drop_table("story_arcs")
