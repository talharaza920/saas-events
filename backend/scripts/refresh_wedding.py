"""One-time production CONTENT refresh for an already-seeded wedding.

Brings the wedding's editable DATA — `content` / `event_details` / `couple_names`,
its story arcs, and the default question set — up to the current `app.seed_data`,
WITHOUT touching guests, RSVPs, companions, answers or wishes.

Why this exists
---------------
The production wedding row was seeded at M2; the invite content, story arcs and
question set have all changed since (the "Chapter Two" redesign + the M10-M12
work). Re-running `seed_wedding` overwrites the content blob but, by design, will
NOT replace story arcs / questions once they exist (so it never clobbers an
owner's /admin edits) — and `alembic upgrade head` auto-creates ONE stale arc from
the old `content.story`. For a first go-live we DO want all three replaced with
the current seed. That's what this does.

Safety
------
Refuses to run if ANY RSVP or answer exists for the wedding, so real guest
responses can never be destroyed by it. (Guest rows themselves are always kept.)

Run AFTER `alembic upgrade head`, against the same DATABASE_URL:
    python -m scripts.refresh_wedding
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models import (
    Answer,
    Guest,
    Question,
    QuestionApplies,
    QuestionScope,
    QuestionType,
    Rsvp,
    StoryArc,
    Wedding,
)
from app.seed_data import (
    CONTENT,
    COUPLE_NAMES,
    DEFAULT_QUESTIONS,
    EVENT_DETAILS,
    STORY_ARCS,
    WEDDING_SLUG,
)


def refresh() -> None:
    db = SessionLocal()
    try:
        wedding = db.query(Wedding).filter_by(slug=WEDDING_SLUG).one_or_none()
        if wedding is None:
            raise SystemExit(
                f"No wedding '{WEDDING_SLUG}' found — run `python -m scripts.seed_wedding` first."
            )

        rsvp_count = db.query(Rsvp).filter_by(wedding_id=wedding.id).count()
        answer_count = db.query(Answer).filter_by(wedding_id=wedding.id).count()
        if rsvp_count or answer_count:
            raise SystemExit(
                f"ABORT: {rsvp_count} RSVP(s) and {answer_count} answer(s) exist for "
                f"'{wedding.slug}'. A refresh would risk real guest responses — review "
                "and refresh manually instead."
            )

        guest_count = db.query(Guest).filter_by(wedding_id=wedding.id).count()

        # 1) Overwrite the editable content blob + event details + names.
        wedding.couple_names = COUPLE_NAMES
        wedding.event_details = EVENT_DETAILS
        wedding.content = CONTENT
        wedding.theme_tokens = None  # use the default "Ever after" template
        wedding.status = "active"

        # 2) Replace story arcs (the migration may have auto-created a stale one
        #    from the old content.story). No guest overrides exist pre-launch, but
        #    clear any just in case so they don't point at deleted arc ids.
        db.query(StoryArc).filter_by(wedding_id=wedding.id).delete()
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
        for g in db.query(Guest).filter_by(wedding_id=wedding.id):
            g.story_arc_ids = None

        # 3) Replace the question set with the current default (safe — no answers).
        db.query(Question).filter_by(wedding_id=wedding.id).delete()
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
        print(
            f"Refreshed '{wedding.slug}': content + {len(STORY_ARCS)} arc(s) + "
            f"{len(DEFAULT_QUESTIONS)} question(s). {guest_count} guest(s) left untouched."
        )
    finally:
        db.close()


if __name__ == "__main__":
    refresh()
