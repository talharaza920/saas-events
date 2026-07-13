"""Apply an AI proposal to the wedding — the "code disposes" half of the rule
(AI_WIZARD_PLAN 8.3 §2).

`apply` is a diff, transactional, and human-gated. It writes ONLY the
allowlisted sections below and nothing else — never `slug`, `status`,
`published`, `invite_tier`, membership, plan, or theme. A proposal is stored
JSON and might have sat in review while things changed, so everything is
re-checked at apply time: entitlements (`max_story_arcs`), the platform
banned-word scan (SAAS_PLAN 2.2), schema shape (the draft re-validates through
DraftArc), and the glyph goes through the allowlist-rebuild sanitiser again.
The audit trail records `source: "ai"`, and every row this creates is stamped
`ai_generated: true`.

The allowlist — adding a path means adding a writer function here:

  couple_names   → weddings.couple_names + content.nav.brand
                   + content.brand.wordmark_text (mirrors wedding_factory)
  event_details  → event_details.{venue, address, map_url,
                   date_display, time_display} — display strings only;
                   nothing here parses or invents an ISO date
  story_arc      → ONE new story_arcs row
  glyph          → content.brand.icon_svg (sanitised form only; icon_mode is
                   left alone — switching the cover to the SVG is the owner's
                   call in the 8.4 UI)

  guests         → new `guests` rows: names only, tier RECOMPUTED here by the
                   deterministic guest_import.infer_tier() (never read from
                   the proposal, never from the model), `story_arc_ids` never
                   AI-populated (that's how tier stays unleakable)
"""
from __future__ import annotations

import copy
import json

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.images import CLIMAX_TARGET
from app.ai.jobs import sweep_generated_images
from app.ai.schemas import DraftArc
from app.ai.svg import SvgSanitizationError, sanitize_glyph
from app.approval import get_approval_rules
from app.audit_log import record
from app.config import Settings
from app.entitlements import check_limit
from app.guest_import import infer_tier, make_guest_slug
from app.models import AiInput, AiJob, AiJobStatus, Guest, StoryArc, Wedding
from app.storage import delete_media_object

# Order is apply order (names/details before the arc that may mention them).
APPLY_SECTIONS = ("couple_names", "event_details", "story_arc", "glyph", "guests")

# What each job KIND may legitimately write. A section a kind's pipeline never
# produces is unreachable even if a stored proposal grows the key — a wizard
# proposal smuggling a "guests" list writes no guests.
SECTIONS_BY_KIND: dict[str, tuple[str, ...]] = {
    "details": ("couple_names", "event_details"),
    "story_arc": ("story_arc",),
    "glyph": ("glyph",),
    "guests": ("guests",),
}


def apply_proposal(
    db: Session,
    settings: Settings,
    wedding: Wedding,
    job: AiJob,
    *,
    selections: list | None = None,
    user=None,
) -> dict:
    """Apply the selected proposal sections. Raises 404 (wrong tenant — the
    router's require_wedding already scopes, this is the belt), 409 (job not
    awaiting review), 403 (entitlement re-check), 422 (unknown selection,
    malformed section, banned words, unusable glyph). Commits on success."""
    if job.wedding_id != wedding.id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != AiJobStatus.AWAITING_REVIEW:
        raise HTTPException(status_code=409, detail=f"Job is {job.status}")

    proposal = job.proposal or {}
    requested = list(selections) if selections is not None else list(APPLY_SECTIONS)
    unknown = [s for s in requested if s not in APPLY_SECTIONS]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown apply selection(s): {', '.join(repr(s) for s in unknown)}",
        )
    allowed_for_kind = SECTIONS_BY_KIND.get(job.kind, ())
    wanted = [
        s for s in APPLY_SECTIONS
        if s in requested and s in allowed_for_kind and proposal.get(s) is not None
    ]
    if not wanted:
        raise HTTPException(status_code=422, detail="Nothing in this proposal matches the selection")

    _check_banned_words(db, proposal, wanted)

    # Deep-copy so nested writers can mutate freely; reassigned at the end
    # (JSON columns don't track in-place mutation).
    content = copy.deepcopy(wedding.content or {})
    applied: list[str] = []
    for section in wanted:
        wrote = {
            "couple_names": lambda: _apply_couple_names(wedding, content, proposal),
            "event_details": lambda: _apply_event_details(wedding, proposal),
            "story_arc": lambda: _apply_story_arc(db, settings, wedding, proposal),
            "glyph": lambda: _apply_glyph(content, proposal),
            "guests": lambda: _apply_guests(db, wedding, proposal),
        }[section]()
        if wrote:
            applied.append(section)
    if not applied:
        raise HTTPException(status_code=422, detail="Nothing in this proposal matches the selection")

    wedding.content = content
    job.status = AiJobStatus.APPLIED
    # APPLIED is terminal too: raw submissions (voice notes, PDFs — PII) go
    # now, and generated beat images the applied arc didn't keep are freed.
    for inp in db.execute(select(AiInput).where(AiInput.job_id == job.id)).scalars():
        if inp.storage_url:
            delete_media_object(settings, inp.storage_url)
        db.delete(inp)
    kept = set(_applied_image_urls(settings, proposal)) if "story_arc" in applied else set()
    sweep_generated_images(db, settings, job, keep=kept)
    record(
        db, "ai.job.apply", user=user, wedding=wedding,
        target_type="ai_job", target_id=job.id,
        detail={"source": "ai", "kind": job.kind, "applied": applied},
    )
    db.commit()
    return {"applied": applied, "job_id": str(job.id)}


