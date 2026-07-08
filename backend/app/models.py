"""ORM models. Multi-tenant: a root `Wedding` owns everything; every other row
carries `wedding_id`. v1 seeds exactly one wedding. RLS (see migrations) is the
DB-level backstop; the API also scopes every query by wedding (app/tenancy.py).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class InviteTier(str, enum.Enum):
    """What a guest's personal link silently allows. Never surfaced in the UI."""

    solo = "solo"
    plus_one = "plus_one"
    plus_family = "plus_family"


class QuestionType(str, enum.Enum):
    choice = "choice"  # single select
    multi_choice = "multi_choice"  # pick any number of the options
    text = "text"
    number = "number"
    yesno = "yesno"


class QuestionVisibility(str, enum.Enum):
    all = "all"  # everyone sees it
    tier = "tier"  # only the invite_tiers listed in visibility_ref
    guests = "guests"  # only the guest ids listed in visibility_ref


class QuestionScope(str, enum.Enum):
    """Who answers a question.

    `invitee` — asked once for the whole party (stored on the primary, companion_id
    NULL). `person` — asked of each attending person (primary + every companion that
    `applies_to` matches), one answer row per person.
    """

    invitee = "invitee"
    person = "person"


class QuestionApplies(str, enum.Enum):
    """For `person`-scope questions, which attendees are asked. Ignored for
    `invitee` scope. `children` is how "age, required for kids only" is expressed.
    """

    everyone = "everyone"
    adults = "adults"  # the primary + adult companions
    children = "children"


