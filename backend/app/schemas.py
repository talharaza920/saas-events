"""API contracts (Pydantic v2). These shapes become `frontend/types/api.ts` via
OpenAPI, so the guest site (M4/M5) and admin (M6) stay in lockstep with the API.

Security note: the guest-facing payloads deliberately expose **capabilities**
(can this person bring a +1 / kids, and how many) rather than the raw
`invite_tier`. A `solo` guest must never be able to tell a +1 was an option, so
the tier string never crosses the wire. See `app/tenancy.py`.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --- Free-form JSON bounds ---------------------------------------------------
# The owner-editable JSON blobs (content / event_details / theme_tokens / story
# arc content) are open dicts by design, but unbounded input lets a hostile
# client nest thousands of levels (RecursionError in _deep_merge → 500) or stuff
# megabytes into one PATCH. Generous ceilings — far above anything the editor
# produces — enforced at the schema edge so every handler gets bounded input.
_JSON_MAX_DEPTH = 16
_JSON_MAX_NODES = 25_000  # containers + leaves, whole blob
_JSON_MAX_STR = 50_000  # chars per string leaf (a long story beat is ~1k)


def _check_json_bounds(value: Any) -> Any:
    """Reject a JSON blob that is too deep, too big, or has huge string leaves.
    Depth is checked BEFORE recursing, so this walker itself can't blow the stack."""
    nodes = 0

    def walk(v: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > _JSON_MAX_NODES:
            raise ValueError("This content is too large")
        if depth > _JSON_MAX_DEPTH:
            raise ValueError("This content is nested too deeply")
        if isinstance(v, dict):
            for child in v.values():
                walk(child, depth + 1)
        elif isinstance(v, list):
            for child in v:
                walk(child, depth + 1)
        elif isinstance(v, str) and len(v) > _JSON_MAX_STR:
            raise ValueError("A text value in this content is too long")

    if value is not None:
        walk(value, 1)
    return value


def _bounded_json(*fields: str):
    """A reusable pydantic validator applying `_check_json_bounds` to `fields`.
    (Same pattern as `_no_duplicate_questions`: a plain one-arg callable.)"""
    return field_validator(*fields)(_check_json_bounds)


# --- Wedding (public, tenant content) -------------------------------------
class WeddingPublic(BaseModel):
    """The themeable, data-driven content for one wedding's invite."""

    couple_names: str
    event_details: dict[str, Any]
    content: dict[str, Any]
    # Partial token override (deep-merged onto the default template client-side).
    theme_tokens: dict[str, Any] | None = None


class LandingResponse(BaseModel):
    """Public "no link" landing page (the site root for someone without an invite).

    Carries only the landing copy + theme tokens — no guest, no tier, no event
    internals beyond what the owner put in the landing block.
    """

    couple_names: str
    landing: dict[str, Any]
    theme_tokens: dict[str, Any] | None = None


# --- Guest + capabilities --------------------------------------------------
class PartyMember(BaseModel):
    """One pre-filled attendee (the +1 adult or a child). Just kind + name — the
    companion's own questions are answered at RSVP time, not pre-filled."""

    kind: str  # "adult" | "child"
    name: str = ""


class GuestPublic(BaseModel):
    """Only what the invite UI needs to greet the guest. No tier, no id leak.

    `email`/`phone` are the guest's OWN previously-saved contacts, returned so the
    RSVP form can prefill them (editable). They come back MASKED (invite links get
    forwarded, so the holder of a link must not learn a saved contact); submitting
    the masked value back means "unchanged".
    """

    name: str
    first_name: str
    # Mandatory invite greeting — the only thing the cover's "Dear …" line shows.
    greeting_name: str
    email: str | None = None
    phone: str | None = None
    # Admin-curated prefill party, CLAMPED to this guest's capabilities (a solo guest
    # always gets []). The RSVP seeds the +1/kids from this when no RSVP exists yet.
    # Only names — no tier leak; `capabilities` already signals whether a +1 is allowed.
    party_members: list[PartyMember] = []


class Capabilities(BaseModel):
    """Tier-derived limits, expressed so the UI never learns the tier name.

    The RSVP form renders identical chrome for everyone and simply omits the
    companion fields when the caps are zero.
    """

    allow_plus_one: bool
    allow_kids: bool
    max_adult_companions: int = Field(ge=0)
    max_child_companions: int = Field(ge=0)
    # True only for plus_family: render an add/remove ADULTS list (multiple extra
    # adults) instead of the single +1 toggle. A capability, not the tier name —
    # solo/plus_one stay False, so a lower tier still can't tell it was eligible.
    adults_multi: bool = False


# --- Questions (only the ones visible to this guest) -----------------------
class QuestionPublic(BaseModel):
    id: UUID
    prompt: str
    qtype: str  # choice | multi_choice | text | number | yesno
    options: list[Any]
    required: bool
    scope: str  # invitee | person
    applies_to: str  # everyone | adults | children (person scope only)
    sort_order: int


# --- Existing RSVP (so a returning guest can edit) -------------------------
class AnswerPublic(BaseModel):
    question_id: UUID
    value: dict[str, Any]


class CompanionPublic(BaseModel):
    # `id` lets the client map this companion's answers back on edit.
    id: UUID
    kind: str  # adult | child
    name: str | None = None
    answers: list[AnswerPublic] = []


class RsvpPublic(BaseModel):
    attending: bool
    notes: str | None = None
    companions: list[CompanionPublic] = []
    # Invitee-scope + the primary person's own answers (companion_id NULL).
    answers: list[AnswerPublic] = []


class StoryArcPublic(BaseModel):
    """A story arc as the guest sees it — content only.

    The owner-facing `title`/`visible`/`sort_order` are deliberately omitted (an
    arc's internal label may hint at targeting, e.g. "Sam's family version").
    `id` is a stable, non-secret key for the carousel; the tier never appears.
    """

    id: UUID
    content: dict[str, Any]


class InviteResponse(BaseModel):
    """Everything the guest site needs to render the invitation for one link."""

    wedding: WeddingPublic
    guest: GuestPublic
    capabilities: Capabilities
    questions: list[QuestionPublic]
    # Story arcs this guest should see (ordered). v1: all visible arcs. Phase 3
    # narrows this per-guest. Empty falls back to the legacy `content.story`.
    story_arcs: list[StoryArcPublic] = []
    rsvp: RsvpPublic | None = None
    # False once the wedding's optional RSVP deadline has passed — the invite
    # still renders, but submits are refused (the form should read-only itself).
    # Just a boolean: the deadline date itself is the owner's business.
    rsvp_open: bool = True


# --- RSVP submission -------------------------------------------------------
# Guest-supplied answer values are bounded to the known shapes so a hostile
# client can't stuff megabytes of arbitrary JSON into the answers table.
_ANSWER_TEXT_MAX = 2000
_ANSWER_CHOICE_MAX = 500
_ANSWER_CHOICES_MAX = 32


class AnswerSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: UUID
    # Exactly one of: {"text": str} {"number": int} {"choice": str}
    # {"choices": [str, …]} {"yesno": bool} — or {} for "cleared".
    value: dict[str, Any]

    @field_validator("value")
    @classmethod
    def _known_shape(cls, v: dict[str, Any]) -> dict[str, Any]:
        if v == {}:
            return v
        if len(v) != 1:
            raise ValueError("Answer value must have exactly one key")
        key, val = next(iter(v.items()))
        if key == "text":
            if not isinstance(val, str) or len(val) > _ANSWER_TEXT_MAX:
                raise ValueError("Invalid text answer")
        elif key == "number":
            if isinstance(val, bool) or not isinstance(val, int) or abs(val) > 1_000_000:
                raise ValueError("Invalid number answer")
        elif key == "choice":
            if not isinstance(val, str) or len(val) > _ANSWER_CHOICE_MAX:
                raise ValueError("Invalid choice answer")
        elif key == "choices":
            if (
                not isinstance(val, list)
                or len(val) > _ANSWER_CHOICES_MAX
                or not all(isinstance(c, str) and len(c) <= _ANSWER_CHOICE_MAX for c in val)
            ):
                raise ValueError("Invalid choices answer")
        elif key == "yesno":
            if not isinstance(val, bool):
                raise ValueError("Invalid yes/no answer")
        else:
            raise ValueError("Unknown answer shape")
        return v


def _no_duplicate_questions(answers: list[AnswerSubmit]) -> list[AnswerSubmit]:
    seen = {a.question_id for a in answers}
    if len(seen) != len(answers):
        raise ValueError("Duplicate answers for the same question")
    return answers


class CompanionSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern="^(adult|child)$")
    name: str | None = Field(default=None, max_length=200)
    # This person's answers to `person`-scope questions (e.g. their dietary, a
    # child's age). Validated against the question's scope/applies_to server-side.
    answers: list[AnswerSubmit] = Field(default=[], max_length=100)

    _dedupe_answers = field_validator("answers")(_no_duplicate_questions)