def _check_banned_words(db: Session, proposal: dict, wanted: list) -> None:
    """The existing platform banned-word scan, run over exactly the sections
    being applied (deterministic output validation, plan 8.3 §8)."""
    banned = get_approval_rules(db).get("banned_words") or []
    if not banned:
        return
    hay = " ".join(
        json.dumps(proposal.get(s) or {}, ensure_ascii=False) for s in wanted
    ).lower()
    hits = [w for w in banned if w and w.lower() in hay]
    if hits:
        raise HTTPException(
            status_code=422,
            detail="The generated content contains words this platform doesn't allow — "
            "regenerate it before applying",
        )


# ---------------------------------------------------------------------------
# Section writers — each returns True iff it wrote something.
# ---------------------------------------------------------------------------
def _apply_couple_names(wedding: Wedding, content: dict, proposal: dict) -> bool:
    value = proposal.get("couple_names")
    if not isinstance(value, str) or not value.strip():
        return False
    value = value.strip()[:200]
    wedding.couple_names = value
    # The same three places wedding_factory personalises on creation.
    content.setdefault("nav", {})["brand"] = value
    content.setdefault("brand", {})["wordmark_text"] = value
    return True


# proposal venue dict (ResolvedVenue.as_dict or the bare-name fallback)
# → event_details keys. lat/lng are deliberately not stored — the template
# has no key for them and nothing renders them.
_VENUE_KEY_MAP = (("name", "venue"), ("address", "address"), ("maps_url", "map_url"))


def _apply_event_details(wedding: Wedding, proposal: dict) -> bool:
    src = proposal.get("event_details") or {}
    if not isinstance(src, dict):
        return False
    details = dict(wedding.event_details or {})
    changed = False
    # Extracted date/time are the couple's own display words ("May 1st, 2027"),
    # never parsed into date_iso — the owner confirms real dates in the admin.
    for fact_key, target in (("date", "date_display"), ("time", "time_display")):
        fact = src.get(fact_key)
        value = fact.get("value") if isinstance(fact, dict) else None
        if isinstance(value, str) and value.strip():
            details[target] = value.strip()[:200]
            changed = True
    venue = src.get("venue")
    if isinstance(venue, dict):
        for src_key, target in _VENUE_KEY_MAP:
            value = venue.get(src_key)
            if isinstance(value, str) and value.strip():
                details[target] = value.strip()[:500]
                changed = True
    if changed:
        wedding.event_details = details  # reassign: JSON column
    return changed


def _applied_image_urls(settings: Settings, proposal: dict) -> list[str]:
    """Exactly the panel-image URLs the story_arc writer wrote (same
    validation), so the post-apply sweep keeps those and only those."""
    arc = proposal.get("story_arc") or {}
    beats = arc.get("beats") if isinstance(arc, dict) else None
    count = len(beats) if isinstance(beats, list) else 0
    keys = [str(i) for i in range(count)] + [CLIMAX_TARGET]
    urls = (_beat_image(settings, proposal, k) for k in keys)
    return [u for u in urls if u]


