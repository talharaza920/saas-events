"""Wedding-scoped AI wizard API (AI_WIZARD_PLAN Phase 8.4) —
`/api/w/{wedding_slug}/admin/ai/*`.

  POST …/inputs               one pasted-text submission
  POST …/inputs/upload        one media submission (image/audio/pdf, multipart)
  POST …/jobs                 {kind, input_ids, options}  [Idempotency-Key]
  GET  …/jobs, …/jobs/{id}    status, step, proposal, variants
  POST …/jobs/{id}/advance    drives exactly ONE pipeline step; idempotent per step
  POST …/jobs/{id}/regenerate {artifact, steer?} → a new variant, old ones kept
  POST …/jobs/{id}/select     {artifact, variant_id} → the keeper, into the proposal
  POST …/jobs/{id}/apply      {selections?} → transactional, allowlisted writes only
  POST …/jobs/{id}/cancel     refunds the hold
  GET  …/credits              balance for the wizard UI

Everything rides `require_wedding` (401 unauth / 404 non-member / 403
suspended-write), and every job lookup re-checks `wedding_id` — the
belt-and-braces rule every admin query follows. The model proposes; code
disposes: nothing here writes wedding content except /apply, which goes
through app/ai/apply.py's writer allowlist.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.apply import apply_proposal
from app.ai.credits import arc_generations_used, credits_remaining
from app.ai.jobs import advance_job, cancel_job, create_job
from app.ai.media import GeminiMedia, get_media_model
from app.ai.providers import get_text_model
from app.ai.types import TextModel
from app.ai.variants import regenerate_artifact, select_variant
from app.authz import WeddingCtx, require_wedding
from app.config import Settings, get_settings
from app.db import get_db
from app.entitlements import effective_entitlements, require_feature
from app.models import AiInput, AiJob, AiVariant, Wedding
from app.storage import UploadError, store_ai_input, validate_ai_media
from app.schemas import (
    AiAdvanceRequest,
    AiApplyRequest,
    AiApplyResult,
    AiCreditsInfo,
    AiInputCreate,
    AiInputRef,
    AiJobAdmin,
    AiJobCreate,
    AiRegenerateRequest,
    AiSelectRequest,
    AiVariantAdmin,
)

router = APIRouter(prefix="/api/w/{wedding_slug}/admin/ai", tags=["ai"])

member_ctx = require_wedding("admin")
editor_ctx = require_wedding("admin", edit=True)

# Uploaded-but-unclaimed submissions are raw PII with a 24h reap TTL; this cap
# just keeps a stuck client from stockpiling them.
MAX_UNCLAIMED_INPUTS = 50


def get_job_text_model(settings: Settings = Depends(get_settings)) -> TextModel:
    """The provider seam as a dependency — tests override this to inject a
    scripted FakeTextModel without touching config."""
    return get_text_model(settings)


def get_job_media_model(settings: Settings = Depends(get_settings)) -> GeminiMedia:
    """The Gemini media seam as a dependency, same override story."""
    return get_media_model(settings)


def _check_unclaimed_cap(db: Session, wedding: Wedding) -> None:
    unclaimed = db.execute(
        select(func.count()).select_from(AiInput).where(
            AiInput.wedding_id == wedding.id, AiInput.job_id.is_(None)
        )
    ).scalar_one()
    if unclaimed >= MAX_UNCLAIMED_INPUTS:
        raise HTTPException(
            status_code=422,
            detail="Too many unused submissions — start a run with what you have first",
        )


def _get_job(db: Session, wedding: Wedding, job_id: UUID) -> AiJob:
    job = db.get(AiJob, job_id)
    if job is None or job.wedding_id != wedding.id:
        # Wrong tenant = same 404 as nonexistent — existence is never revealed.
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _variant_admin(v: AiVariant) -> AiVariantAdmin:
    return AiVariantAdmin(
        id=v.id, artifact=v.artifact, content=v.content, image_url=v.image_url,
        selected=v.selected, steer=v.steer, created_at=v.created_at,
    )


def _job_admin(db: Session, job: AiJob, *, with_variants: bool = True) -> AiJobAdmin:
    variants: list[AiVariantAdmin] = []
    if with_variants:
        variants = [
            _variant_admin(v)
            for v in db.execute(
                select(AiVariant)
                .where(AiVariant.job_id == job.id)
                .order_by(AiVariant.artifact, AiVariant.created_at)
            ).scalars()
        ]
    return AiJobAdmin(
        id=job.id, kind=job.kind, status=job.status,
        step=job.step, steps_total=job.steps_total,
        credits_held=job.credits_held, error=job.error, proposal=job.proposal,
        variants=variants, created_at=job.created_at, expires_at=job.expires_at,
    )


# --- Inputs ------------------------------------------------------------------
@router.post("/inputs", response_model=AiInputRef, status_code=201)
def create_input(
    payload: AiInputCreate,
    ctx: WeddingCtx = Depends(editor_ctx),
    db: Session = Depends(get_db),
) -> AiInputRef:
    require_feature(db, ctx.wedding, "ai_enabled")
    _check_unclaimed_cap(db, ctx.wedding)
    inp = AiInput(
        wedding_id=ctx.wedding.id,
        kind="text",
        text_content=payload.text,
        bytes=len(payload.text.encode("utf-8")),
        created_by=ctx.user.sub,
    )
    db.add(inp)
    db.commit()
    db.refresh(inp)
    return AiInputRef(id=inp.id, kind=inp.kind, bytes=inp.bytes, created_at=inp.created_at)


@router.post("/inputs/upload", response_model=AiInputRef, status_code=201)
async def upload_ai_input(
    file: UploadFile = File(...),
    ctx: WeddingCtx = Depends(editor_ctx),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AiInputRef:
    """One media submission (voice note / photo / PDF), stored under the
    transient ai-inputs namespace (unmetered, reaped with the job or the
    orphan sweep — never rendered on a page). Refused with a clear message
    when the Gemini seam isn't configured: better here than a run that fails
    at its very first step."""
    require_feature(db, ctx.wedding, "ai_enabled")
    _check_unclaimed_cap(db, ctx.wedding)
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=422,
            detail="Voice notes, photos and PDFs aren't available yet — paste text instead",
        )
    data = await file.read()
    try:
        kind, ext = validate_ai_media(file.content_type, len(data))
        url = store_ai_input(settings, ctx.wedding.slug, data, ext,
                             file.content_type or "application/octet-stream")
    except UploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    inp = AiInput(
        wedding_id=ctx.wedding.id,
        kind=kind,
        storage_url=url,
        mime=(file.content_type or "").lower(),
        bytes=len(data),
        created_by=ctx.user.sub,
    )
    db.add(inp)
    db.commit()
    db.refresh(inp)
    return AiInputRef(id=inp.id, kind=inp.kind, bytes=inp.bytes, created_at=inp.created_at)


# --- Jobs ----------------------------------------------------------------------
@router.post("/jobs", response_model=AiJobAdmin, status_code=201)
def create_ai_job(
    payload: AiJobCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=64),
    ctx: WeddingCtx = Depends(editor_ctx),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AiJobAdmin:
    job = create_job(
        db, settings, ctx.wedding,
        kind=payload.kind,
        input_ids=payload.input_ids,
        created_by=ctx.user.sub,
        idempotency_key=idempotency_key,
        options=payload.options,
    )
    return _job_admin(db, job)


@router.get("/jobs", response_model=list[AiJobAdmin])
def list_ai_jobs(
    ctx: WeddingCtx = Depends(member_ctx),
    db: Session = Depends(get_db),
) -> list[AiJobAdmin]:
    """Recent runs, newest first — how a reloaded wizard rediscovers the
    active/reviewable job. Variants omitted here (fetch the job for those)."""
    jobs = db.execute(
        select(AiJob)
        .where(AiJob.wedding_id == ctx.wedding.id)
        .order_by(AiJob.created_at.desc())
        .limit(20)
    ).scalars().all()
    return [_job_admin(db, j, with_variants=False) for j in jobs]


@router.get("/jobs/{job_id}", response_model=AiJobAdmin)
def get_ai_job(
    job_id: UUID,
    ctx: WeddingCtx = Depends(member_ctx),
    db: Session = Depends(get_db),
) -> AiJobAdmin:
    return _job_admin(db, _get_job(db, ctx.wedding, job_id))


@router.post("/jobs/{job_id}/advance", response_model=AiJobAdmin)
def advance_ai_job(
    job_id: UUID,
    payload: AiAdvanceRequest | None = None,
    ctx: WeddingCtx = Depends(editor_ctx),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    text_model: TextModel = Depends(get_job_text_model),
    media_model: GeminiMedia = Depends(get_job_media_model),
) -> AiJobAdmin:
    job = _get_job(db, ctx.wedding, job_id)
    job = advance_job(
        db, settings, job,
        text_model=text_model,
        media_model=media_model,
        expected_step=payload.expected_step if payload else None,
    )
    return _job_admin(db, job)


@router.post("/jobs/{job_id}/regenerate", response_model=AiVariantAdmin)
def regenerate_ai_artifact(
    job_id: UUID,
    payload: AiRegenerateRequest,
    ctx: WeddingCtx = Depends(editor_ctx),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    text_model: TextModel = Depends(get_job_text_model),
    media_model: GeminiMedia = Depends(get_job_media_model),
) -> AiVariantAdmin:
    job = _get_job(db, ctx.wedding, job_id)
    variant = regenerate_artifact(
        db, settings, job,
        artifact=payload.artifact, steer=payload.steer,
        text_model=text_model, media_model=media_model, user=ctx.user,
    )
    return _variant_admin(variant)


@router.post("/jobs/{job_id}/select", response_model=AiJobAdmin)
def select_ai_variant(
    job_id: UUID,
    payload: AiSelectRequest,
    ctx: WeddingCtx = Depends(editor_ctx),
    db: Session = Depends(get_db),
) -> AiJobAdmin:
    job = _get_job(db, ctx.wedding, job_id)
    select_variant(
        db, job, artifact=payload.artifact, variant_id=payload.variant_id, user=ctx.user
    )
    return _job_admin(db, job)


@router.post("/jobs/{job_id}/apply", response_model=AiApplyResult)
def apply_ai_job(
    job_id: UUID,
    payload: AiApplyRequest | None = None,
    ctx: WeddingCtx = Depends(editor_ctx),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AiApplyResult:
    job = _get_job(db, ctx.wedding, job_id)
    result = apply_proposal(
        db, settings, ctx.wedding, job,
        selections=payload.selections if payload else None,
        user=ctx.user,
    )
    return AiApplyResult(**result)


@router.post("/jobs/{job_id}/cancel", response_model=AiJobAdmin)
def cancel_ai_job(
    job_id: UUID,
    ctx: WeddingCtx = Depends(editor_ctx),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AiJobAdmin:
    job = _get_job(db, ctx.wedding, job_id)
    return _job_admin(db, cancel_job(db, settings, job))


# --- Credits -------------------------------------------------------------------
@router.get("/credits", response_model=AiCreditsInfo)
def ai_credits(
    ctx: WeddingCtx = Depends(member_ctx),
    db: Session = Depends(get_db),
) -> AiCreditsInfo:
    ents = effective_entitlements(db, ctx.wedding)

    def _int(key: str) -> int:
        v = ents.get(key, 0)
        return v if isinstance(v, int) and not isinstance(v, bool) else 0

    return AiCreditsInfo(
        remaining=credits_remaining(db, ctx.wedding),
        included=_int("ai_credits_included"),
        arc_generations_used=arc_generations_used(db, ctx.wedding),
        arc_generations_included=_int("ai_arc_generations_included"),
    )
