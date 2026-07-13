"""Direct human edits to a story proposal (AI_WIZARD_PLAN Phase 8.5b).

The couple should be able to fix a word without asking a model to try again —
regeneration is for "make it different", editing is for "make it right". So
PATCH /proposal is FREE, makes no provider call, and is the shortest path from
"almost" to "yes".

Three rules hold it together:

1. **The schema still owns the shape.** An edit re-validates through `DraftArc`,
   exactly like the model's own output does, so the bounds (beat count, string
   lengths, no extra fields) can't be widened by hand-posting JSON. Nothing but
   `story_arc` is writable — an edit can't reach `guests`, `glyph` or the venue.
2. **Edited fields lose their grounding flags.** The grounding pass exists to
   catch the MODEL inventing things; a sentence the couple typed themselves
   needs no receipt from us. Stale claims (whose text no longer appears in the
   draft) are dropped with it.
3. **Edits are recorded, so regeneration can't quietly eat them.** Every edited
   path lands in `proposal["user_edited"]`; the review UI warns before a
   regenerated variant is selected over hand-written words. (Regeneration
   itself is non-destructive — it appends a variant and leaves the original,
   edits and all, as variant 0.)
"""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.schemas import DraftArc
from app.ai.styles import MAX_STYLE_NOTE_CHARS, STYLE_PRESETS, resolve_style
from app.audit_log import record
from app.models import AiJob, AiJobKind, AiJobStatus


def edit_proposal(
    db: Session,
    job: AiJob,
    *,
    story_arc: dict | None = None,
    style_preset: str | None = None,
    style_note: str | None = None,
    user=None,
) -> AiJob:
    """Apply the couple's own edits to a story proposal. Raises 409 (not in
    review), 422 (wrong kind, malformed draft, unknown style). Commits."""
    if job.kind != AiJobKind.STORY_ARC:
        raise HTTPException(status_code=422, detail="Only a story run has a draft to edit")
    if job.status != AiJobStatus.AWAITING_REVIEW:
        raise HTTPException(status_code=409, detail=f"Job is {job.status}")

    proposal = dict(job.proposal or {})
    edited: list[str] = list(proposal.get("user_edited") or [])

    if story_arc is not None:
        try:
            draft = DraftArc.model_validate(story_arc)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"That edit doesn't fit the story format ({exc.error_count()} problem(s))",
            )
        new_arc = draft.model_dump()
        before = proposal.get("story_arc") or {}
        for path in _changed_paths(before, new_arc):
            if path not in edited:
                edited.append(path)
        proposal["story_arc"] = new_arc
        proposal["grounding"] = _prune_grounding(proposal.get("grounding"), new_arc, edited)
        # Images belong to the scene that described them: editing a beat's
        # illustration line invalidates its art, so drop the pairing (the bytes
        # are swept at apply/cancel) rather than showing a picture of the old
        # sentence. The text edit alone leaves art alone.
        proposal["beat_images"] = _drop_restyled(
            proposal.get("beat_images"), before, new_arc
        )
        proposal["user_edited"] = edited

    if style_preset is not None or style_note is not None:
        _set_style(job, style_preset, style_note)
    # The style lives in the job's options, but the proposal is the only thing
    # that crosses the wire — echo it there so the review UI reads one surface.
    options = (job.state or {}).get("options") or {}
    proposal["style"] = {
        "preset": resolve_style(options).key,
        "note": options.get("style_note") or None,
    }

    job.proposal = proposal  # reassign: JSON columns don't track mutation
    record(
        db, "ai.job.edit", user=user, wedding=job.wedding,
        target_type="ai_job", target_id=job.id,
        detail={"fields": edited, "style": style_preset} if story_arc else {"style": style_preset},
    )
    db.commit()
    db.refresh(job)
    return job


def _set_style(job: AiJob, preset: str | None, note: str | None) -> None:
    """Style is a rendering choice, so it lives with the job's options, not in
    the draft — re-picking it must not touch a word of the approved text."""
    if preset is not None and preset not in STYLE_PRESETS:
        raise HTTPException(status_code=422, detail=f"Unknown illustration style {preset!r}")
    state = dict(job.state or {})
    options = dict(state.get("options") or {})
    if preset is not None:
        options["style_preset"] = preset
    if note is not None:
        options["style_note"] = note.strip()[:MAX_STYLE_NOTE_CHARS]
    state["options"] = options
    job.state = state


def _changed_paths(before: dict, after: dict) -> list[str]:
    """Dotted paths the couple actually changed ("heading", "beats.2.text")."""
    paths: list[str] = []
    for key in ("kicker", "heading", "intro", "climax", "climax_image_prompt"):
        if before.get(key) != after.get(key):
            paths.append(key)
    old_beats = before.get("beats") or []
    new_beats = after.get("beats") or []
    for i, beat in enumerate(new_beats):
        old = old_beats[i] if i < len(old_beats) and isinstance(old_beats[i], dict) else {}
        for key in ("text", "image_prompt"):
            if old.get(key) != beat.get(key):
                paths.append(f"beats.{i}.{key}")
    return paths


def _prune_grounding(grounding, arc: dict, edited: list[str]):
    """Keep only the claims still worth reading: the flagged text must still
    appear in the draft, and it must not be in a line the couple rewrote."""
    if not isinstance(grounding, dict):
        return grounding
    claims = grounding.get("unsupported")
    if not isinstance(claims, list):
        return grounding
    own_words = {
        arc.get(f) for f in ("kicker", "heading", "intro", "climax") if f in _edited_fields(edited)
    }
    for i, beat in enumerate(arc.get("beats") or []):
        if f"beats.{i}.text" in edited and isinstance(beat, dict):
            own_words.add(beat.get("text"))
    live = _draft_text(arc)
    kept = [
        c
        for c in claims
        if isinstance(c, dict)
        and isinstance(c.get("draft_text"), str)
        and c["draft_text"] in live
        and c["draft_text"] not in own_words
    ]
    return {"unsupported": kept, "all_supported": not kept}


def _edited_fields(edited: list[str]) -> set[str]:
    return {p for p in edited if "." not in p}


def _draft_text(arc: dict) -> str:
    parts = [arc.get(f) or "" for f in ("kicker", "heading", "intro", "climax")]
    parts += [
        (b or {}).get("text") or "" for b in (arc.get("beats") or []) if isinstance(b, dict)
    ]
    return "\n".join(parts)


def _drop_restyled(images, before: dict, after: dict) -> dict:
    """Beat art whose scene description changed is art of a scene that no
    longer exists — unpair it (the sweep frees the bytes)."""
    images = dict(images or {}) if isinstance(images, dict) else {}
    old_beats = before.get("beats") or []
    for i, beat in enumerate(after.get("beats") or []):
        old = old_beats[i] if i < len(old_beats) and isinstance(old_beats[i], dict) else {}
        if isinstance(beat, dict) and old.get("image_prompt") != beat.get("image_prompt"):
            images.pop(str(i), None)
    if before.get("climax_image_prompt") != after.get("climax_image_prompt"):
        images.pop("climax", None)
    return images
