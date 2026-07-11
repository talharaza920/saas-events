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

The `guests` writer lands with the `guests` job kind (8.1c): names only, tier
from the deterministic guest_import.infer_tier(), never from the model, and
`story_arc_ids` never AI-populated (that's how tier stays unleakable).
"""
from __future__ import annotations

import copy
import json

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.schemas import DraftArc
from app.ai.svg import SvgSanitizationError, sanitize_glyph
from app.approval import get_approval_rules
from app.audit_log import record
from app.entitlements import check_limit
from app.models import AiJob, AiJobStatus, StoryArc, Wedding

# Order is apply order (names/details before the arc that may mention them).
APPLY_SECTIONS = ("couple_names", "event_details", "story_arc", "glyph")


def apply_proposal(
    db: Session,
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
    wanted = [s for s in APPLY_SECTIONS if s in requested and proposal.get(s) is not None]
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
            "story_arc": lambda: _apply_story_arc(db, wedding, proposal),
            "glyph": lambda: _apply_glyph(content, proposal),
        }[section]()
        if wrote:
            applied.append(section)
    if not applied:
        raise HTTPException(status_code=422, detail="Nothing in this proposal matches the selection")

    wedding.content = content
    job.status = AiJobStatus.APPLIED
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


def _apply_story_arc(db: Session, wedding: Wedding, proposal: dict) -> bool:
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
    arc_content = {
        "kicker": draft.kicker,
        "heading": draft.heading,
        "intro": draft.intro,
        # Beats are numbered by position on render; image URLs arrive when the
        # images step lands (8.1c) — text-only beats render as feathered panels.
        "beats": [{"text": beat.text} for beat in draft.beats],
        "climax": {"text": draft.climax} if draft.climax else None,
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