class RsvpSubmit(BaseModel):
    """A guest's RSVP. Companions/answers are validated against the guest's tier
    and the wedding's visible questions server-side — the client cannot widen
    its own invite by posting extra companions."""

    model_config = ConfigDict(extra="forbid")

    attending: bool
    notes: str | None = Field(default=None, max_length=2000)
    # The primary attendee's (possibly edited) name, written back to Guest.name. Blank
    # leaves the stored name untouched — re-submitting an empty field never wipes it.
    name: str | None = Field(default=None, max_length=200)
    # Invitee contacts (the guest's own). Free-form here; normalized + validated in
    # the endpoint (E.164 phone, format-checked email) — invalid → 422.
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=32)
    companions: list[CompanionSubmit] = Field(default=[], max_length=40)
    # Invitee-scope answers + the primary person's own person-scope answers.
    answers: list[AnswerSubmit] = Field(default=[], max_length=100)

    _dedupe_answers = field_validator("answers")(_no_duplicate_questions)


class RsvpConfirmation(BaseModel):
    ok: bool = True
    attending: bool
    companion_count: int


# --- Wishes / guestbook (public) ------------------------------------------
class WishPublic(BaseModel):
    """A guestbook message as shown on the public wall (approved only)."""

    name: str
    message: str
    created_at: datetime


