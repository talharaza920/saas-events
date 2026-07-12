"""Per-artifact regeneration + variant selection (AI_WIZARD_PLAN
"Regeneration and variants").

The first draft will not be the one they keep — this is the designed-for path,
not an error path. While a job sits in `awaiting_review`:

  regenerate {artifact, steer?} → appends an `ai_variants` row and leaves every
      previous one intact (the version the couple might, on reflection, have
      preferred is never destroyed). The FIRST regeneration of each artifact is
      free — a bad first output is our prompt's fault, not the couple's;
      subsequent ones draw 1 credit, bounded by `ai_max_regens_per_artifact`.
  select {artifact, variant_id} → marks the keeper and writes its content into
      `job.proposal`, so the apply allowlist (app/ai/apply.py) needs no change
      and never learns variants exist.

The `steer` note is the ONLY place a wedding owner instructs the model. It is
untrusted: bounded in length and placed in the USER turn, never concatenated
into the system prompt — the output stays schema-constrained and human-applied,
which is why it's safe to offer at all.

Failed and refused regenerations never charge (the ledger still records calls
that did run — real dollars were spent — but the couple's credits don't move).

Artifacts today: `arc.text` (draft + a fresh grounding pass — a regenerated
draft can invent facts just like the first one), `glyph` (re-sanitised before
storage, same as the pipeline step) and `arc.beat.N` (that beat's Nano Banana
image, re-rendered from the CURRENT draft's scene description).
"""
from __future__ import annotations

import copy
import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.jobs import _dump, check_circuit_breaker
from app.ai.credits import credits_remaining
from app.ai.ledger import record_usage
from app.ai.media import GeminiMedia, get_media_model, sniff_image_mime
from app.ai.prompts import render_prompt
from app.ai.schemas import DraftArc, GlyphOutput, GroundingReport
from app.ai.svg import SvgSanitizationError, sanitize_glyph
from app.ai.types import EFFORT_VALUES, ProviderError, ProviderRefusal, TextModel
from app.audit_log import record
from app.config import Settings
from app.entitlements import check_limit, check_storage, require_feature
from app.models import AiJob, AiJobKind, AiJobStatus, AiVariant
from app.storage import prepare_image, store_image, UploadError

ARTIFACT_ARC_TEXT = "arc.text"
ARTIFACT_GLYPH = "glyph"
# A single beat's image: "arc.beat.0", "arc.beat.1", … (index into the
# CURRENT proposal's beats).
ARTIFACT_BEAT_RE = re.compile(r"^arc\.beat\.(\d{1,2})$")
# Which artifacts a job of each kind can regenerate (a wizard proposal has no
# glyph — the glyph pipeline is its own kind). Beat images are validated by
# _beat_index (they need a beat count, not a fixed list).
ARTIFACTS_BY_KIND: dict[str, tuple[str, ...]] = {
    AiJobKind.WIZARD: (ARTIFACT_ARC_TEXT,),
    AiJobKind.STORY_ARC: (ARTIFACT_ARC_TEXT,),
    AiJobKind.GLYPH: (ARTIFACT_GLYPH,),
}
MAX_STEER_CHARS = 500
REGEN_CREDIT_COST = 1  # after the free first regen of each artifact


def _beat_index(job: AiJob, artifact: str) -> int | None:
    """The beat index for an `arc.beat.N` artifact of THIS job, or None."""
    if job.kind not in (AiJobKind.WIZARD, AiJobKind.STORY_ARC):
        return None
    m = ARTIFACT_BEAT_RE.match(artifact)
    if not m:
        return None
    index = int(m.group(1))
    beats = ((job.proposal or {}).get("story_arc") or {}).get("beats") or []
    return index if index < len(beats) else None


