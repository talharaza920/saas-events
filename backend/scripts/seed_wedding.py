"""Seed (or update) the default wedding row — Alex & Sam.

Content + event details live as DATA on the row (multi-tenant; editable later).
Run AFTER migrations:  python -m scripts.seed_wedding
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models import (
    Question,
    QuestionApplies,
    QuestionScope,
    QuestionType,
    StoryArc,
    Wedding,
)
from app.seed_data import (
    COUPLE_NAMES,
    CONTENT,
    DEFAULT_QUESTIONS,
    EVENT_DETAILS,
    STORY_ARCS,
    WEDDING_SLUG,
)


def seed() -> Wedding:
    db = SessionLocal()
    try:
        wedding = db.query(Wedding).filter_by(slug=WEDDING_SLUG).one_or_none()
        if wedding is None:
            wedding = Wedding(slug=WEDDING_SLUG)
            db.add(wedding)
        wedding.couple_names = COUPLE_NAMES
        wedding.event_details = EVENT_DETAILS
        wedding.content = CONTENT
        wedding.theme_tokens = None  # use the default "Ever after" template
        wedding.status = "active"
        db.commit()
        db.refresh(wedding)

        # Seed the initial story arc only if the wedding has none yet (idempotent;
        # never clobbers arcs the owner has since edited in /admin).
        if db.query(StoryArc).filter_by(wedding_id=wedding.id).count() == 0:
            for arc in STORY_ARCS:
                db.add(
                    StoryArc(
                        wedding_id=wedding.id,
                        title=arc["title"],
                        visible=arc["visible"],
                        sort_order=arc["sort_order"],
                        content=arc["content"],
                    )
                )
            db.commit()

        # Seed the default RSVP questions, but only if the wedding has none (so the
        # owner's edits in /admin are never clobbered on a re-run).
        if db.query(Question).filter_by(wedding_id=wedding.id).count() == 0:
            for q in DEFAULT_QUESTIONS:
                db.add(
                    Question(
                        wedding_id=wedding.id,
                        prompt=q["prompt"],
                        qtype=QuestionType(q["qtype"]),
                        options=q["options"],
                        required=q["required"],
                        scope=QuestionScope(q["scope"]),
                        applies_to=QuestionApplies(q["applies_to"]),
                        sort_order=q["sort_order"],
                    )
                )
            db.commit()

        print(f"Seeded wedding '{wedding.slug}' (id={wedding.id}) — {wedding.couple_names}")
        return wedding
    finally:
        db.close()


if __name__ == "__main__":
    seed()
