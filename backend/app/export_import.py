"""Pure logic for the guest XLSX round-trip — the canonical **split-row** schema
(one row per person) shared by export, the fillable template, and import.

Design (locked with RT 2026-06-10/-11/-14):
- Each invitee AND each companion is its own row. The first row of a party is the
  **Primary** (the invited guest); the rows under it (`Guest` / `Child`) are their
  companions (`Adult` is still accepted on import for older sheets). A companion
  attaches to the Primary that SHARES its `Id` (so a party
  can be reordered as a block), or — if it has no `Id` — to the nearest Primary above
  it (positional, for hand-built sheets). There is no `Invitee` column.
- A stable **`Id`** column (the invite's Guest UUID) is the upsert key: a Primary row
  whose `Id` resolves to an existing guest updates it; a **blank `Id` creates a new
  guest** (we mint the id + slug). An `Id` that doesn't resolve is an error (typo /
  wrong wedding). The `Id` is copied onto EVERY row of the party (companions too) so
  it's obvious which invite each person belongs to; companion `Id`s are read only for
  grouping, never as their own key (companions are not separate guests — editing a
  companion row and re-importing updates it via the party's shared `Id`). The `Link`
  column is exported for convenience (clickable) but is **display-only**, never matched,
  and stays Primary-only.
- Guest-level fields (Id/Greeting/Email/Phone/Tier/Side/…/Attending/Notes + invitee-
  scope question answers) live on the Primary row but are **copied down** onto every
  companion row so each person row is self-contained (`Link` excepted). `Name` is
  per-person. `Greeting` (the mandatory "Dear …" label) is copied down for readability
  but read from the Primary row only on import. `Expected`/`Actual` are Primary-only.
- Dietary/age and any other admin-defined questions are ordinary columns, round-
  tripped both ways. A **person**-scope question shows each person's OWN answer on
  their row; an **invitee**-scope question's answer is copied down to the party.
- Columns with a fixed list of values (Person/Tier/Invited/Attending + single-
  choice / yes-no questions) get a strict Excel dropdown; multi-select questions
  (e.g. dietary) get the list as a non-strict hint so "Halal, Vegan" still works.
  See `list_columns()`.

This module is DB-free and unit-tested. The router (app/routers/admin.py) does the
DB work: id→guest resolution, contact normalization, tier-cap enforcement, answer
typing/validation, and persistence — feeding off the `ParsedGuest` intents here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Guest-level columns (Primary row only), in order. Custom-question prompts are
# appended after these at runtime (one column per question). `Id` is the upsert key.
BASE_COLUMNS = [
    "Id",  # the invite's key (a Guest UUID). Copied onto EVERY row of the party so it's
    # clear which invite each person belongs to and so an edited row updates the right one.
    "Link",
    "Person",
    "Name",
    "Greeting",  # the invite's mandatory "Dear …" label; shown on every row for readability
    "Email",
    "Phone",
    "Tier",
    "Side",
    "Relationship",
    "Group",
    "Batch",
    "Expected",  # owner's pre-RSVP headcount estimate (Primary row only); admin-only
    "Actual",  # computed party size from RSVPs (Primary row only); export-only, ignored on import
    "Invited",  # is on the guest list (guest.invited)
    "Invite Sent",  # has the owner sent the invite (drives the "Invited" status)
    "Attending",
    "Notes",
]

# Invitee-level columns copied DOWN onto each companion row so every person row is
# self-contained. `Id` + `Greeting` are copied too: the Id ties the whole party to one
# invite (its upsert key) and the Greeting labels it. `Link` stays Primary-only.
_INVITEE_COPY = [
    "Id",
    "Greeting",
    "Email",
    "Phone",
    "Tier",
    "Side",
    "Relationship",
    "Group",
    "Batch",
    "Invited",
    "Invite Sent",
    "Attending",
    "Notes",
]

_TIER_ALIASES = {
    "solo": "solo",
    "plus_one": "plus_one",
    "+1": "plus_one",
    "plus one": "plus_one",
    "plusone": "plus_one",
    "plus_family": "plus_family",
    "+family": "plus_family",
    "family": "plus_family",
    "plus family": "plus_family",
}
_YES = {"yes", "y", "true", "1", "attending", "going"}
_NO = {"no", "n", "false", "0", "declined", "regrets"}


# Spreadsheet (CSV/formula) injection: when a guest-supplied value (name, notes,
# free-text answer) starts with one of these, Excel/Sheets may interpret the cell as
# a formula when the owner opens the exported workbook. Prefix a single quote so it's
# always treated as text. Applied to every cell written on export (see admin._xlsx).
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def escape_formula(value):
    """Neutralize spreadsheet formula injection. A string cell beginning with a
    formula trigger (`= + - @` or a leading tab/CR) gets a leading `'` so Excel/Sheets
    renders it as literal text; everything else (incl. non-strings) passes through."""
    if isinstance(value, str) and value[:1] in _FORMULA_TRIGGERS:
        return "'" + value
    return value


def _answer_text(value: dict) -> str:
    """Flatten a stored answer to a cell string. Handles every question type:
    {text} / {number} / {choice} / {choices:[...]} / {yesno}."""
    if not isinstance(value, dict):
        return ""
    if isinstance(value.get("text"), str):
        return value["text"]
    if value.get("number") is not None:
        return str(value["number"])
    if isinstance(value.get("choice"), str):
        return value["choice"]
    if isinstance(value.get("choices"), list):
        return ", ".join(str(x) for x in value["choices"])
    if isinstance(value.get("yesno"), bool):
        return "Yes" if value["yesno"] else "No"
    return ""


def columns(question_prompts: list[str]) -> list[str]:
    """Full ordered header = base columns + one column per custom question."""
    return [*BASE_COLUMNS, *question_prompts]


def _scope_of(q) -> str:
    """`question.scope` as a plain string, tolerating an enum or a bare str (so the
    pure functions can be unit-tested with lightweight stand-ins)."""
    s = getattr(q, "scope", "invitee")
    return getattr(s, "value", s)


def _qtype_of(q) -> str:
    t = getattr(q, "qtype", "text")
    return getattr(t, "value", t)


@dataclass
class ListSpec:
    """A column's allowed values for an Excel dropdown. `strict=False` shows the
    list but still permits other input (used for multi-select columns)."""

    values: list[str]
    strict: bool


def list_columns(questions: list) -> dict[str, ListSpec]:
    """Which columns get a dropdown, and from what list. Built-ins are strict;
    among admin-defined questions, single-choice / yes-no are strict and
    multi-select is non-strict (so comma-separated multi values are still allowed)."""
    out: dict[str, ListSpec] = {
        "Person": ListSpec(["Primary", "Guest", "Child"], True),
        "Tier": ListSpec(["solo", "plus_one", "plus_family"], True),
        "Invited": ListSpec(["yes", "no"], True),
        "Invite Sent": ListSpec(["yes", "no"], True),
        "Attending": ListSpec(["yes", "no"], True),
    }
    for q in questions:
        t = _qtype_of(q)
        if t == "yesno":
            out[q.prompt] = ListSpec(["Yes", "No"], True)
        elif t == "choice":
            out[q.prompt] = ListSpec([str(o) for o in (q.options or [])], True)
        elif t == "multi_choice":
            out[q.prompt] = ListSpec([str(o) for o in (q.options or [])], False)
    return out


def build_rows(guests: list, questions: list) -> list[dict]:
    """Serialize guests (with their RSVP rollup) to split-row dicts keyed by the
    header in `columns()`. `guests` are ORM Guest objects; `questions` are the
    wedding's questions in column order (each exposes `id`, `prompt`, `scope`).

    The Primary row carries the guest + RSVP-level fields and the party's answers
    (invitee-scope + the primary's own person-scope answers). Each companion gets
    its own row: the invitee-level fields are copied DOWN (so the row stands alone),
    a **person**-scope question shows that companion's OWN answer, and an
    **invitee**-scope question's answer is copied down too.
    """
    out: list[dict] = []
    for g in guests:
        rsvp = g.rsvp
        attending = "" if rsvp is None else ("yes" if rsvp.attending else "no")
        # Actual head count for this party: 0 unless they've RSVP'd attending.
        party = 1 + len(rsvp.companions) if rsvp is not None and rsvp.attending else 0
        # Party answers (companion_id None) keyed by question id = invitee-scope +
        # the primary person's own person-scope answers.
        party_by_qid: dict = {}
        if rsvp is not None:
            for a in rsvp.answers:
                if a.companion_id is None:
                    party_by_qid[a.question_id] = _answer_text(a.value)
        primary = {
            "Id": str(g.id),
            "Link": f"/i/{g.slug}",
            "Person": "Primary",
            "Name": g.name,
            "Greeting": g.greeting_name or "",
            "Email": g.email or "",
            "Phone": g.phone or "",
            "Tier": g.invite_tier.value,
            "Side": g.side or "",
            "Relationship": g.relationship_label or "",
            "Group": g.group_name or "",
            "Batch": g.batch or "",
            "Expected": "" if g.expected_party_size is None else str(g.expected_party_size),
            "Actual": str(party),
            "Invited": "yes" if g.invited else "no",
            "Invite Sent": "yes" if g.invite_sent else "no",
            "Attending": attending,
            "Notes": (rsvp.notes if rsvp else "") or "",
        }
        for q in questions:
            primary[q.prompt] = party_by_qid.get(q.id, "")
        out.append(primary)

        # Companion rows come from the RESPONDED party (RSVP companions) when the guest
        # has replied, else the admin's PREFILL party (party_members) so a round-trip
        # preserves seeded names. Prefill rows carry no per-person answers.
        if rsvp is not None and rsvp.companions:
            members = [
                (
                    "Child" if c.kind.value == "child" else "Guest",
                    c.name or "",
                    {a.question_id: _answer_text(a.value) for a in c.answers},
                )
                for c in rsvp.companions
            ]
        else:
            members = [
                ("Child" if (m or {}).get("kind") == "child" else "Guest", (m or {}).get("name") or "", {})
                for m in (g.party_members or [])
            ]
        for person_label, member_name, own_by_qid in members:
            row = {col: "" for col in BASE_COLUMNS}
            row["Person"] = person_label
            row["Name"] = member_name
            # Invitee-level fields (incl. Id + Greeting) copy down so the companion row
            # is self-contained and clearly tied to its invite.
            for col in _INVITEE_COPY:
                row[col] = primary[col]
            for q in questions:
                if _scope_of(q) == "invitee":
                    row[q.prompt] = primary[q.prompt]  # party value, copied down
                else:
                    row[q.prompt] = own_by_qid.get(q.id, "")  # this person's own
            out.append(row)
    return out


def template_rows() -> list[dict]:
    """A couple of illustrative rows for the blank template (headers + examples)."""
    ex_primary = {col: "" for col in BASE_COLUMNS}
    ex_primary.update(
        {
            "Person": "Primary",
            "Name": "Hasaan Ali",
            "Greeting": "Hasaan & May",
            "Email": "hasaan@example.com",
            "Phone": "+65 9123 4567",
            "Tier": "plus_family",
            "Side": "Alex",
            "Invited": "yes",
            "Attending": "yes",
        }
    )
    ex_adult = {col: "" for col in BASE_COLUMNS}
    ex_adult.update({"Person": "Guest", "Name": "May Tan"})
    ex_child = {col: "" for col in BASE_COLUMNS}
    ex_child.update({"Person": "Child", "Name": "Leo"})
    return [ex_primary, ex_adult, ex_child]


# --- Parsing (import) ------------------------------------------------------
# Header keys that are NOT admin-defined question columns.
_BASE_SET = {*BASE_COLUMNS, "__row__"}


@dataclass
class ParsedCompanion:
    kind: str  # adult | child
    name: str | None
    # Raw answer cells for this person, keyed by question prompt (header). The
    # router types/validates them against the wedding's questions.
    answers: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedGuest:
    source_row: int  # 1-based spreadsheet row of the Primary (for error messages)
    guest_id: str | None  # the `Id` cell (UUID) — the upsert key; blank = create
    link_slug: str | None  # parsed from Link, kept for reference only (not a key)
    name: str
    greeting_name: str | None
    email: str
    phone: str
    tier: str | None
    side: str | None
    relationship: str | None
    group_name: str | None
    batch: str | None
    expected_party_size: int | None
    invited: bool
    # None = leave unchanged (blank cell never wipes); True/False = the owner set it.
    invite_sent: bool | None
    attending: bool | None
    notes: str | None
    # Raw party answer cells (invitee-scope + the primary's own), by question prompt.
    answers: dict[str, str] = field(default_factory=dict)
    companions: list[ParsedCompanion] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _norm(v) -> str:
    return str(v).strip() if v is not None else ""


def _slug_from_link(link: str) -> str | None:
    """Extract the guest slug from a Link cell ('/i/{slug}' or a full URL)."""
    link = _norm(link)
    if not link:
        return None
    m = re.search(r"/i/([^/\s?#]+)", link)
    return m.group(1) if m else (link or None)


def _match_option(raw: str, options: list[str]) -> str | None:
    """Case-insensitively map a cell to one of the allowed options (returns the
    canonical option text). With no options defined, accept the raw value."""
    if not options:
        return raw
    for o in options:
        if str(o).lower() == raw.lower():
            return str(o)
    return None


def typed_answer(qtype: str, options: list[str], raw: str) -> tuple[dict | None, str | None]:
    """Convert a raw cell into a typed answer value for `qtype`, or report why not.
    Returns `(value, None)`, `(None, None)` for a blank cell, or `(None, error)`."""
    raw = _norm(raw)
    if raw == "":
        return None, None
    if qtype == "text":
        return {"text": raw}, None
    if qtype == "number":
        if not re.fullmatch(r"-?\d+", raw):
            return None, f"'{raw}' is not a whole number"
        return {"number": int(raw)}, None
    if qtype == "yesno":
        low = raw.lower()
        if low in _YES:
            return {"yesno": True}, None
        if low in _NO:
            return {"yesno": False}, None
        return None, f"'{raw}' is not yes/no"
    if qtype == "choice":
        match = _match_option(raw, [str(o) for o in (options or [])])
        if match is None:
            return None, f"'{raw}' is not an allowed option"
        return {"choice": match}, None
    if qtype == "multi_choice":
        opts = [str(o) for o in (options or [])]
        chosen: list[str] = []
        for part in (p.strip() for p in raw.split(",") if p.strip()):
            match = _match_option(part, opts)
            if match is None:
                return None, f"'{part}' is not an allowed option"
            chosen.append(match)
        return ({"choices": chosen} if chosen else None), None
    return None, f"unsupported question type '{qtype}'"


def _parse_invited(v) -> bool:
    t = _norm(v).lower()
    return t not in _NO  # default invited=yes unless explicitly no/false/0


def _parse_invite_sent(v) -> bool | None:
    t = _norm(v).lower()
    if t in _YES:
        return True
    if t in _NO:
        return False
    return None  # blank → leave the flag unchanged (never wipes)


def _parse_attending(v) -> bool | None:
    t = _norm(v).lower()
    if t in _YES:
        return True
    if t in _NO:
        return False
    return None  # blank / "pending" → don't touch the RSVP


def _parse_expected(raw: str) -> tuple[int | None, str | None]:
    """Owner's pre-RSVP headcount estimate. Returns `(value, None)`, `(None, None)`
    for a blank cell (leave unchanged), or `(None, error)`. Bounds match the API
    schema (0–50)."""
    if raw == "":
        return None, None
    if not re.fullmatch(r"\d+", raw) or not (0 <= int(raw) <= 50):
        return None, f"expected party size '{raw}' must be a whole number 0–50"
    return int(raw), None


def _answer_cells(rec: dict) -> dict[str, str]:
    """Non-empty admin-defined question cells in a row, keyed by question prompt."""
    return {
        k: _norm(v)
        for k, v in rec.items()
        if k not in _BASE_SET and _norm(v) != ""
    }


def parse_records(records: list[dict]) -> list[ParsedGuest]:
    """Group split-rows into per-invitee `ParsedGuest` intents with structural
    validation. `records` are dicts keyed by the header; admin-defined question
    columns are collected as raw `answers` (the router types + validates them).

    Each record carries a 1-based `__row__` for error messages (the caller sets it).
    Returns intents in input order; `errors` on an intent mean "skip on commit".
    """
    out: list[ParsedGuest] = []
    current: ParsedGuest | None = None
    by_id: dict[str, ParsedGuest] = {}  # primaries that carry an Id, for Id-aware grouping

    for rec in records:
        row_no = int(rec.get("__row__", 0) or 0)
        person = _norm(rec.get("Person")).lower()
        cell_name = _norm(rec.get("Name"))
        row_id = _norm(rec.get("Id"))

        if person in ("adult", "guest", "child"):
            # "Guest" is the current label for an adult companion row; "Adult" is still
            # accepted for older sheets. Both map to the structural kind "adult".
            kind = "child" if person == "child" else "adult"
            # Attach to the Primary that SHARES this row's Id (robust to reordering —
            # the export copies the invite's Id onto every party row), else to the most
            # recent Primary above it (positional fallback for hand-built sheets).
            target = (by_id.get(row_id) if row_id else None) or current
            if target is None:
                # Orphan companion with no preceding primary — record on a stub.
                stub = _blank_guest(row_no, cell_name or "(unknown)")
                stub.errors.append(f"Row {row_no}: companion '{cell_name}' has no invitee above it")
                out.append(stub)
                continue
            target.companions.append(
                ParsedCompanion(kind=kind, name=cell_name or None, answers=_answer_cells(rec))
            )
            continue

        # Otherwise this is a Primary row (Person == "primary" or blank) → new guest.
        greeting = _norm(rec.get("Greeting"))
        guest_id = row_id
        tier_raw = _norm(rec.get("Tier")).lower()
        # The primary's Name is OPTIONAL now; a row counts as a primary if it carries
        # any identifying content. A wholly blank row is ignored.
        if not (cell_name or greeting or guest_id or tier_raw):
            continue
        tier = _TIER_ALIASES.get(tier_raw) if tier_raw else None
        expected_raw = _norm(rec.get("Expected"))
        expected, expected_err = _parse_expected(expected_raw)
        current = ParsedGuest(
            source_row=row_no,
            guest_id=guest_id or None,
            link_slug=_slug_from_link(rec.get("Link")),
            name=cell_name,  # optional — no fallback to the Invitee label
            greeting_name=greeting or None,
            email=_norm(rec.get("Email")),
            phone=_norm(rec.get("Phone")),
            tier=tier,
            side=_norm(rec.get("Side")) or None,
            relationship=_norm(rec.get("Relationship")) or None,
            group_name=_norm(rec.get("Group")) or None,
            batch=_norm(rec.get("Batch")) or None,
            expected_party_size=expected,
            invited=_parse_invited(rec.get("Invited")),
            invite_sent=_parse_invite_sent(rec.get("Invite Sent")),
            attending=_parse_attending(rec.get("Attending")),
            notes=_norm(rec.get("Notes")) or None,
            answers=_answer_cells(rec),
        )
        # Greeting is the invite's mandatory label — a Primary row without it is an error.
        if not greeting:
            current.errors.append(f"Row {row_no}: Greeting is required")
        if tier_raw and tier is None:
            current.errors.append(f"Row {row_no}: unknown tier '{tier_raw}'")
        if expected_err:
            current.errors.append(f"Row {row_no}: {expected_err}")
        if guest_id:
            by_id[guest_id] = current  # so companion rows can attach by shared Id
        out.append(current)

    return out


def _blank_guest(row_no: int, name: str) -> ParsedGuest:
    return ParsedGuest(
        source_row=row_no, guest_id=None, link_slug=None, name=name, greeting_name=None,
        email="", phone="",
        tier=None, side=None, relationship=None, group_name=None, batch=None,
        expected_party_size=None, invited=True, invite_sent=None, attending=None, notes=None,
    )
