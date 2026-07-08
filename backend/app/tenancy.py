"""Tenant scoping + the invite-tier → capabilities mapping.

This module is the ONLY place that reads `Guest.invite_tier`. Everything above it
(routers, schemas) speaks in terms of *capabilities* (can bring a +1 / kids, and
how many) so the tier name never reaches the client. Two rules from CLAUDE.md
live here:

  1. Multi-tenant: a guest slug resolves to exactly one (wedding, guest); every
     query is scoped by `wedding_id`.
  2. The tier is invisible. `solo` guests get identical chrome with the companion
     fields silently omitted (caps of 0), and the API rejects any companion that
     exceeds the tier — the client cannot widen its own invite.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Guest, InviteTier, Question, QuestionVisibility, StoryArc, Wedding
from app.schemas import Capabilities

# Fixed companion allowance for the lower tiers (solo / +1). plus_family's caps are
# owner-configurable per wedding (see capabilities_for / family_party_caps), so it is
# computed dynamically rather than templated here.
_TIER_CAPS: dict[InviteTier, Capabilities] = {
    InviteTier.solo: Capabilities(
        allow_plus_one=False, allow_kids=False, max_adult_companions=0, max_child_companions=0
    ),
    InviteTier.plus_one: Capabilities(
        allow_plus_one=True, allow_kids=False, max_adult_companions=1, max_child_companions=0
    ),
}

# plus_family adult/child caps when the wedding hasn't configured content.rsvp.party.
DEFAULT_FAMILY_ADULTS = 4
DEFAULT_FAMILY_KIDS = 4


def _non_negative_int(value, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n >= 0 else default


def family_party_caps(content) -> tuple[int, int]:
    """(max_adults, max_child) for a plus_family invite, read from the owner-editable
    `content.rsvp.party` config. Either group can be switched off (→ 0) and capped;
    both default to 4 when unset. `content` may be the wedding's content dict or None.
    """
    party: dict = {}
    if isinstance(content, dict):
        party = ((content.get("rsvp") or {}).get("party")) or {}
    adults = (
        _non_negative_int(party.get("max_adults"), DEFAULT_FAMILY_ADULTS)
        if party.get("adults_enabled", True)
        else 0
    )
    kids = (
        _non_negative_int(party.get("max_kids"), DEFAULT_FAMILY_KIDS)
        if party.get("kids_enabled", True)
        else 0
    )
    return adults, kids


def capabilities_for(tier: InviteTier, content=None) -> Capabilities:
    """Map a tier to what the guest may do — the only tier→UI translation.

    For plus_family the adult/child caps come from the wedding's `content.rsvp.party`
    (owner-configurable, default 4/4) and `adults_multi` is set so the form renders an
    add/remove ADULTS list rather than the single +1 toggle. solo/plus_one are fixed.
    The tier name itself is never exposed — only these capabilities.
    """
    if tier is InviteTier.plus_family:
        adults, kids = family_party_caps(content)
        return Capabilities(
            allow_plus_one=adults > 0,
            allow_kids=kids > 0,
            max_adult_companions=adults,
            max_child_companions=kids,
            adults_multi=True,
        )
    # Return a copy so callers can't mutate the shared template.
    return _TIER_CAPS[tier].model_copy()


def clamp_party_members(members, tier: InviteTier, content=None) -> list[dict]:
    """Normalize an admin/import prefill party to `[{"kind","name"}]`, CLAMPED to the
    tier's caps. A solo invite always yields [] — the prefill can never leak or grant
    a companion the tier doesn't allow (mirrors the RSVP submit's anti-tamper clamp).

    `members` items may be dicts or objects exposing `kind`/`name`. Unknown kinds and
    overflow beyond the per-kind cap are dropped; names are trimmed.
    """
    caps = capabilities_for(tier, content)
    limits = {"adult": caps.max_adult_companions, "child": caps.max_child_companions}
    out: list[dict] = []
    for m in members or []:
        kind = (m.get("kind") if isinstance(m, dict) else getattr(m, "kind", None)) or ""
        name = (m.get("name") if isinstance(m, dict) else getattr(m, "name", None)) or ""
        kind = str(kind).strip().lower()
        if kind not in limits:
            continue
        if sum(1 for o in out if o["kind"] == kind) >= limits[kind]:
            continue
        out.append({"kind": kind, "name": str(name).strip()})
    return out


def primary_wedding(db: Session) -> Wedding | None:
    """The wedding shown on the public site root (the "no link" landing page).

    Single-tenant build: the earliest active wedding. (Multi-tenant later turns the
    root into a platform page; this stays the single-wedding fallback.)
    """
    return (
        db.execute(
            select(Wedding)
            .where(Wedding.status == "active", Wedding.published.is_(True))
            .order_by(Wedding.created_at)
        )
        .scalars()
        .first()
    )


def resolve_guest(db: Session, guest_slug: str) -> tuple[Wedding, Guest] | None:
    """Resolve an unguessable guest slug to its (wedding, guest), or None.

    The slug is globally unique and carries the tenant, so this is the single
    entry point for the guest-facing API.
    """
    guest = db.execute(select(Guest).where(Guest.slug == guest_slug)).scalar_one_or_none()
    if guest is None or not guest.invited:
        return None
    wedding = db.get(Wedding, guest.wedding_id)
    # Guests see the invite only when the wedding is BOTH approved (`active`) and
    # published — suspended/unpublished/archived all yield the same neutral 404,
    # so a guest can never tell why a link went dark.
    if wedding is None or wedding.status != "active" or not wedding.published:
        return None
    return wedding, guest


def visible_questions(db: Session, wedding: Wedding, guest: Guest) -> list[Question]:
    """Questions this guest should see, ordered. Tier/guest targeting is applied
    server-side; a hidden question is simply absent (no hint as to why)."""
    rows = (
        db.execute(
            select(Question)
            .where(Question.wedding_id == wedding.id)
            .order_by(Question.sort_order, Question.prompt)
        )
        .scalars()
        .all()
    )
    out: list[Question] = []
    for q in rows:
        if q.visibility is QuestionVisibility.all:
            out.append(q)
        elif q.visibility is QuestionVisibility.tier:
            if guest.invite_tier.value in (q.visibility_ref or []):
                out.append(q)
        elif q.visibility is QuestionVisibility.guests:
            if str(guest.id) in {str(x) for x in (q.visibility_ref or [])}:
                out.append(q)
    return out


def visible_arcs(db: Session, wedding: Wedding, guest: Guest) -> list[StoryArc]:
    """Story arcs this guest should see, ordered.

    Default (no override): every `visible` arc on the wedding. If the guest has a
    `story_arc_ids` override, they see exactly those arcs instead — even ones the
    owner has otherwise hidden (the override is a deliberate per-invitee pick) —
    validated to this wedding and returned in the arcs' own sort order.

    Targeting is by arc id ONLY; the tier is never the selector and never leaks.
    """
    override = guest.story_arc_ids or []
    base = select(StoryArc).where(StoryArc.wedding_id == wedding.id)
    if override:
        wanted = {str(x) for x in override}
        rows = (
            db.execute(base.order_by(StoryArc.sort_order, StoryArc.title)).scalars().all()
        )
        return [a for a in rows if str(a.id) in wanted]
    return (
        db.execute(
            base.where(StoryArc.visible.is_(True)).order_by(StoryArc.sort_order, StoryArc.title)
        )
        .scalars()
        .all()
    )
