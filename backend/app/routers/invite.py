"""Guest-facing, tenant-scoped invite endpoints.

  GET  /api/i/{guest_slug}        → render data for the invitation
  POST /api/i/{guest_slug}/rsvp   → submit / update the RSVP

Both resolve the tenant from the unguessable slug. The tier is never returned;
the RSVP submit enforces the tier's companion caps and the wedding's visible
questions, so a tampered client cannot grant itself a +1 or answer hidden Qs.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.answers import is_party_question, person_question_applies
from app.audit import SOURCE_GUEST, stamp_rsvp
from app.db import get_db
from app.models import Answer, Companion, CompanionKind, Rsvp, Wish
from app.schemas import (
    AnswerPublic,
    CompanionPublic,
    GuestPublic,
    InviteResponse,
    LandingResponse,
    PartyMember,
    QuestionPublic,
    RsvpConfirmation,
    RsvpPublic,
    RsvpSubmit,
    StoryArcPublic,
    WeddingPublic,
    WishCreate,
    WishCreated,
    WishPublic,
)
from app.tenancy import (
    capabilities_for,
    clamp_party_members,
    primary_wedding,
    resolve_guest,
    visible_arcs,
    visible_questions,
)
from app.validation import ContactError, normalize_email, normalize_phone

router = APIRouter(prefix="/api/i", tags=["invite"])

# Public, non-guest endpoints (the site root). Separate prefix so it never
# collides with the `/{guest_slug}` dynamic route above.
public_router = APIRouter(prefix="/api", tags=["public"])


@public_router.get("/landing", response_model=LandingResponse)
def get_landing(db: Session = Depends(get_db)) -> LandingResponse:
    """Copy for the public "no link" landing page (someone visiting the root with
    no personal link). Returns only the owner-editable `landing` block + theme."""
    wedding = primary_wedding(db)
    if wedding is None:
        raise HTTPException(status_code=404, detail="No wedding configured")
    landing = (wedding.content or {}).get("landing") or {}
    return LandingResponse(
        couple_names=wedding.couple_names,
        landing=landing,
        theme_tokens=wedding.theme_tokens,
    )


def _first_name(name: str) -> str:
    return name.strip().split(" ")[0] if name.strip() else name


# --- Owner-only data must not reach guests ----------------------------------
# The wedding row also carries owner-side settings (e.g. capacity planning in
# event_details). Guests get an ALLOWLIST of keys, never the raw dicts, so a new
# owner-only field is private by default.
_PUBLIC_EVENT_KEYS = frozenset(
    {
        "title", "venue", "address", "area", "date_iso", "start_time", "end_time",
        "date_display", "time_display", "timezone", "map_url", "dress_code",
        "getting_there",
    }
)
_PUBLIC_CONTENT_KEYS = frozenset(
    {
        "nav", "cover", "brand", "landing", "story_section", "story", "day",
        "dress_code", "faq", "rsvp", "footer", "wishes",
    }
)


def _public_wedding(wedding) -> WeddingPublic:
    return WeddingPublic(
        couple_names=wedding.couple_names,
        event_details={
            k: v for k, v in (wedding.event_details or {}).items() if k in _PUBLIC_EVENT_KEYS
        },
        content={k: v for k, v in (wedding.content or {}).items() if k in _PUBLIC_CONTENT_KEYS},
        theme_tokens=wedding.theme_tokens,
    )


# --- Contact masking ---------------------------------------------------------
# Invite links get forwarded; the GET must not hand a previously-saved contact to
# whoever holds the link. Masked values are shown as prefill; a submitted value
# still containing the mask character means "unchanged" and is ignored on POST.
_MASK = "•"


def _mask_email(email: str | None) -> str | None:
    if not email:
        return email
    local, _, domain = email.partition("@")
    return f"{local[:1]}{_MASK * 3}@{domain}"


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return phone
    if len(phone) <= 4:
        return _MASK * 4
    return f"{phone[:3]} {_MASK * 4} {phone[-4:]}"


def _serialize_rsvp(rsvp: Rsvp) -> RsvpPublic:
    # Party answers (invitee-scope + the primary's own person answers) have no
    # companion_id; each companion's answers carry its id.
    return RsvpPublic(
        attending=rsvp.attending,
        notes=rsvp.notes,
        companions=[
            CompanionPublic(
                id=c.id,
                kind=c.kind.value,
                name=c.name,
                answers=[
                    AnswerPublic(question_id=a.question_id, value=a.value) for a in c.answers
                ],
            )
            for c in rsvp.companions
        ],
        answers=[
            AnswerPublic(question_id=a.question_id, value=a.value)
            for a in rsvp.answers
            if a.companion_id is None
        ],
    )


@router.get("/{guest_slug}", response_model=InviteResponse)
def get_invite(guest_slug: str, db: Session = Depends(get_db)) -> InviteResponse:
    resolved = resolve_guest(db, guest_slug)
    if resolved is None:
        # Same 404 for "no such slug" and "not active" — don't leak which.
        raise HTTPException(status_code=404, detail="Invitation not found")
    wedding, guest = resolved

    questions = visible_questions(db, wedding, guest)
    arcs = visible_arcs(db, wedding, guest)
    existing = db.execute(select(Rsvp).where(Rsvp.guest_id == guest.id)).scalar_one_or_none()

    return InviteResponse(
        wedding=_public_wedding(wedding),
        guest=GuestPublic(
            name=guest.name,
            first_name=_first_name(guest.name),
            greeting_name=guest.greeting_name,
            email=_mask_email(guest.email),
            phone=_mask_phone(guest.phone),
            # Prefill party clamped to this guest's tier — a solo guest gets [].
            party_members=[
                PartyMember(kind=m["kind"], name=m["name"])
                for m in clamp_party_members(guest.party_members, guest.invite_tier, wedding.content)
            ],
        ),
        capabilities=capabilities_for(guest.invite_tier, wedding.content),
        story_arcs=[StoryArcPublic(id=a.id, content=a.content) for a in arcs],
        questions=[
            QuestionPublic(
                id=q.id,
                prompt=q.prompt,
                qtype=q.qtype.value,
                options=q.options,
                required=q.required,
                scope=q.scope.value,
                applies_to=q.applies_to.value,
                sort_order=q.sort_order,
            )
            for q in questions
        ],
        rsvp=_serialize_rsvp(existing) if existing else None,
    )


@router.post("/{guest_slug}/rsvp", response_model=RsvpConfirmation)
def submit_rsvp(
    guest_slug: str, payload: RsvpSubmit, db: Session = Depends(get_db)
) -> RsvpConfirmation:
    resolved = resolve_guest(db, guest_slug)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    wedding, guest = resolved

    caps = capabilities_for(guest.invite_tier, wedding.content)

    # --- Enforce the tier's companion caps (anti-tamper) ------------------
    companions = payload.companions if payload.attending else []
    adults = [c for c in companions if c.kind == "adult"]
    children = [c for c in companions if c.kind == "child"]
    if len(adults) > caps.max_adult_companions or len(children) > caps.max_child_companions:
        # Generic 422 — never reveal the cap or the tier.
        raise HTTPException(status_code=422, detail="Too many companions for this invitation")

    # --- Validate + normalize the invitee's contacts ----------------------
    # A value still carrying the mask character is the untouched masked prefill
    # from GET — treat it as "unchanged", never store or validate it.
    raw_email = payload.email if not (payload.email and _MASK in payload.email) else None
    raw_phone = payload.phone if not (payload.phone and _MASK in payload.phone) else None
    try:
        email = normalize_email(raw_email)
        phone = normalize_phone(raw_phone)
    except ContactError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # --- Validate answers against the questions this guest can actually see -
    # The party list (payload.answers) carries invitee-scope + the primary's own
    # person answers; each companion carries its person answers. Every answer must
    # target a visible question that applies to that person, and every required
    # question that applies must be answered.
    allowed_q = {q.id: q for q in visible_questions(db, wedding, guest)}
    party_answers = payload.answers if payload.attending else []

    def _validate(answer_list, *, on_party: bool, is_child: bool) -> set:
        answered: set = set()
        for a in answer_list:
            q = allowed_q.get(a.question_id)
            if q is None:
                raise HTTPException(status_code=422, detail="Unknown question")
            applies = is_party_question(q) if on_party else person_question_applies(q, is_child=is_child)
            if not applies:
                raise HTTPException(status_code=422, detail="Question not applicable")
            answered.add(a.question_id)
        return answered

    if payload.attending:
        party_answered = _validate(party_answers, on_party=True, is_child=False)
        comp_answered = [
            _validate(c.answers, on_party=False, is_child=(c.kind == "child")) for c in companions
        ]
        # Required-question enforcement, by scope + who it applies to.
        for q in allowed_q.values():
            if not q.required:
                continue
            if is_party_question(q):
                if q.id not in party_answered:
                    raise HTTPException(status_code=422, detail="A required question is unanswered")
            else:  # person-scope, applies to companions of a kind
                for c, answered in zip(companions, comp_answered):
                    if person_question_applies(q, is_child=(c.kind == "child")) and q.id not in answered:
                        raise HTTPException(
                            status_code=422, detail="A required question is unanswered"
                        )

    # --- Upsert the RSVP (one per guest); replace companions + answers -----
    rsvp = db.execute(select(Rsvp).where(Rsvp.guest_id == guest.id)).scalar_one_or_none()
    if rsvp is None:
        rsvp = Rsvp(wedding_id=wedding.id, guest_id=guest.id, attending=payload.attending)
        db.add(rsvp)
    rsvp.attending = payload.attending
    rsvp.notes = payload.notes
    # The primary's name is now editable on the RSVP and written back to the guest.
    # Only overwrite when supplied + non-blank, so a blank field never wipes it.
    if payload.name and payload.name.strip():
        guest.name = payload.name.strip()
    # Contacts live on the guest (one invitee = one contact), so import / admin can
    # set them independently of any RSVP. Only overwrite when the guest supplied a
    # value, so re-submitting a blank field doesn't wipe a previously-saved contact.
    if email is not None:
        guest.email = email
    if phone is not None:
        guest.phone = phone

    # Replace companions first and flush so each has an id before its answers are
    # attached. The answer relationship cascades, so old rows are cleared too.
    new_companions = [
        Companion(wedding_id=wedding.id, kind=CompanionKind(c.kind), name=c.name)
        for c in companions
    ]
    rsvp.companions[:] = new_companions
    db.flush()

    answer_rows = [
        Answer(wedding_id=wedding.id, question_id=a.question_id, value=a.value)
        for a in party_answers
    ]
    for comp_model, comp_payload in zip(new_companions, companions):
        for a in comp_payload.answers:
            answer_rows.append(
                Answer(
                    wedding_id=wedding.id,
                    question_id=a.question_id,
                    value=a.value,
                    companion_id=comp_model.id,
                )
            )
    rsvp.answers[:] = answer_rows

    # Audit: a guest's own submission via their signed link (no admin actor).
    stamp_rsvp(rsvp, SOURCE_GUEST)

    db.commit()
    return RsvpConfirmation(ok=True, attending=payload.attending, companion_count=len(companions))


# --- Wishes / guestbook ----------------------------------------------------
@router.get("/{guest_slug}/wishes", response_model=list[WishPublic])
def list_wishes(guest_slug: str, db: Session = Depends(get_db)) -> list[WishPublic]:
    """Approved guestbook messages for this wedding, newest first. The slug only
    serves to resolve (and gate access to) the tenant — every guest of the same
    wedding sees the same wall."""
    resolved = resolve_guest(db, guest_slug)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    wedding, _ = resolved
    rows = (
        db.execute(
            select(Wish)
            .where(Wish.wedding_id == wedding.id, Wish.approved.is_(True))
            .order_by(Wish.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [WishPublic(name=w.name, message=w.message, created_at=w.created_at) for w in rows]


@router.post("/{guest_slug}/wishes", response_model=WishCreated, status_code=201)
def create_wish(
    guest_slug: str, payload: WishCreate, db: Session = Depends(get_db)
) -> WishCreated:
    """Leave a guestbook message. Tied to the resolved guest so the owner can
    moderate by person. Held UNAPPROVED on arrival — the couple must approve it
    from /admin before it shows on the public wall."""
    resolved = resolve_guest(db, guest_slug)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    wedding, guest = resolved
    wish = Wish(
        wedding_id=wedding.id,
        guest_id=guest.id,
        name=payload.name.strip(),
        message=payload.message.strip(),
        approved=False,
    )
    db.add(wish)
    db.commit()
    return WishCreated(ok=True, approved=wish.approved)
