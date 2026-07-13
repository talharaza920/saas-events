"""Wedding-scoped AI wizard API (AI_WIZARD_PLAN Phase 8.4) —
`/api/w/{wedding_slug}/admin/ai/*`.

  POST …/inputs               one pasted-text submission
  POST …/inputs/upload        one media submission (image/audio/pdf, multipart);
                              role=reference + consent = a photo OF the couple (8.5d)
  POST …/jobs                 {kind, input_ids, options}  [Idempotency-Key]
  GET  …/jobs, …/jobs/{id}    status, step, proposal, variants
  POST …/jobs/{id}/advance    drives exactly ONE pipeline step; idempotent per step
  POST …/jobs/{id}/answers    {answers} → clears up an ambiguous guest list; ONE re-extract
  PATCH …/jobs/{id}/proposal  {story_arc?, style_preset?, style_note?} → free human edits
  POST …/jobs/{id}/references {input_ids} → the consented photos to draw them from
  POST …/jobs/{id}/illustrate {targets?} → renders panels; 1 credit each
  POST …/jobs/{id}/regenerate {artifact, steer?} → a new variant, old ones kept
  POST …/jobs/{id}/select     {artifact, variant_id} → the keeper, into the proposal
  POST …/jobs/{id}/apply      {selections?} → transactional, allowlisted writes only
  POST …/jobs/{id}/cancel     refunds the hold
  GET  …/credits, …/styles    balance + the illustration-style chips

Everything rides `require_wedding` (401 unauth / 404 non-member / 403
suspended-write), and every job lookup re-checks `wedding_id` — the
belt-and-braces rule every admin query follows. The model proposes; code
disposes: nothing here writes wedding content except /apply, which goes
through app/ai/apply.py's writer allowlist.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.apply import apply_proposal
from app.ai.askback import answer_questions
from app.ai.credits import arc_generations_used, credits_remaining
from app.ai.edit import edit_proposal
from app.ai.images import illustrate
from app.ai.jobs import advance_job, cancel_job, create_job
from app.ai.likeness import (
    BLOCKED_LIKENESS_STYLES,
    REFERENCE_ROLE,
    SOURCE_ROLE,
    set_references,
)
from app.ai.media import GeminiMedia, get_media_model
from app.ai.providers import get_text_model
from app.ai.runtime import effective_settings
from app.ai.styles import STYLE_PRESETS
from app.ai.types import TextModel
from app.ai.variants import regenerate_artifact, select_variant
from app.authz import WeddingCtx, require_wedding
from app.config import Settings, get_settings
from app.db import get_db
from app.entitlements import effective_entitlements, require_feature
from app.models import AiInput, AiJob, AiVariant, Wedding
from app.storage import UploadError, store_ai_input, validate_ai_media
from app.timeutil import utcnow
from app.schemas import (
    AiAdvanceRequest,
    AiAnswersRequest,
    AiApplyRequest,
    AiApplyResult,
    AiCreditsInfo,
    AiIllustrateRequest,
    AiInputCreate,
    AiInputRef,
    AiJobAdmin,
    AiJobCreate,
    AiProposalEdit,
    AiReferencesRequest,
    AiRegenerateRequest,
    AiSelectRequest,
    AiStyleOption,
    AiVariantAdmin,
)

router = APIRouter(prefix="/api/w/{wedding_slug}/admin/ai", tags=["ai"])

member_ctx = require_wedding("admin")
editor_ctx = require_wedding("admin", edit=True)

# Uploaded-but-unclaimed submissions are raw PII with a 24h reap TTL; this cap
# just keeps a stuck client from stockpiling them.
MAX_UNCLAIMED_INPUTS = 50


def get_ai_settings_effective(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> Settings:
    """Config for every AI route: env, with the platform console's text-model
    choice applied on top (ai/runtime.py).

    Every route in this router takes THIS instead of `get_settings`, so the
    console's choice reaches `render_prompt(provider=…)`, the effort default and
    the adapter alike — one seam, not a parameter threaded through the pipeline.
    """
    return effective_settings(db, settings)


def get_job_text_model(settings: Settings = Depends(get_ai_settings_effective)) -> TextModel:
    """The provider seam as a dependency — tests override this to inject a
    scripted FakeTextModel without touching config."""
    return get_text_model(settings)


def get_job_media_model(settings: Settings = Depends(get_settings)) -> GeminiMedia:
    """The Gemini media seam as a dependency, same override story. NOT overlaid:
    the console picks the TEXT model; Gemini is the hard-coded media seam."""
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
    role: str = Form(default=SOURCE_ROLE),
    consent: bool = Form(default=False),
    ctx: WeddingCtx = Depends(editor_ctx),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_ai_settings_effective),
) -> AiInputRef:
    """One media submission (voice note / photo / PDF / spreadsheet), stored
    under the transient ai-inputs namespace (unmetered, reaped with the job or
    the orphan sweep — never rendered on a page).

    The Gemini kinds are refused with a clear message when that seam isn't
    configured — better here than a run that fails at its very first step. A
    SHEET is not one of them: it's parsed in code (app/ai/sheets.py), so it
    stays available with every provider switched off.

    `role="reference"` is a photo OF THE COUPLE (8.5d), which is a different
    thing from material about their wedding: it needs the likeness entitlement,
    it must be an image, and it needs consent — which is recorded on the row,
    with who and when, at the moment the file arrives. Consent asserted after
    the fact is not consent, so this is the only place it can be given."""
    require_feature(db, ctx.wedding, "ai_enabled")
    _check_unclaimed_cap(db, ctx.wedding)
    if role not in (SOURCE_ROLE, REFERENCE_ROLE):
        raise HTTPException(status_code=422, detail=f"Unknown upload role {role!r}")
    data = await file.read()
    try:
        kind, ext = validate_ai_media(file.content_type, len(data))
    except UploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if role == REFERENCE_ROLE:
        require_feature(db, ctx.wedding, "ai_likeness_enabled")
        if kind != "image":
            raise HTTPException(
                status_code=422, detail="A photo of you needs to be an image (PNG, JPG or WebP)"
            )
        if not settings.ai_images_available:
            raise HTTPException(
                status_code=422,
                detail="Illustrations aren't available right now, so there's nothing to put you in",
            )
        if not consent:
            raise HTTPException(
                status_code=422,
                detail=(
                    "We can't use photos of you without your say-so — tick the box to "
                    "confirm these are photos of you and that we may store and process "
                    "them to create stylised illustrations"
                ),
            )
    elif kind != "sheet" and not settings.ai_transcribe_enabled:
        raise HTTPException(
            status_code=422,
            detail="Voice notes, photos and PDFs aren't available yet — paste text instead",
        )

    try:
        url = store_ai_input(settings, ctx.wedding.slug, data, ext,
                             file.content_type or "application/octet-stream")
    except UploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    inp = AiInput(
        wedding_id=ctx.wedding.id,
        kind=kind,
        role=role,
        storage_url=url,
        mime=(file.content_type or "").lower(),
        bytes=len(data),
        created_by=ctx.user.sub,
        consent_at=utcnow() if role == REFERENCE_ROLE else None,
        consent_by=ctx.user.sub if role == REFERENCE_ROLE else None,
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
    settings: Settings = Depends(get_ai_settings_effective),
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
    settings: Settings = Depends(get_ai_settings_effective),
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
    settings: Settings = Depends(get_ai_settings_effective),
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


@router.patch("/jobs/{job_id}/proposal", response_model=AiJobAdmin)
def edit_ai_proposal(
    job_id: UUID,
    payload: AiProposalEdit,
    ctx: WeddingCtx = Depends(editor_ctx),
    db: Session = Depends(get_db),
) -> AiJobAdmin:
    """The couple's own edits to the draft, and the illustration style. Free —
    no provider call — and the shortest path from "almost" to "yes"."""
    job = _get_job(db, ctx.wedding, job_id)
    job = edit_proposal(
        db, job,
        story_arc=payload.story_arc,
        style_preset=payload.style_preset,
        style_note=payload.style_note,
        user=ctx.user,
    )
    return _job_admin(db, job)


@router.post("/jobs/{job_id}/illustrate", response_model=AiJobAdmin)
def illustrate_ai_job(
    job_id: UUID,
    payload: AiIllustrateRequest | None = None,
    ctx: WeddingCtx = Depends(editor_ctx),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_ai_settings_effective),
    media_model: GeminiMedia = Depends(get_job_media_model),
) -> AiJobAdmin:
    """Illustrate panels of a settled draft — the stage where images cost money
    (1 credit each, onto the job's hold). Renders at most IMAGES_PER_CALL per
    request, so the client just calls again while panels remain pending."""
    job = _get_job(db, ctx.wedding, job_id)
    job = illustrate(
        db, settings, job,
        targets=payload.targets if payload else None,
        media_model=media_model,
        user=ctx.user,
    )
    return _job_admin(db, job)


@router.post("/jobs/{job_id}/answers", response_model=AiJobAdmin)
def answer_ai_questions(
    job_id: UUID,
    payload: AiAnswersRequest,
    ctx: WeddingCtx = Depends(editor_ctx),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_ai_settings_effective),
    text_model: TextModel = Depends(get_job_text_model),
) -> AiJobAdmin:
    """Answer a guest-list run's open questions and re-extract ONCE (8.5c).
    Free — we're asking because our extraction was uncertain, and the two-round
    cap is what bounds the spend."""
    job = _get_job(db, ctx.wedding, job_id)
    job = answer_questions(
        db, settings, job,
        answers=[a.model_dump() for a in payload.answers],
        text_model=text_model,
        user=ctx.user,
    )
    return _job_admin(db, job)


@router.post("/jobs/{job_id}/references", response_model=AiJobAdmin)
def set_ai_references(
    job_id: UUID,
    payload: AiReferencesRequest,
    ctx: WeddingCtx = Depends(editor_ctx),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_ai_settings_effective),
) -> AiJobAdmin:
    """Put the couple THEMSELVES in the illustrations (8.5d): the consented
    photos this run draws them from. A set — posting an empty list detaches and
    deletes the ones attached, which is how they change their mind. Free; the
    photos only cost anything when a panel is actually rendered."""
    job = _get_job(db, ctx.wedding, job_id)
    job = set_references(db, settings, job, input_ids=payload.input_ids, user=ctx.user)
    return _job_admin(db, job)


@router.get("/styles", response_model=list[AiStyleOption])
def ai_styles(ctx: WeddingCtx = Depends(member_ctx)) -> list[AiStyleOption]:
    """The illustration-style chips. Server-owned: the couple picks a key, the
    platform owns the sentence it stands for (app/ai/styles.py). Rides
    require_wedding like every route here — the authz matrix has no holes in
    it, not even for static data."""
    return [
        AiStyleOption(
            key=s.key,
            label=s.label,
            likeness_blocked=s.key in BLOCKED_LIKENESS_STYLES,
        )
        for s in STYLE_PRESETS.values()
    ]


@router.post("/jobs/{job_id}/apply", response_model=AiApplyResult)
def apply_ai_job(
    job_id: UUID,
    payload: AiApplyRequest | None = None,
    ctx: WeddingCtx = Depends(editor_ctx),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_ai_settings_effective),
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
    settings: Settings = Depends(get_ai_settings_effective),
) -> AiJobAdmin:
    job = _get_job(db, ctx.wedding, job_id)
    return _job_admin(db, cancel_job(db, settings, job))


# --- Credits -------------------------------------------------------------------
@router.get("/credits", response_model=AiCreditsInfo)
def ai_credits(
    ctx: WeddingCtx = Depends(member_ctx),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_ai_settings_effective),
) -> AiCreditsInfo:
    ents = effective_entitlements(db, ctx.wedding)

    def _int(key: str) -> int:
        v = ents.get(key, 0)
        return v if isinstance(v, int) and not isinstance(v, bool) else 0

    # Likeness needs BOTH the plan's opt-in and a process that can actually
    # generate images — a "add photos of us" control that can't render anything
    # is a promise we can't keep.
    likeness = ents.get("ai_likeness_enabled") is True and settings.ai_images_available
    return AiCreditsInfo(
        remaining=credits_remaining(db, ctx.wedding),
        included=_int("ai_credits_included"),
        arc_generations_used=arc_generations_used(db, ctx.wedding),
        arc_generations_included=_int("ai_arc_generations_included"),
        images_available=settings.ai_images_available,
        likeness_available=likeness,
        max_likeness_references=_int("ai_max_likeness_references") if likeness else 0,
    )