def regenerate_artifact(
    db: Session,
    settings: Settings,
    job: AiJob,
    *,
    artifact: str,
    steer: str | None = None,
    text_model: TextModel,
    media_model: GeminiMedia | None = None,
    user=None,
) -> AiVariant:
    """Generate a new variant of `artifact`. Raises 409 (not in review),
    422 (artifact/kind mismatch, or the model declined), 403 (regen cap or
    credits), 503 (circuit breaker), 502 (provider error). Commits on success."""
    wedding = job.wedding
    require_feature(db, wedding, "ai_enabled")
    if job.status != AiJobStatus.AWAITING_REVIEW:
        raise HTTPException(status_code=409, detail=f"Job is {job.status}")
    beat = _beat_index(job, artifact)
    if artifact not in ARTIFACTS_BY_KIND.get(job.kind, ()) and beat is None:
        raise HTTPException(
            status_code=422,
            detail=f"A {job.kind} run has no {artifact!r} to regenerate",
        )
    check_circuit_breaker(db)
    steer = (steer or "").strip()[:MAX_STEER_CHARS] or None

    existing = db.execute(
        select(AiVariant)
        .where(AiVariant.job_id == job.id, AiVariant.artifact == artifact)
        .order_by(AiVariant.created_at)
    ).scalars().all()
    # Variant 0 is the seeded original, so regens done = rows beyond it.
    regens_done = max(len(existing) - 1, 0)
    check_limit(
        db, wedding, "ai_max_regens_per_artifact", current_count=regens_done, adding=1
    )
    charge = 0 if regens_done == 0 else REGEN_CREDIT_COST
    if charge and credits_remaining(db, wedding) < charge:
        raise HTTPException(
            status_code=403,
            detail="You've used all this wedding's AI credits — contact us to upgrade",
        )

    # Generate BEFORE any variant/credit writes so a refusal or provider error
    # charges nothing. Ledger rows for calls that DID run are kept (real money
    # was spent) — commit them even on the failure paths.
    image_url: str | None = None
    try:
        if artifact == ARTIFACT_ARC_TEXT:
            content, meta = _regen_arc_text(db, settings, job, steer, text_model)
        elif beat is not None:
            content = None
            image_url, meta = _regen_beat_image(
                db, settings, job, beat, steer, media_model
            )
        else:
            content, meta = _regen_glyph(db, settings, job, steer, text_model)
    except ProviderRefusal as exc:
        db.commit()
        raise HTTPException(
            status_code=422,
            detail=f"The model declined this request: {exc} — adjust your note and try again",
        )
    except ProviderError as exc:
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc))

    if not existing:
        original = _original_variant(job, artifact)
        if original is not None:  # a beat that never had art has no original
            db.add(original)
    variant = AiVariant(
        wedding_id=job.wedding_id,
        job_id=job.id,
        artifact=artifact,
        content=content,
        image_url=image_url,
        steer=steer,
        **meta,
    )
    db.add(variant)
    if charge:
        job.credits_held += charge  # rides the job's hold: refunded with it
    record(
        db, "ai.job.regenerate", user=user, wedding=wedding,
        target_type="ai_job", target_id=job.id,
        detail={"artifact": artifact, "charged": charge, "steered": steer is not None},
    )
    db.commit()
    db.refresh(variant)
    return variant


def select_variant(
    db: Session, job: AiJob, *, artifact: str, variant_id, user=None
) -> AiVariant:
    """Mark one variant as the keeper and write its content into the proposal
    (the apply allowlist reads only the proposal — it never learns variants
    exist). Raises 409 (not in review), 404 (variant not of this job/artifact)."""
    if job.status != AiJobStatus.AWAITING_REVIEW:
        raise HTTPException(status_code=409, detail=f"Job is {job.status}")
    chosen = db.get(AiVariant, variant_id)
    if chosen is None or chosen.job_id != job.id or chosen.artifact != artifact:
        raise HTTPException(status_code=404, detail="Variant not found")

    for v in db.execute(
        select(AiVariant).where(AiVariant.job_id == job.id, AiVariant.artifact == artifact)
    ).scalars():
        v.selected = v.id == chosen.id

    proposal = copy.deepcopy(job.proposal or {})
    content = chosen.content or {}
    beat = _beat_index(job, artifact)
    if artifact == ARTIFACT_ARC_TEXT:
        proposal["story_arc"] = content.get("story_arc")
        proposal["grounding"] = content.get("grounding")
        # Beat art belongs to the draft that described its scenes — selecting
        # a different text variant restores THAT draft's images (none, for a
        # fresh regen: its scenes have never been rendered).
        proposal["beat_images"] = content.get("beat_images") or {}
    elif beat is not None:
        images = dict(proposal.get("beat_images") or {})
        if chosen.image_url:
            images[str(beat)] = chosen.image_url
        else:
            images.pop(str(beat), None)
        proposal["beat_images"] = images
    else:
        proposal["glyph"] = content
    job.proposal = proposal  # reassign: JSON columns don't track mutation
    record(
        db, "ai.variant.select", user=user, wedding=job.wedding,
        target_type="ai_variant", target_id=chosen.id, detail={"artifact": artifact},
    )
    db.commit()
    return chosen


# ---------------------------------------------------------------------------
# Generation — mirrors the pipeline steps, plus the optional <steer> tag.
# ---------------------------------------------------------------------------
def _call(db, settings, job, text_model, *, key, user, schema, variables=None, ledger_kind):
    prompt = render_prompt(
        db, key, provider=settings.ai_text_provider, user=user, variables=variables
    )
    effort = prompt.effort if prompt.effort in EFFORT_VALUES else settings.ai_text_effort
    if effort not in EFFORT_VALUES:
        effort = "high"
    completion = text_model.generate_structured(prompt, schema, effort=effort)
    record_usage(db, wedding_id=job.wedding_id, job_id=job.id,
                 kind=ledger_kind, usage=completion.usage)
    meta = {
        "provider": completion.usage.provider, "model": completion.usage.model,
        "prompt_key": prompt.key, "prompt_version": prompt.version,
    }
    return completion.output, meta