class WishCreate(BaseModel):
    """A guest leaving a message. Tied server-side to the resolved guest."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=1000)


class WishCreated(BaseModel):
    ok: bool = True
    approved: bool


# =========================================================================
# Admin (owner-authenticated). Unlike the guest payloads, the admin DOES see
# and set the invite_tier — the owner is the one authoring the invites. These
# endpoints are gated by app/auth.get_current_owner and scoped to the owner's
# wedding.
# =========================================================================
_TIER_PATTERN = "^(solo|plus_one|plus_family)$"
_QTYPE_PATTERN = "^(choice|multi_choice|text|number|yesno)$"
_VISIBILITY_PATTERN = "^(all|tier|guests)$"
_SCOPE_PATTERN = "^(invitee|person)$"
_APPLIES_PATTERN = "^(everyone|adults|children)$"


# --- Whoami / dashboard header --------------------------------------------
class AdminMe(BaseModel):
    email: str
    via: str
    wedding_id: UUID
    wedding_slug: str
    couple_names: str
    # The caller's effective role on THIS wedding: admin | owner | platform.
    role: str
    # Lifecycle: draft | pending_approval | active | suspended | archived, plus
    # the independent publication switch. Drives the dashboard's status banner.
    wedding_status: str
    published: bool
    # Whether this caller may toggle publication (owner, or admin when the
    # owner granted it via settings.admins_can_publish).
    can_publish: bool
    # Effective entitlements for the wedding (plan ∪ overrides; Phase 5). The UI
    # uses this to gray out features — the server re-checks on every write.
    entitlements: dict[str, Any] = {}
    # Upload bytes attributed to this wedding, for showing usage against
    # entitlements.max_storage_mb (counter; reconciled by the cron job).
    storage_bytes_used: int = 0


# --- RSVP rollup pieces (defined before GuestAdmin, which embeds them) ------
class AnswerAdmin(BaseModel):
    question_id: UUID
    prompt: str
    qtype: str
    value: dict[str, Any]


class CompanionAdmin(BaseModel):
    id: UUID  # stable key so the owner can edit/remove this companion
    kind: str  # adult | child
    name: str | None = None
    # This person's answers to person-scope questions.
    answers: list[AnswerAdmin] = []


# --- Guests ----------------------------------------------------------------
class GuestAdmin(BaseModel):
    """A guest row as the owner sees it — tier visible, with RSVP rollup."""

    id: UUID
    slug: str
    invite_path: str  # "/i/{slug}" — the shareable link path
    name: str  # the primary attendee's name (may be "" — the invite is labelled by greeting)
    # Mandatory invite greeting — the label/identity of the invite and the "Dear …" line.
    greeting_name: str
    # Admin-curated prefill party (the +1/kids' names). Clamped to the tier on write.
    party_members: list[PartyMember] = []
    email: str | None = None
    phone: str | None = None
    side: str | None = None
    relationship: str | None = None
    group_name: str | None = None
    batch: str | None = None
    invite_tier: str  # solo | plus_one | plus_family
    invited: bool
    # Whether the owner has sent this guest their invite (drives the "Invited" status).
    invite_sent: bool = False
    # Owner's pre-RSVP headcount estimate (incl. the invitee). Admin-only; compared
    # against the real `party_size` below as RSVPs come in. Null = no estimate yet.
    expected_party_size: int | None = None
    # Per-guest story-arc override (arc ids). Empty = sees every visible arc.
    story_arc_ids: list[UUID] = []
    rsvp_status: str  # attending | declined | invited | pending
    party_size: int  # 0 if not attending/pending; else 1 + companions
    notes: str | None = None
    responded_at: datetime | None = None  # first reply
    # Audit trail (see app/audit.py): when this RSVP last changed, where the latest
    # change + the first reply came from, and which admin (if any) made the change.
    updated_at: datetime | None = None
    first_source: str | None = None  # guest | admin | import
    last_source: str | None = None
    last_actor: str | None = None  # admin email for owner/import edits; null for guest
    # RSVP rollup so one /guests call powers both the combined and split views.
    companions: list[CompanionAdmin] = []
    # Invitee-scope + the primary person's own answers.
    answers: list[AnswerAdmin] = []


class GuestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # The primary attendee's name — optional (the guest can fill it at RSVP). The
    # invite is identified by its slug and labelled by the greeting.
    name: str = Field(default="", max_length=200)
    invite_tier: str = Field(default="solo", pattern=_TIER_PATTERN)
    # Mandatory invite greeting — the "Dear …" line and the admin label.
    greeting_name: str = Field(min_length=1, max_length=120)
    # Admin-curated prefill party (the +1/kids' names). Clamped to the tier server-side.
    party_members: list[PartyMember] = []
    # Contacts — normalized + validated in the router (E.164 phone, format email).
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=32)
    side: str | None = Field(default=None, max_length=40)
    relationship: str | None = Field(default=None, max_length=80)
    group_name: str | None = Field(default=None, max_length=120)
    batch: str | None = Field(default=None, max_length=40)
    invited: bool = True
    # Owner's pre-RSVP headcount estimate (incl. the invitee). Admin-only.
    expected_party_size: int | None = Field(default=None, ge=0, le=50)
    # Story-arc override; ids are validated against the wedding's arcs server-side.
    story_arc_ids: list[UUID] | None = None


class GuestUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Primary attendee's name; omit to leave unchanged, "" to clear (invite stays
    # labelled by its greeting).
    name: str | None = Field(default=None, max_length=200)
    invite_tier: str | None = Field(default=None, pattern=_TIER_PATTERN)
    # Mandatory greeting — omit to leave unchanged; a present value must be non-empty
    # (min_length=1 rejects "" with a 422, so the invite can never lose its label).
    greeting_name: str | None = Field(default=None, min_length=1, max_length=120)
    # Admin-curated prefill party; omit to leave unchanged. Clamped to the tier.
    party_members: list[PartyMember] | None = None
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=32)
    side: str | None = Field(default=None, max_length=40)
    relationship: str | None = Field(default=None, max_length=80)
    group_name: str | None = Field(default=None, max_length=120)
    batch: str | None = Field(default=None, max_length=40)
    invited: bool | None = None
    # Owner's pre-RSVP headcount estimate (incl. the invitee). Admin-only; omit to
    # leave unchanged, send null to clear the estimate.
    expected_party_size: int | None = Field(default=None, ge=0, le=50)
    # Story-arc override; null leaves it unchanged, [] clears it (back to default).
    story_arc_ids: list[UUID] | None = None


class GuestRsvpUpdate(BaseModel):
    """Owner edit of a guest's RSVP from /admin — set the attendance status and,
    when attending, the party answers (the primary person's own + invitee-scope).

    `status`: `attending` / `declined` / `invited` / `pending`. `pending` clears any
    RSVP back to "no response, not yet contacted"; `invited` clears the RSVP but marks
    the guest as having been sent their invite. `declined` keeps the RSVP but drops
    companions + answers.
    `answers`, when provided (attending only), REPLACES the party answer list
    (companion_id NULL) wholesale; each must be a party question (invitee-scope, or
    person-scope applying to an adult — the primary counts as an adult).
    `companions`, when provided (attending only), REPLACES the whole companion party
    — each +1/child with its name and its own person-scope answers (e.g. a child's
    age, a +1's dietary). Validated against the tier's caps and each question's
    scope/applies_to server-side. Omit it to leave the companion party as-is (the
    single-companion endpoint still edits one at a time).
    """

    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern="^(attending|declined|invited|pending)$")
    notes: str | None = Field(default=None, max_length=2000)
    answers: list[AnswerSubmit] | None = None
    companions: list[CompanionSubmit] | None = None


class BulkGuestIds(BaseModel):
    """A selection of this wedding's guests to act on in one shot. Ids that don't
    belong to the owner's wedding are silently ignored (the response `count` is the
    number actually affected), so a stray/foreign id can never touch another tenant."""

    model_config = ConfigDict(extra="forbid")
    ids: list[UUID] = Field(min_length=1)


class BulkRsvpUpdate(BulkGuestIds):
    """Set the attendance status for many guests at once (no answers — those stay
    as authored). `attending` keeps any existing party/answers; `declined` drops
    the party; `invited` marks invites as sent; `pending` clears the RSVP back to
    "no response"."""

    status: str = Field(pattern="^(attending|declined|invited|pending)$")


class BulkResult(BaseModel):
    count: int  # guests actually affected (foreign/unknown ids excluded)


class CompanionUpdate(BaseModel):
    """Owner edit of a single companion (the +1 or a child on an RSVP).

    `kind` is structural (set by the invite/RSVP) and not editable here. `name` is
    left unchanged when omitted. `answers`, when provided, REPLACES this companion's
    person-scope answers wholesale (validated against the wedding's questions).
    """

    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=200)
    answers: list[AnswerSubmit] | None = None


# --- Questions (full CRUD view) -------------------------------------------
class QuestionAdmin(BaseModel):
    id: UUID
    prompt: str
    qtype: str
    options: list[Any]
    required: bool
    scope: str
    applies_to: str
    visibility: str
    visibility_ref: list[Any]
    sort_order: int


class QuestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=400)
    qtype: str = Field(pattern=_QTYPE_PATTERN)
    options: list[str] = []
    required: bool = False
    scope: str = Field(default="invitee", pattern=_SCOPE_PATTERN)
    applies_to: str = Field(default="everyone", pattern=_APPLIES_PATTERN)
    visibility: str = Field(default="all", pattern=_VISIBILITY_PATTERN)
    visibility_ref: list[str] = []
    sort_order: int = 0


class QuestionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str | None = Field(default=None, min_length=1, max_length=400)
    qtype: str | None = Field(default=None, pattern=_QTYPE_PATTERN)
    options: list[str] | None = None
    required: bool | None = None
    scope: str | None = Field(default=None, pattern=_SCOPE_PATTERN)
    applies_to: str | None = Field(default=None, pattern=_APPLIES_PATTERN)
    visibility: str | None = Field(default=None, pattern=_VISIBILITY_PATTERN)
    visibility_ref: list[str] | None = None
    sort_order: int | None = None


# --- Responses + summary ---------------------------------------------------
# (CompanionAdmin / AnswerAdmin are defined above, before GuestAdmin which embeds them.)
class ResponseAdmin(BaseModel):
    guest_id: UUID
    guest_name: str
    slug: str
    attending: bool
    responded_at: datetime  # first reply
    updated_at: datetime | None = None  # latest change
    last_source: str | None = None  # guest | admin | import
    last_actor: str | None = None  # admin email for owner/import edits; null for guest
    notes: str | None = None
    companions: list[CompanionAdmin] = []
    answers: list[AnswerAdmin] = []


class OptionCount(BaseModel):
    """One bar in a question breakdown: an answer value and how many chose it."""

    label: str
    count: int


class QuestionBreakdown(BaseModel):
    """Tally of a categorical question's answers across ATTENDING people/parties.

    Generic over the question engine — every choice/multi_choice/yesno question is
    summarized the same way (this is how "how many Halal", "ages", etc. surface,
    without hardcoding any one question). `applicable` is how many people/parties
    could have answered (attending + matching the question's scope/applies_to);
    `answered` is how many actually did.
    """

    question_id: UUID
    prompt: str
    qtype: str  # choice | multi_choice | yesno
    scope: str  # invitee | person
    applies_to: str  # everyone | adults | children
    applicable: int
    answered: int
    counts: list[OptionCount] = []


class GroupBreakdown(BaseModel):
    """One row of a grouped RSVP rollup — by side / batch / invite tier / relationship
    / group. Carries BOTH lenses so the same shape feeds the status bars and the
    headcount block: the four invitation-status counts (`pending`/`invited`/
    `attending`/`declined`, summing to `invitations`) and the people headcount
    (`head_count` confirmed vs `expected_head_count` estimated). `key` is a stable
    bucket id (`__unassigned__` for the no-value bucket); `label` is what's shown.
    `children` holds one optional level of sub-grouping (the pivot's "then by")."""

    key: str
    label: str
    invitations: int  # parties/links in this bucket (the invitation lens)
    pending: int  # created, not yet contacted
    invited: int  # invite sent, no reply yet
    attending: int  # RSVP yes
    declined: int  # RSVP no
    head_count: int  # confirmed attending people (primaries + companions)
    # Expected people for the `invited` invites only (invite sent, no reply yet) — the
    # "still TBD" headcount for the capacity lens. Excludes pending (not yet contacted)
    # and declined, so confirmed (`head_count`) + this is what's committed against capacity.
    invited_people: int = 0
    expected_head_count: int  # owner's pre-RSVP people estimate for this bucket
    # The people lens: confirmed heads for attending invites + the expected estimate
    # for everyone else (invited/pending/declined). This is what the People charts plot.
    people: int
    children: list["GroupBreakdown"] = []


class PivotSummary(BaseModel):
    """Interactive status pivot for the Overview (GET /summary/pivot). Invitation
    status + headcount grouped by `by`, optionally sub-grouped by `then`.
    `available_dims` lists the dimensions that actually split THIS guest list into
    ≥2 buckets (empty/single-value ones are omitted from the selector). `total` is
    the all-guests rollup for the footer/denominators."""

    by: str
    then: str | None = None
    available_dims: list[str] = []
    groups: list[GroupBreakdown] = []
    total: GroupBreakdown


class CapacityConfig(BaseModel):
    """Owner-set guest capacity (people, not invitations), echoed from the wedding's
    `event_details.capacity`. `total` is the venue ceiling; `by_side` is an optional
    per-side ceiling keyed by the side label (e.g. "Alex"/"Sam"). Either can be
    unset — the capacity chart then just shows the used count without a ceiling."""

    total: int | None = None
    by_side: dict[str, int] = {}


class AdminSummary(BaseModel):
    total_guests: int  # number of invitations (one per party/link)
    attending: int  # invitations whose RSVP says yes
    declined: int
    invited: int  # no reply yet, but the owner has sent the invite
    pending: int  # no reply yet, not yet contacted
    invite_sent_count: int = 0  # invitations whose link the owner has sent (invited + replied)
    head_count: int  # attending primaries + their companions (confirmed people = attending_people)
    # People-lens split of the not-yet-confirmed buckets (expected estimate). With
    # `head_count` (attending) these four make the hero's people-by-status bar.
    invited_people: int = 0
    pending_people: int = 0
    declined_people: int = 0
    extra_adults: int
    extra_children: int  # attending children — also the kids'-chair count
    # Owner's pre-RSVP planning estimate of total people, using the fallback chain
    # expected_party_size → prefilled party_members count → 1 (the invitee). Compare
    # against `head_count` to watch attendance firm up.
    expected_head_count: int
    # Owner-set capacity (people) for the capacity-utilization chart. Echoed from
    # event_details so the Overview can render it without a separate content fetch.
    capacity: CapacityConfig = CapacityConfig()
    # Per-question tallies over attending people/parties (dietary/Halal, ages, …).
    question_breakdowns: list[QuestionBreakdown] = []
    # RSVP rollup grouped by guest side (Alex's vs Sam's), for the headcount block.
    # Empty when no guest has a side set. Sorted by invitation count desc, "Unassigned" last.
    by_side: list[GroupBreakdown] = []
    # RSVP rollup grouped by invite tier (solo / plus-one / family), for the invitee-mix
    # block. Empty when every guest is the same tier (nothing to split).
    by_tier: list[GroupBreakdown] = []
    # New replies (by first-reply time) in the trailing 7 days and the 7 before it —
    # powers the "this week vs last week" momentum stat (full series is /summary/timeline).
    replies_this_week: int = 0
    replies_last_week: int = 0


class TimelinePoint(BaseModel):
    """One weekly bucket of the RSVP timeline (Monday-anchored)."""

    week_start: date
    new: int  # first replies that landed that week
    cumulative: int  # running total of replies up to and including that week


class TimelineSummary(BaseModel):
    """Cumulative RSVP replies over time, for the admin Overview's Trends chart.
    Replies are counted by `responded_at` (the first reply), so edits don't inflate
    the curve. `total_invitations` is the ceiling line (all parties)."""

    total_invitations: int
    total_replied: int
    points: list[TimelinePoint] = []


# --- Wishes moderation (owner) --------------------------------------------
class WishAdmin(BaseModel):
    """A guestbook message as the owner sees it — incl. moderation state."""

    id: UUID
    name: str
    message: str
    approved: bool
    guest_name: str | None = None  # the invited guest who left it, if known
    created_at: datetime


class WishModerate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: bool


# --- Content / event details / theme (owner-editable) ----------------------
class ContentAdmin(BaseModel):
    """The whole editable surface of a wedding's invite (copy + details + theme)."""

    couple_names: str
    event_details: dict[str, Any]
    content: dict[str, Any]
    theme_tokens: dict[str, Any] | None = None


class ContentUpdate(BaseModel):
    """Partial update. `event_details`, `content` and `theme_tokens` are
    deep-merged onto the stored JSON (so the admin can PATCH a single section);
    `couple_names` is replaced. Omitted fields are untouched."""

    model_config = ConfigDict(extra="forbid")
    couple_names: str | None = Field(default=None, min_length=1, max_length=200)
    event_details: dict[str, Any] | None = None
    content: dict[str, Any] | None = None
    theme_tokens: dict[str, Any] | None = None

    _bounds = _bounded_json("event_details", "content", "theme_tokens")


# --- Story arcs (owner CRUD) ----------------------------------------------
class StoryArcAdmin(BaseModel):
    id: UUID
    title: str
    visible: bool
    sort_order: int
    content: dict[str, Any]


class StoryArcCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="Our story", min_length=1, max_length=200)
    visible: bool = True
    sort_order: int = 0
    content: dict[str, Any] = Field(default_factory=dict)

    _bounds = _bounded_json("content")


class StoryArcUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    visible: bool | None = None
    sort_order: int | None = None
    content: dict[str, Any] | None = None

    _bounds = _bounded_json("content")


class UploadResult(BaseModel):
    url: str


# --- Spreadsheet import (owner) -------------------------------------------
class ImportRowResult(BaseModel):
    """What happened to one invitee in an import (dry-run or committed)."""

    row: int  # 1-based spreadsheet row of the invitee's Primary line
    invitee: str
    action: str  # create | update | error
    detail: str | None = None  # error message(s), when action == "error"


class ImportResult(BaseModel):
    committed: bool  # False = dry-run preview, True = applied
    created: int  # invitees (parties) created
    updated: int  # invitees (parties) updated
    # Persons (each invitee + its companions) across the created/updated invitees, so
    # the preview can show guest-level totals alongside the invitee-level ones.
    people_created: int = 0
    people_updated: int = 0
    errors: int
    rows: list[ImportRowResult] = []


# =========================================================================
# Platform era (SAAS_PLAN Phases 1–5): accounts, weddings lifecycle, members,
# platform console, plans & entitlements.
# =========================================================================
_MEMBER_ROLE_PATTERN = "^(owner|admin)$"


# --- /api/me — the signed-in user's home ------------------------------------
class MeResponse(BaseModel):
    user_id: str
    email: str
    via: str
    display_name: str = ""
    is_platform_admin: bool = False


class MyWedding(BaseModel):
    """One row of the post-login dashboard: a wedding + the caller's role."""

    wedding_id: UUID
    slug: str
    couple_names: str
    role: str  # owner | admin
    status: str  # draft | pending_approval | active | suspended | archived
    published: bool
    guest_count: int = 0
    created_at: datetime | None = None


# --- Wedding creation (Phase 2 wizard) ---------------------------------------
class WeddingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    couple_names: str = Field(min_length=3, max_length=200)
    slug: str = Field(min_length=3, max_length=63)
    # Optional at creation; everything is editable later in the dashboard.
    venue: str | None = Field(default=None, max_length=200)
    date_iso: str | None = Field(default=None, max_length=10)  # YYYY-MM-DD
    date_display: str | None = Field(default=None, max_length=80)


class WeddingCreated(BaseModel):
    wedding_id: UUID
    slug: str
    couple_names: str
    status: str
    admin_path: str  # "/{slug}/admin"


class SlugCheck(BaseModel):
    slug: str
    available: bool
    reason: str | None = None  # why not, when unavailable
    suggestion: str | None = None


# --- Wedding lifecycle (approval + publication) ------------------------------
class LifecycleResult(BaseModel):
    wedding_id: UUID
    status: str
    published: bool
    # When a submission was auto-evaluated: which rules ran and what they said.
    auto_approved: bool | None = None
    rule_trace: list[RuleTraceEntry] = []


class RuleTraceEntry(BaseModel):
    rule: str
    ok: bool
    detail: str | None = None


class PublishUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    published: bool


class WeddingSettingsUpdate(BaseModel):
    """Owner-editable per-wedding admin settings (not guest content).

    PATCH semantics: omitted/null fields are untouched; an empty string CLEARS a
    string setting back to its default (the endpoint drops the key).
    """

    model_config = ConfigDict(extra="forbid")
    admins_can_publish: bool | None = None
    # ISO 3166-1 alpha-2 region for interpreting guests' national-format phone
    # numbers (e.g. "US", "GB"). Unset = platform default (validation.DEFAULT_REGION).
    phone_region: str | None = None
    # Last day (ISO YYYY-MM-DD, inclusive, UTC) guests may submit or edit RSVPs.
    # Unset = RSVPs stay open indefinitely. The invite page still renders after
    # the deadline — only the RSVP write closes.
    rsvp_deadline: str | None = None

    @field_validator("phone_region")
    @classmethod
    def _valid_region(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from app.validation import is_supported_region

        code = v.strip().upper()
        if not code:
            return ""  # clear
        if not is_supported_region(code):
            raise ValueError("phone_region must be a supported two-letter country code")
        return code

    @field_validator("rsvp_deadline")
    @classmethod
    def _valid_deadline(cls, v: str | None) -> str | None:
        if v is None:
            return v
        text = v.strip()
        if not text:
            return ""  # clear
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            raise ValueError("rsvp_deadline must be a date like 2027-06-01")


# --- Members (Phase 3 team management) ---------------------------------------
class MemberAdmin(BaseModel):
    id: UUID
    user_id: str | None = None
    email: str | None = None  # invited_email, or the member profile's email
    display_name: str = ""
    role: str  # owner | admin
    status: str  # invited | active | revoked
    invited_by: str | None = None
    created_at: datetime | None = None
    # For pending invites only: when the emailed token stops working.
    invite_expires_at: datetime | None = None


class MemberInviteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    role: str = Field(default="admin", pattern=_MEMBER_ROLE_PATTERN)


class MemberInvited(BaseModel):
    member: MemberAdmin
    # Single-use accept path (also emailed). Returned so the owner can copy the
    # link into any channel; it is useless to anyone but the invited email.
    accept_path: str


class MemberRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(pattern=_MEMBER_ROLE_PATTERN)


class InviteAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=16, max_length=128)


class InviteAccepted(BaseModel):
    wedding_id: UUID
    wedding_slug: str
    couple_names: str
    role: str


# --- Platform console (Phase 4) ----------------------------------------------
class PlatformWedding(BaseModel):
    id: UUID
    slug: str
    couple_names: str
    status: str
    published: bool
    owner_email: str | None = None
    member_count: int = 0
    guest_count: int = 0
    plan_name: str | None = None
    created_at: datetime | None = None


class ApprovalItem(BaseModel):
    """One pending wedding in the approval queue, with the auto-rule trace."""

    wedding: PlatformWedding
    rule_trace: list[RuleTraceEntry] = []
    would_auto_approve: bool = False


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=500)


class PlatformSettingsPayload(BaseModel):
    """The platform_settings 'approval' blob (rules editor). Whole-blob PUT."""

    model_config = ConfigDict(extra="forbid")
    auto_approve: bool = False
    require_verified_email: bool = True
    min_account_age_hours: int = Field(default=0, ge=0)
    max_weddings_per_account: int = Field(default=3, ge=1)
    max_guests_at_submission: int = Field(default=500, ge=0)
    banned_words: list[str] = []


class PlatformUser(BaseModel):
    user_id: str
    email: str
    display_name: str = ""
    disabled: bool = False
    is_platform_admin: bool = False
    wedding_count: int = 0
    created_at: datetime | None = None


class UserDisableUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disabled: bool


class PlatformStats(BaseModel):
    weddings_by_status: dict[str, int] = {}
    total_users: int = 0
    total_guests: int = 0
    rsvps_last_7_days: int = 0
    signups_last_7_days: int = 0


class AuditEntry(BaseModel):
    id: UUID
    wedding_id: UUID | None = None
    actor_email: str | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    detail: dict[str, Any] = {}
    created_at: datetime | None = None


# --- Plans & entitlements (Phase 5) -------------------------------------------
class PlanAdmin(BaseModel):
    id: UUID
    name: str
    description: str = ""
    is_default: bool = False
    entitlements: dict[str, Any] = {}
    archived: bool = False
    created_at: datetime | None = None


class PlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)
    is_default: bool = False
    entitlements: dict[str, Any] = Field(default_factory=dict)


class PlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    is_default: bool | None = None
    entitlements: dict[str, Any] | None = None
    archived: bool | None = None


class PlanAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: UUID | None = None  # None = back to the default plan
    overrides: dict[str, Any] | None = None  # None = keep current overrides
    valid_until: datetime | None = None


class WeddingPlanAdmin(BaseModel):
    wedding_id: UUID
    plan: PlanAdmin | None = None
    overrides: dict[str, Any] = {}
    effective: dict[str, Any] = {}
    valid_until: datetime | None = None
