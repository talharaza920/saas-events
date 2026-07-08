"""Creating a wedding from the neutral starter template (SAAS_PLAN 2.1).

One code path for the self-serve `/create` wizard, the seed scripts, and tests:
seeds template content/questions/arcs as DATA on the new rows, personalises the
couple-name-bearing fields, and grants the creator the `owner` membership.
"""
from __future__ import annotations

import copy

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import AuthedUser
from app.models import (
    MemberRole,
    MemberStatus,
    Question,
    QuestionApplies,
    QuestionScope,
    QuestionType,
    StoryArc,
    Wedding,
    WeddingMember,
    WeddingStatus,
)
from app.seed_data import CONTENT, DEFAULT_QUESTIONS, EVENT_DETAILS, STORY_ARCS


def _personalised_content(couple_names: str) -> dict:
    """The template content with the couple-name-bearing fields swapped in.
    Everything else stays placeholder copy the owners edit in the dashboard."""
    content = copy.deepcopy(CONTENT)
    content.setdefault("nav", {})["brand"] = couple_names
    content.setdefault("brand", {})["wordmark_text"] = couple_names
    content.setdefault("landing", {})["heading"] = couple_names
    return content


def create_wedding(
    db: Session,
    *,
    slug: str,
    couple_names: str,
    creator: AuthedUser | None = None,
    event_overrides: dict | None = None,
    status: str = WeddingStatus.DRAFT,
    published: bool = False,
) -> Wedding:
    """Create + flush a wedding from the neutral template. Caller commits.

    Slug format/reservation/uniqueness must be validated by the caller (the API
    endpoint does; scripts use known-good slugs).
    """
    event_details = copy.deepcopy(EVENT_DETAILS)
    for key, value in (event_overrides or {}).items():
        if value is not None:
            event_details[key] = value

    wedding = Wedding(
        slug=slug,
        couple_names=couple_names,
        owner_id=creator.sub if creator else None,
        event_details=event_details,
        content=_personalised_content(couple_names),
        theme_tokens=None,  # the default "Ever after" template
        status=status,
        published=published,
    )
    db.add(wedding)
    db.flush()

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

    if creator is not None:
        db.add(
            WeddingMember(
                wedding_id=wedding.id,
                user_id=creator.sub,
                invited_email=creator.email,
                role=MemberRole.owner,
                status=MemberStatus.active,
            )
        )
    db.flush()
    return wedding


def ensure_owner_membership(db: Session, wedding: Wedding, user_sub: str, email: str) -> None:
    """Idempotently grant `owner` membership (used by seed scripts so the local
    dev principal can open the seeded wedding's dashboard)."""
    existing = db.execute(
        select(WeddingMember).where(
            WeddingMember.wedding_id == wedding.id, WeddingMember.user_id == user_sub
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            WeddingMember(
                wedding_id=wedding.id,
                user_id=user_sub,
                invited_email=email,
                role=MemberRole.owner,
                status=MemberStatus.active,
            )
        )
    else:
        existing.role = MemberRole.owner
        existing.status = MemberStatus.active
