"""On-demand illustration of a story draft (AI_WIZARD_PLAN Phase 8.5b).

Until 8.5b, a `story_arc` run illustrated every beat automatically as a
pipeline step — the couple paid for art before they had even read the text, and
the first thing they did was change the words. Images are now a SEPARATE,
explicitly clicked stage: the run parks at review as text only (cheap to
iterate), and money moves only when someone presses a button.

    review (text only) ──▶ illustrate ["0"] ──▶ iterate style on that one image
                                            ──▶ illustrate (rest + climax)

`targets` are the panels of a draft: "0".."7" for the beats, "climax" for the
closing "you're invited" panel. Each generated image charges 1 credit onto the
job's hold (so cancelling still refunds it), is metered against the wedding's
storage, and has its bytes tracked in `job.state["image_bytes"]` so the sweeps
(cancel / expire / apply) can free whatever the final proposal didn't keep.

Degrading, not failing, stays the rule: a refusal on one scene, a missing key
or a full bucket leaves that panel text-only. The proposal is a review
artifact — it must never be less applicable than it was a second ago.
"""
from __future__ import annotations

import logging
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai.credits import IMAGE_CREDIT_COST, credits_remaining
from app.ai.ledger import record_usage
from app.ai.media import GeminiMedia, get_media_model, sniff_image_mime
from app.ai.styles import compose_image_prompt
from app.ai.types import ProviderError, ProviderRefusal
from app.audit_log import record
from app.config import Settings
from app.entitlements import check_storage, effective_entitlements, require_feature
from app.models import AiJob, AiJobKind, AiJobStatus
from app.obs import log_event
from app.storage import prepare_image, store_image, UploadError

logger = logging.getLogger("app.ai")

CLIMAX_TARGET = "climax"
TARGET_RE = re.compile(rf"^(?:\d{{1,2}}|{CLIMAX_TARGET})$")

# How many images one /illustrate call generates. Each is ~5–15 s at the
# provider, so two keeps the request comfortably inside serverless timeouts and
# the client simply calls again while `pending` is non-empty.
IMAGES_PER_CALL = 2


def illustration_targets(proposal: dict | None) -> list[tuple[str, str]]:
    """Every panel of the CURRENT draft that has a scene to render, in order:
    the beats, then the climax. The prompts are the ones the couple can edit
    (PATCH /proposal), so this always reflects their latest wording."""
    arc = (proposal or {}).get("story_arc") or {}
    if not isinstance(arc, dict):
        return []
    out: list[tuple[str, str]] = []
    beats = arc.get("beats")
    for i, beat in enumerate(beats if isinstance(beats, list) else []):
        prompt = (beat or {}).get("image_prompt") if isinstance(beat, dict) else None
        if isinstance(prompt, str) and prompt.strip():
            out.append((str(i), prompt.strip()))
    climax_prompt = arc.get("climax_image_prompt")
    if isinstance(climax_prompt, str) and climax_prompt.strip():
        out.append((CLIMAX_TARGET, climax_prompt.strip()))
    return out


def pending_targets(job: AiJob) -> list[str]:
    """Panels with a scene but no image yet (a refused one is not pending — it
    would just refuse again; the couple can still redo it deliberately)."""
    proposal = job.proposal or {}
    images = proposal.get("beat_images") or {}
    refused = proposal.get("images_refused") or {}
    return [
        key
        for key, _ in illustration_targets(proposal)
        if key not in images and key not in refused
    ]


def image_cap(db: Session, job: AiJob) -> int:
    cap = effective_entitlements(db, job.wedding).get("ai_max_images_per_arc", 0)
    return cap if isinstance(cap, int) and not isinstance(cap, bool) else 0


def render_image(
    db: Session,
    settings: Settings,
    job: AiJob,
    prompt: str,
    media: GeminiMedia,
) -> str:
    """One image: generate → ledger → meter → store. Returns the stored URL.
    Raises ProviderRefusal (content filter), ProviderError (unusable bytes) or
    HTTPException 403 (storage full) — the callers decide what each means.

    Shared by /illustrate and the per-panel regeneration path so an image is
    accounted for identically however it was asked for."""
    data, usage = media.generate_image(prompt)
    record_usage(db, wedding_id=job.wedding_id, job_id=job.id, kind="image",
                 usage=usage, images=1)
    try:
        blob, ext = prepare_image(data, sniff_image_mime(data))
    except UploadError as exc:
        raise ProviderError(f"the generated image wasn't usable ({exc}) — try again")
    check_storage(db, job.wedding, adding_bytes=len(blob))
    url = store_image(settings, job.wedding.slug, blob, ext, sniff_image_mime(data))
    job.wedding.storage_bytes_used = (job.wedding.storage_bytes_used or 0) + len(blob)
    state = dict(job.state or {})
    tracked = dict(state.get("image_bytes") or {})
    tracked[url] = len(blob)
    state["image_bytes"] = tracked
    job.state = state  # reassign: JSON columns don't track mutation
    return url