def _beat_image(settings: Settings, proposal: dict, key: str) -> str | None:
    """The proposal's image URL for panel `key` ("0".."7" or "climax"), or
    None. Defence in depth on stored JSON: only a URL our own storage minted
    (local /media mount or the Supabase public bucket) is ever written where a
    page will render it."""
    images = proposal.get("beat_images")
    url = images.get(key) if isinstance(images, dict) else None
    if not isinstance(url, str) or not url.strip() or len(url) > 500:
        return None
    url = url.strip()
    allowed = [f"{settings.media_base_url.rstrip('/')}/media/"]
    if settings.supabase_url:
        allowed.append(
            f"{settings.supabase_url.rstrip('/')}/storage/v1/object/public/"
            f"{settings.supabase_storage_bucket}/"
        )
    return url if any(url.startswith(p) for p in allowed) else None


def _apply_story_arc(db: Session, settings: Settings, wedding: Wedding, proposal: dict) -> bool:
    try:
        draft = DraftArc.model_validate(proposal.get("story_arc"))
    except ValidationError:
        raise HTTPException(
            status_code=422, detail="The story draft in this proposal is malformed — regenerate it"
        )
    # Re-check at apply time: the plan may have changed while this sat in review.
    check_limit(
        db, wedding, "max_story_arcs",
        current_count=len(wedding.story_arcs), adding=1,
    )
    beats = []
    for i, beat in enumerate(draft.beats):
        entry: dict = {"text": beat.text}
        image = _beat_image(settings, proposal, str(i))
        if image:  # beats without art render as feathered text panels
            entry["image"] = image
        beats.append(entry)
    climax: dict | None = None
    if draft.climax:
        climax = {"text": draft.climax}
        climax_image = _beat_image(settings, proposal, CLIMAX_TARGET)
        if climax_image:
            climax["image"] = climax_image
    arc_content = {
        "kicker": draft.kicker,
        "heading": draft.heading,
        "intro": draft.intro,
        "beats": beats,
        "climax": climax,
        "ai_generated": True,  # provenance, stamped on every row apply creates
    }
    db.add(
        StoryArc(
            wedding_id=wedding.id,
            title=draft.heading[:200],
            visible=True,
            sort_order=max((a.sort_order for a in wedding.story_arcs), default=-1) + 1,
            content=arc_content,
        )
    )
    return True


def _clamped_int(value, *, lo: int = 0, hi: int = 10) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return lo
    return min(max(value, lo), hi)


def _unique_guest_slug(db: Session) -> str:
    """A fresh 128-bit slug (the guest's only credential); the collision retry
    is for form, not expectation."""
    while True:
        slug = make_guest_slug()
        if db.execute(select(Guest.id).where(Guest.slug == slug)).first() is None:
            return slug


def _apply_guests(db: Session, wedding: Wedding, proposal: dict) -> bool:
    """Create shell guest rows from the proposal. The tier is RECOMPUTED here
    from the bounded companion counts via the same deterministic infer_tier()
    the spreadsheet import uses — a tampered `invite_tier` string in stored
    proposal JSON is ignored by construction. `story_arc_ids` stays NULL
    (default visibility); AI never targets arcs at guests."""
    entries = proposal.get("guests")
    if not isinstance(entries, list) or not entries:
        return False
    if len(entries) > 300:
        raise HTTPException(
            status_code=422, detail="This guest proposal is malformed — regenerate it"
        )
    drafts: list[tuple[str, int, int]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        drafts.append(
            (
                name.strip()[:120],
                _clamped_int(entry.get("adult_companions")),
                _clamped_int(entry.get("child_companions")),
            )
        )
    if not drafts:
        return False
    # Re-check at apply time, like max_story_arcs above.
    check_limit(
        db, wedding, "max_guests",
        current_count=len(wedding.guests), adding=len(drafts),
    )
    for name, adults, kids in drafts:
        db.add(
            Guest(
                wedding_id=wedding.id,
                slug=_unique_guest_slug(db),
                name=name,
                greeting_name=name,
                invite_tier=infer_tier(adults, kids),  # code, never the proposal
                expected_party_size=1 + adults + kids,
                invited=True,
                seed_meta={"ai_generated": True},  # provenance on every row
            )
        )
    return True


def _apply_glyph(content: dict, proposal: dict) -> bool:
    glyph = proposal.get("glyph") or {}
    children = glyph.get("svg_children") if isinstance(glyph, dict) else None
    if not isinstance(children, str) or not children.strip():
        return False
    # Defence in depth: the pipeline sanitised before building the proposal,
    # but the proposal is stored JSON — only what passes the sanitiser NOW is
    # ever written where a page will render it.
    try:
        clean = sanitize_glyph(children)
    except SvgSanitizationError:
        raise HTTPException(
            status_code=422, detail="The glyph in this proposal isn't renderable — regenerate it"
        )
    content.setdefault("brand", {})["icon_svg"] = clean
    return True