class CompanionKind(str, enum.Enum):
    adult = "adult"
    child = "child"


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Wedding(Base):
    """Tenant root. v1 = one row (Alex & Sam)."""

    __tablename__ = "weddings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    # Supabase auth user id of the PRIMARY owner / creator. Nullable until an
    # owner signs in (v1). Future two-tier admin model (see PLAN.md) adds a
    # `wedding_members` join table for nominated co-admins — additive, this stays
    # as the creator.
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    couple_names: Mapped[str] = mapped_column(String(200))
    # Structured but flexible content so it's editable per-wedding (future editor).
    event_details: Mapped[dict] = mapped_column(JSON, default=dict)  # venue/date/time/map
    content: Mapped[dict] = mapped_column(JSON, default=dict)  # story/dress/faq sections
    theme_tokens: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # override of default template
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    guests: Mapped[list[Guest]] = relationship(back_populates="wedding", cascade="all, delete-orphan")
    questions: Mapped[list[Question]] = relationship(back_populates="wedding", cascade="all, delete-orphan")
    wishes: Mapped[list[Wish]] = relationship(back_populates="wedding", cascade="all, delete-orphan")
    story_arcs: Mapped[list[StoryArc]] = relationship(
        back_populates="wedding", cascade="all, delete-orphan"
    )


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    wedding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("weddings.id", ondelete="CASCADE"), index=True
    )
    # Globally unique, unguessable. Resolves to (wedding, guest) — carries the tenant.
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # The PRIMARY attendee's name (one party member, not the invite's identity).
    # Optional now — the invite is identified by `slug` and labelled by `greeting_name`.
    # Prefills the primary's editable Name field on the RSVP and is written back when
    # the guest confirms/edits it. "" = no name yet. The +1/kids live in
    # `party_members` (prefill) / Companion rows (response).
    name: Mapped[str] = mapped_column(String(200), default="")
    # Mandatory invite greeting — the ONLY thing shown in the cover's "Dear …" line
    # (e.g. "John & Jane"). Party-level, never per-companion.
    greeting_name: Mapped[str] = mapped_column(String(120))
    # Admin-curated PREFILL party: [{"kind": "adult"|"child", "name": str}]. Set in the
    # admin form / import; seeds the RSVP companions ONLY when no RSVP exists yet. Once
    # the guest responds, the Rsvp's Companion rows are the source of truth (this is
    # never re-synced from a submission). Clamped to the tier's caps on write/serialize.
    party_members: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Invitee contact for the couple's comms. Set by the guest at RSVP time and/or
    # by the owner via admin / spreadsheet import. Email is format-validated and
    # phone normalized to E.164 (see app/validation.py) before it lands here.
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    side: Mapped[str | None] = mapped_column(String(40), nullable=True)  # Alex / Sam
    relationship_label: Mapped[str | None] = mapped_column("relationship", String(80), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    batch: Mapped[str | None] = mapped_column(String(40), nullable=True)
    invite_tier: Mapped[InviteTier] = mapped_column(
        Enum(InviteTier, name="invite_tier"), default=InviteTier.solo
    )
    # Owner's pre-RSVP estimate of how many people this invite will bring (incl. the
    # invitee). Admin-only — never sent to the guest or used in the RSVP flow; it's a
    # planning aid the owner compares against the real `party_size` as RSVPs land.
    expected_party_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    invited: Mapped[bool] = mapped_column(Boolean, default=True)
    # Whether the owner has SENT this guest their invite (copied the link/message and
    # passed it on). Drives the "Invited" status between Pending (created, not yet
    # contacted) and a real RSVP reply. Set manually by the owner (per-row toggle,
    # bulk action, or the edit dialog) — distinct from `invited` ("on the guest list").
    invite_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # Per-guest story-arc override. NULL/empty = this guest sees every `visible`
    # arc (the default). A non-empty list = they see exactly these arc ids,
    # ordered by the arcs' own sort_order. Targeting is by arc id ONLY — the
    # invite_tier must never be the selector, so this never leaks the tier.
    story_arc_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    seed_meta: Mapped[dict] = mapped_column(JSON, default=dict)  # raw import row, prob tier, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    wedding: Mapped[Wedding] = relationship(back_populates="guests")
    rsvp: Mapped[Rsvp | None] = relationship(
        back_populates="guest", uselist=False, cascade="all, delete-orphan"
    )


class Rsvp(Base):
    __tablename__ = "rsvps"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    wedding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("weddings.id", ondelete="CASCADE"), index=True
    )
    guest_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("guests.id", ondelete="CASCADE"), unique=True, index=True
    )
    attending: Mapped[bool] = mapped_column(Boolean)
    # The FIRST reply time (set once on insert). `updated_at` below tracks the latest
    # change — together they let the admin surface new vs recently-edited RSVPs.
    responded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Audit provenance (stamped via app/audit.py). `first_source` is where the very
    # first reply came from (never overwritten); `last_source` is the latest write.
    # Both are "guest" | "admin" | "import". `last_actor` is the admin email for
    # owner/import writes, NULL for a guest's own submission.
    first_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_actor: Mapped[str | None] = mapped_column(String(254), nullable=True)
    # Free "note to the couple". Dietary / how-you-know / song are now admin-defined
    # questions (see Question/Answer), not packed into this blob.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    guest: Mapped[Guest] = relationship(back_populates="rsvp")
    companions: Mapped[list[Companion]] = relationship(
        back_populates="rsvp", cascade="all, delete-orphan"
    )
    answers: Mapped[list[Answer]] = relationship(back_populates="rsvp", cascade="all, delete-orphan")


class Companion(Base):
    """A +1 or a child attached to an RSVP. Existence gated by the guest's tier."""

    __tablename__ = "companions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    wedding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("weddings.id", ondelete="CASCADE"), index=True
    )
    rsvp_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rsvps.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[CompanionKind] = mapped_column(Enum(CompanionKind, name="companion_kind"))
    # The only universal per-person field. Everything else (dietary, age, …) is an
    # admin-defined Question answered per person (Answer.companion_id → this row).
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    rsvp: Mapped[Rsvp] = relationship(back_populates="companions")
    answers: Mapped[list[Answer]] = relationship(
        back_populates="companion", cascade="all, delete-orphan"
    )


