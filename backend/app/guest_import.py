"""Pure logic for importing the planning spreadsheet into guest rows.

The planning sheet models every +1 and child as its OWN row ("Riley +1",
"Kid 2 (Casey)"). The app wants ONE guest per primary person, with an
`invite_tier` that allows the right number of companions — the guest fills in
companion names at RSVP time. So we collapse placeholder rows into the primary
guest's tier instead of creating junk guests/links.

These functions are deterministic and unit-tested (tests/test_guest_import.py);
the DB-touching part lives in scripts/import_guests.py.
"""
from __future__ import annotations

import re
import secrets
import unicodedata
from dataclasses import dataclass, field

from app.models import InviteTier

# "Riley +1", "Mehmood + 2"  → base name + companion number
_PLUS_RE = re.compile(r"^(?P<base>.+?)\s*\+\s*(?P<n>\d+)\s*$")
# "(Casey)" parent hint inside a kid row name
_PAREN_RE = re.compile(r"\(([^)]+)\)")
_KID_NAME_RE = re.compile(r"^\s*kid\b", re.IGNORECASE)


def slugify(name: str) -> str:
    """ASCII, lowercase, hyphenated. Strips '+N' and parentheticals."""
    name = _PLUS_RE.sub(lambda m: m.group("base"), name)
    name = _PAREN_RE.sub("", name)
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return name or "guest"


def make_guest_slug(name: str = "") -> str:
    """Globally-unique, unguessable per-guest link slug. A bare random token — the
    name is deliberately NOT included so the link reveals nothing about the guest
    (e.g. `/i/Xa3kQ7p2...`). `name` is accepted for call-site compatibility, ignored.

    The slug IS the guest's only credential (resolves the tenant + guest and gates
    their PII/RSVP), so it must be infeasible to enumerate: 16 random bytes = 128
    bits, URL-safe base64 (~22 chars of [A-Za-z0-9_-]). _unique_slug retries on the
    (astronomically rare) collision."""
    return secrets.token_urlsafe(16)


def normalize_key(name: str) -> str:
    """Match key for grouping companions to their primary (case/space-insensitive)."""
    base = _PLUS_RE.sub(lambda m: m.group("base"), name)
    base = _PAREN_RE.sub("", base)
    return re.sub(r"\s+", " ", base).strip().lower()


@dataclass
class RowClass:
    kind: str  # "primary" | "adult" | "child"
    base_key: str | None  # normalize_key of the primary this attaches to (for adult/child)


def classify_row(name: str, relationship: str | None) -> RowClass:
    """Decide whether a row is a primary guest or a companion placeholder."""
    rel = (relationship or "").strip().lower()
    if _PLUS_RE.match(name):
        return RowClass("adult", normalize_key(name))
    if rel == "kid" or _KID_NAME_RE.match(name):
        # Prefer an explicit "(Parent)" hint; otherwise unresolved (base_key=None).
        m = _PAREN_RE.search(name)
        parent = normalize_key(m.group(1)) if m else None
        return RowClass("child", parent)
    return RowClass("primary", None)


def infer_tier(adult_companions: int, child_companions: int) -> InviteTier:
    """Tier from how many companions the planning sheet attached to a guest."""
    if child_companions > 0 or adult_companions >= 2:
        return InviteTier.plus_family
    if adult_companions == 1:
        return InviteTier.plus_one
    return InviteTier.solo


@dataclass
class GuestDraft:
    name: str
    side: str | None = None
    relationship: str | None = None
    group_name: str | None = None
    batch: str | None = None
    invited: bool = True
    adult_companions: int = 0
    child_companions: int = 0
    seed_meta: dict = field(default_factory=dict)

    @property
    def invite_tier(self) -> InviteTier:
        return infer_tier(self.adult_companions, self.child_companions)


def build_guests(rows: list[dict]) -> tuple[list[GuestDraft], list[dict]]:
    """Collapse raw rows → primary GuestDrafts (+ tiers) and a list of unresolved
    companion placeholders that couldn't be matched to a primary.

    `rows` are dicts with keys: name, side, relationship, group_name, batch,
    invited (bool), prob_tier, prob_pct.
    """
    primaries: dict[str, GuestDraft] = {}
    order: list[str] = []
    pending_companions: list[tuple[str, RowClass, dict]] = []  # (name, class, row)

    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        cls = classify_row(name, row.get("relationship"))
        if cls.kind == "primary":
            key = normalize_key(name)
            if key not in primaries:
                primaries[key] = GuestDraft(
                    name=name,
                    side=row.get("side"),
                    relationship=row.get("relationship"),
                    group_name=row.get("group_name"),
                    batch=row.get("batch"),
                    invited=row.get("invited", True),
                    seed_meta={
                        "prob_tier": row.get("prob_tier"),
                        "prob_pct": row.get("prob_pct"),
                    },
                )
                order.append(key)
        else:
            pending_companions.append((name, cls, row))

    unresolved: list[dict] = []
    for name, cls, row in pending_companions:
        target = primaries.get(cls.base_key) if cls.base_key else None
        if target is None:
            unresolved.append({"name": name, "kind": cls.kind, "row": row})
            continue
        if cls.kind == "adult":
            target.adult_companions += 1
        else:
            target.child_companions += 1

    return [primaries[k] for k in order], unresolved