def _regen_arc_text(db, settings, job, steer, text_model):
    state = job.state or {}
    options = state.get("options") or {}
    tone = options.get("tone") or "warm, specific, unsentimental"
    user_turn = (
        f"<submission>\n{state.get('submission', '')}\n</submission>\n"
        f"<facts>\n{_dump(state.get('facts') or {})}\n</facts>\n"
        f"<style>\n{tone}\n</style>"
    )
    if steer:  # user-turn data only — never in the system prompt
        user_turn += f"\n<steer>\n{steer}\n</steer>"
    draft, meta = _call(
        db, settings, job, text_model,
        key="draft_arc.system", user=user_turn, schema=DraftArc,
        variables={"beat_count": options.get("beat_count", 4)}, ledger_kind="draft",
    )
    # Re-ground: a regenerated draft can invent facts exactly like the first.
    report, _ = _call(
        db, settings, job, text_model,
        key="ground.system",
        user=f"SOURCE:\n{state.get('submission', '')}\n\nDRAFT:\n{_dump(draft.model_dump())}",
        schema=GroundingReport, ledger_kind="ground",
    )
    # beat_images deliberately empty: this draft's scenes have never been
    # rendered (selecting the variant must not pair it with stale art).
    return {
        "story_arc": draft.model_dump(),
        "grounding": report.model_dump(),
        "beat_images": {},
    }, meta


def _regen_beat_image(db, settings, job, beat: int, steer, media_model):
    """Re-render ONE beat's art from the current draft's scene description.
    Mirrors the pipeline's images step: ledgered per image, metered against
    the wedding's storage, bytes tracked in job.state for the sweeps."""
    proposal = job.proposal or {}
    beats = (proposal.get("story_arc") or {}).get("beats") or []
    prompt = (beats[beat].get("image_prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="This beat has no scene to illustrate")
    if steer:  # untrusted, appended to the scene text — never a system prompt
        prompt += f". Adjustment requested by the couple: {steer}"

    media = media_model or get_media_model(settings)
    data, usage = media.generate_image(prompt)  # ProviderRefusal/Error → caller maps
    record_usage(db, wedding_id=job.wedding_id, job_id=job.id,
                 kind="image", usage=usage, images=1)
    mime = sniff_image_mime(data)
    try:
        blob, ext = prepare_image(data, mime)
    except UploadError as exc:
        raise ProviderError(f"the generated image wasn't usable ({exc}) — try again")
    check_storage(db, job.wedding, adding_bytes=len(blob))
    url = store_image(settings, job.wedding.slug, blob, ext, mime)
    job.wedding.storage_bytes_used = (job.wedding.storage_bytes_used or 0) + len(blob)
    state = dict(job.state or {})
    tracked = dict(state.get("image_bytes") or {})
    tracked[url] = len(blob)
    state["image_bytes"] = tracked
    job.state = state  # reassign: JSON columns don't track mutation
    return url, {"provider": usage.provider, "model": usage.model}


def _regen_glyph(db, settings, job, steer, text_model):
    state = job.state or {}
    user_turn = f"<submission>\n{state.get('submission', '')}\n</submission>"
    if steer:
        user_turn += f"\n<steer>\n{steer}\n</steer>"
    glyph, meta = _call(
        db, settings, job, text_model,
        key="glyph.system", user=user_turn, schema=GlyphOutput, ledger_kind="glyph",
    )
    try:
        children = sanitize_glyph(glyph.svg_children)
    except SvgSanitizationError as exc:
        raise ProviderError(f"the generated mark wasn't usable ({exc}) — try again")
    return {"svg_children": children, "concept": glyph.concept, "sanitised": True}, meta


def _original_variant(job: AiJob, artifact: str) -> AiVariant | None:
    """Variant 0: the proposal's current content, so regenerating never loses
    the original. Selected until the couple picks otherwise. None when there
    is nothing to preserve (a beat that never had art)."""
    proposal = job.proposal or {}
    generation = (job.state or {}).get("generation") or {}
    beat = _beat_index(job, artifact)
    if beat is not None:
        url = (proposal.get("beat_images") or {}).get(str(beat))
        if not url:
            return None
        return AiVariant(
            wedding_id=job.wedding_id,
            job_id=job.id,
            artifact=artifact,
            image_url=url,
            selected=True,
            provider="google",
            model=None,  # the pipeline's configured image model at the time
        )
    if artifact == ARTIFACT_ARC_TEXT:
        content = {
            "story_arc": proposal.get("story_arc"),
            "grounding": proposal.get("grounding"),
            "beat_images": proposal.get("beat_images") or {},
        }
        gen = generation.get("draft") or {}
    else:
        content = proposal.get("glyph")
        gen = generation.get("glyph") or {}
    return AiVariant(
        wedding_id=job.wedding_id,
        job_id=job.id,
        artifact=artifact,
        content=content,
        selected=True,
        provider=gen.get("provider"),
        model=gen.get("model"),
        prompt_key=gen.get("prompt_key"),
        prompt_version=gen.get("prompt_version"),
    )