class Question(Base):
    """A custom RSVP question authored by the owner."""

    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    wedding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("weddings.id", ondelete="CASCADE"), index=True
    )
    prompt: Mapped[str] = mapped_column(String(400))
    qtype: Mapped[QuestionType] = mapped_column(Enum(QuestionType, name="question_type"))
    options: Mapped[list] = mapped_column(JSON, default=list)  # for choice / multi_choice
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    # Asked once per party (`invitee`) or of each attendee (`person`). `applies_to`
    # narrows a person-scope question to a subset of attendees (e.g. children only).
    scope: Mapped[QuestionScope] = mapped_column(
        Enum(QuestionScope, name="question_scope"), default=QuestionScope.invitee
    )
    applies_to: Mapped[QuestionApplies] = mapped_column(
        Enum(QuestionApplies, name="question_applies"), default=QuestionApplies.everyone
    )
    visibility: Mapped[QuestionVisibility] = mapped_column(
        Enum(QuestionVisibility, name="question_visibility"), default=QuestionVisibility.all
    )
    visibility_ref: Mapped[list] = mapped_column(JSON, default=list)  # tiers or guest ids
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    wedding: Mapped[Wedding] = relationship(back_populates="questions")
    answers: Mapped[list[Answer]] = relationship(back_populates="question", cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    wedding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("weddings.id", ondelete="CASCADE"), index=True
    )
    rsvp_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rsvps.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    # Which person this answer is for. NULL = the primary invitee (or an
    # invitee-scope/party answer); a value = that companion. The question's `scope`
    # disambiguates a NULL primary person-answer from a NULL party answer.
    companion_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("companions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Shape depends on the question type: {"text"|"number"|"choice"|"yesno": ...}
    # or {"choices": [...]} for multi_choice.
    value: Mapped[dict] = mapped_column(JSON, default=dict)

    rsvp: Mapped[Rsvp] = relationship(back_populates="answers")
    question: Mapped[Question] = relationship(back_populates="answers")
    companion: Mapped[Companion | None] = relationship(back_populates="answers")


class StoryArc(Base):
    """One configurable story arc shown on the invite.

    `content` is the same loose shape the invite's Story section renders:
    `{kicker, heading, intro, beats:[{image,text,wide,onoma}], climax:{...}|null}`.
    Beats are numbered by POSITION on render (no stored bullet number), so the
    owner just adds rows of text + an uploaded image. The trailing `climax` is the
    optional, unnumbered "you're invited" finale.

    v1 seeds exactly one visible arc. Phase 3 adds multiplicity (show/hide via
    `visible`, ordering via `sort_order`) and per-guest targeting — modelled here
    already so that's purely additive.
    """

    __tablename__ = "story_arcs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    wedding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("weddings.id", ondelete="CASCADE"), index=True
    )
    # Owner-only label (e.g. "Chapter Two", "Sam's family version"). Never sent
    # to guests — the invite exposes arc content only, not this internal name.
    title: Mapped[str] = mapped_column(String(200), default="Our story")
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[dict] = mapped_column(JSON, default=dict)

    wedding: Mapped[Wedding] = relationship(back_populates="story_arcs")


class Wish(Base):
    """Guestbook message."""

    __tablename__ = "wishes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    wedding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("weddings.id", ondelete="CASCADE"), index=True
    )
    guest_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("guests.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    # Public wall shows approved wishes only. Guest submissions arrive UNAPPROVED
    # (the create endpoint sets approved=False); the owner approves from /admin.
    # The column default stays True for rows the owner/seed inserts directly.
    approved: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    wedding: Mapped[Wedding] = relationship(back_populates="wishes")
    # Who left it (if an invited guest); unidirectional — SET NULL on delete.
    guest: Mapped[Guest | None] = relationship()


# All tenant tables (used by migrations to enable RLS uniformly).
TENANT_TABLES = ["guests", "rsvps", "companions", "questions", "answers", "wishes", "story_arcs"]
ALL_TABLES = ["weddings", *TENANT_TABLES]