def illustrate(
    db: Session,
    settings: Settings,
    job: AiJob,
    *,
    targets: list[str] | None = None,
    media_model: GeminiMedia | None = None,
    user=None,
) -> AiJob:
    """Render up to IMAGES_PER_CALL panels of a story proposal.

    `targets=None` = the next batch of pending panels (how "illustrate the
    rest" works); an explicit list = exactly those, which is how the couple
    asks for beat 0 first and then re-renders it after changing the style.
    Raises 409 (not in review), 422 (wrong kind / unknown target), 403
    (credits), 503 (breaker) — the last surfaces from check_circuit_breaker.
    Commits."""
    from app.ai.jobs import check_circuit_breaker  # local: jobs imports styles-free

    if job.kind != AiJobKind.STORY_ARC:
        raise HTTPException(status_code=422, detail="Only a story run has scenes to illustrate")
    if job.status != AiJobStatus.AWAITING_REVIEW:
        raise HTTPException(status_code=409, detail=f"Job is {job.status}")
    require_feature(db, job.wedding, "ai_enabled")
    if not settings.ai_images_available:
        raise HTTPException(
            status_code=422,
            detail="Illustrations aren't available right now — your story text is unaffected",
        )
    check_circuit_breaker(db)

    proposal = dict(job.proposal or {})
    scenes = dict(illustration_targets(proposal))
    if targets is None:
        wanted = pending_targets(job)[:IMAGES_PER_CALL]
    else:
        unknown = [t for t in targets if t not in scenes]
        if unknown:
            raise HTTPException(status_code=422, detail="There's no scene to illustrate there")
        wanted = targets[:IMAGES_PER_CALL]
    if not wanted:
        return job

    # The cap counts illustrated panels of THIS arc, so illustrating them one
    # at a time can't walk past it. A redo replaces a panel, so it doesn't
    # consume room.
    images = dict(proposal.get("beat_images") or {})
    refused = dict(proposal.get("images_refused") or {})
    cap = image_cap(db, job)
    if all(key not in images for key in wanted) and len(images) >= cap:
        raise HTTPException(
            status_code=403,
            detail=f"This plan illustrates up to {cap} panels per story — contact us to upgrade",
        )

    options = (job.state or {}).get("options") or {}
    media = media_model or get_media_model(settings)
    charged = 0
    for key in wanted:
        if key not in images and len(images) >= cap:
            break
        if credits_remaining(db, job.wedding) < IMAGE_CREDIT_COST:
            if charged:  # keep what we generated; tell them why we stopped
                break
            raise HTTPException(
                status_code=403,
                detail="You've used all this wedding's AI credits — contact us to upgrade",
            )
        prompt = compose_image_prompt(scenes[key], options)
        try:
            url = render_image(db, settings, job, prompt, media)
        except ProviderRefusal as exc:
            log_event(logger, "ai.image.refused", job_id=str(job.id), target=key)
            refused[key] = str(exc)[:200]
            continue
        except ProviderError as exc:
            refused[key] = str(exc)[:200]
            continue
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
            # Storage full: stop here, keep everything already rendered.
            refused[key] = "this wedding's storage is full"
            break
        images[key] = url
        refused.pop(key, None)
        charged += IMAGE_CREDIT_COST
        job.credits_held += IMAGE_CREDIT_COST  # rides the hold: refunded with it

    proposal["beat_images"] = images
    proposal["images_refused"] = refused
    job.proposal = proposal  # reassign: JSON column
    record(
        db, "ai.job.illustrate", user=user, wedding=job.wedding,
        target_type="ai_job", target_id=job.id,
        detail={"targets": wanted, "charged": charged, "refused": sorted(refused)},
    )
    db.commit()
    db.refresh(job)
    return job
