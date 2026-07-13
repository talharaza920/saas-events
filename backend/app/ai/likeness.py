"""Likeness references — illustrations OF the couple (AI_WIZARD_PLAN 8.5d).

Until now the rule was absolute: generated art depicts scenes, objects and
light, and any figures in it are "small, stylised and faceless". 8.5d relaxes
it in exactly one direction — the couple may hand us photographs of THEMSELVES
and get stylised illustrations that look like them — and it is the only feature
in this codebase that ships ahead of its own legal framing (RT, 2026-07-12).
So the mechanism is built to be small, off, and stoppable:

1. **Consent is a property of the file, not of a session.** A reference photo
   is uploaded with `role="reference"` and a ticked box, and the row records
   who ticked it and when (`consent_at` / `consent_by`). No consent recorded,
   no reference — this module simply won't return the input, so no code path
   downstream can pass it to the image model by accident.
2. **Stylised only.** With references attached, the photographic preset is
   refused server-side: a realistic rendering of a real person is the thing the
   deferred legal work is about, and we are not shipping it on a maybe. The
   refusal happens where the style is CHOSEN (a clear 422 the couple can act
   on) and again, silently, where the prompt is composed — the second one is
   the guard that holds if a path is ever added that forgets the first.
3. **Two switches above it.** `ai_likeness_enabled` (entitlement, default
   false) turns it off per plan or platform-wide, and the whole feature needs
   image generation, which `AI_LIVE_CALLS` already governs.

Reference photos are NEVER transcribed (app/ai/jobs._step_transcribe skips
them): a face has nothing to contribute to fact extraction, and running one
through a captioning model would put a description of the couple's bodies into
a prompt for no benefit at all. They ride the job like every other input, which
means the existing sweeps (cancel / expire / apply / reap / purge) delete them
and their stored objects — a likeness reference outlives the run it was for by
zero seconds.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.types import ProviderError
from app.audit_log import record
from app.config import Settings
from app.entitlements import check_limit, effective_entitlements, require_feature
from app.models import AiInput, AiJob, AiJobKind, AiJobStatus, Wedding
from app.obs import log_event
from app.storage import delete_media_object, load_media_bytes, UploadError

logger = logging.getLogger("app.ai")

REFERENCE_ROLE = "reference"
SOURCE_ROLE = "source"

# Photorealism + a real person is precisely the combination whose legal framing
# is deferred, so it is the combination we refuse. Blocking the style (rather
# than the whole feature) keeps the useful half: a watercolour of the two of
# them is not a photograph of them.
BLOCKED_LIKENESS_STYLES = frozenset({"hyper_realistic"})

# What the image model is told to do with the attached photos. It replaces the
# no-recognisable-people guardrail rather than sitting beside it (they
# contradict each other), and it still forbids photorealism in words — the
# style block is the enforcement, this is the instruction.
LIKENESS_DIRECTION = (
    "The attached photographs show the couple. Draw the two figures in the scene "
    "to resemble them — same hair, build and colouring — rendered fully in the "
    "illustration style described above, never as a photograph or photorealistic "
    "portrait. Depict no other identifiable person. No text, lettering or numerals "
    "anywhere in the image."
)

# Watermark disclosure (the UI says this too — it is a property of the images
# themselves, not a UI detail).
SYNTHID_NOTICE = "Generated images carry Google's invisible SynthID watermark."


def likeness_enabled(db: Session, wedding: Wedding) -> bool:
    """Is likeness on for this wedding's plan? A plain bool, not a raise — the
    credits endpoint needs to ANSWER this question, not fail on it."""
    return effective_entitlements(db, wedding).get("ai_likeness_enabled") is True


def max_references(db: Session, wedding: Wedding) -> int:
    cap = effective_entitlements(db, wedding).get("ai_max_likeness_references", 0)
    return cap if isinstance(cap, int) and not isinstance(cap, bool) else 0


def consented_references(inputs) -> list[AiInput]:
    """The reference photos in a set of inputs that we may actually use.

    The consent check lives HERE, in the one predicate every caller goes
    through, rather than at each call site — a photo whose consent was never
    recorded is not a reference, it is just a file we happen to be storing.
    """
    return [
        i
        for i in inputs
        if i.role == REFERENCE_ROLE and i.consent_at is not None and i.storage_url
    ]


def reference_inputs(db: Session, job: AiJob) -> list[AiInput]:
    """The job's usable reference photos, oldest first."""
    rows = db.execute(
        select(AiInput)
        .where(AiInput.job_id == job.id, AiInput.role == REFERENCE_ROLE)
        .order_by(AiInput.created_at)
    ).scalars().all()
    return consented_references(rows)


def load_references(
    settings: Settings, inputs: list[AiInput]
) -> list[tuple[bytes, str]]:
    """Reference photos as (bytes, mime) for the image call. A file we can no
    longer read is skipped, not fatal: a missing reference means a picture
    without their faces in it, which is worse art but not a failed run."""
    out: list[tuple[bytes, str]] = []
    for inp in inputs:
        try:
            out.append((load_media_bytes(settings, inp.storage_url or ""), inp.mime or "image/jpeg"))
        except (UploadError, ProviderError) as exc:
            log_event(logger, "ai.likeness.reference_unreadable",
                      input_id=str(inp.id), error=str(exc)[:120])
    return out


def set_references(
    db: Session,
    settings: Settings,
    job: AiJob,
    *,
    input_ids: list,
    user=None,
) -> AiJob:
    """Set the job's likeness references to exactly these inputs (8.5d).

    A SET, not an append: the couple hand us the photos they want used, and an
    empty list is the way back out — it deletes the ones they'd attached, which
    is the only honest meaning of "actually, don't use pictures of us". Photos
    dropped from the set are deleted here rather than left orphaned in the
    bucket, because a face we no longer have permission to use is not a file we
    should still be holding.

    Raises 403 (feature off — only when ADDING), 404 (unknown / already-claimed /
    unconsented input), 409 (job not open), 422 (wrong kind, no image generation,
    over the cap, or a photographic style already picked). Commits.
    """
    from app.ai.styles import resolve_style  # deferred: styles imports this module

    if job.kind != AiJobKind.STORY_ARC:
        raise HTTPException(
            status_code=422, detail="Only a story run has illustrations to put you in"
        )
    if job.status not in (*AiJobStatus.ACTIVE, AiJobStatus.AWAITING_REVIEW):
        raise HTTPException(status_code=409, detail=f"Job is {job.status}")
    if input_ids:
        # Gated on ADDING only. Taking your photos back out must work even when
        # the plan has just lost the feature — that is the exact moment the
        # illustrate endpoint tells them to do it, and a way out that 403s is not
        # a way out.
        require_feature(db, job.wedding, "ai_likeness_enabled")
    if input_ids and not settings.ai_images_available:
        raise HTTPException(
            status_code=422,
            detail="Illustrations aren't available right now — your story text is unaffected",
        )
    if input_ids:
        check_limit(
            db, job.wedding, "ai_max_likeness_references",
            current_count=0, adding=len(set(input_ids)),
        )

    claimed = {
        i.id: i
        for i in db.execute(
            select(AiInput).where(
                AiInput.job_id == job.id, AiInput.role == REFERENCE_ROLE
            )
        ).scalars()
    }
    wanted: list[AiInput] = []
    for input_id in dict.fromkeys(input_ids):  # de-dupe, keep order
        inp = claimed.get(input_id)
        if inp is None:
            inp = db.execute(
                select(AiInput).where(
                    AiInput.wedding_id == job.wedding_id,  # tenancy: never across weddings
                    AiInput.id == input_id,
                    AiInput.role == REFERENCE_ROLE,
                    AiInput.job_id.is_(None),
                )
            ).scalars().first()
        # Unconsented is indistinguishable from unknown, deliberately: there is
        # no path that reveals "that photo exists but you may not use it".
        if inp is None or inp.consent_at is None:
            raise HTTPException(status_code=404, detail="Photo not found")
        inp.job_id = job.id
        wanted.append(inp)

    options = (job.state or {}).get("options") or {}
    check_style(options.get("style_preset"), has_references=bool(wanted))

    keep = {i.id for i in wanted}
    for input_id, inp in claimed.items():
        if input_id not in keep:
            if inp.storage_url:
                delete_media_object(settings, inp.storage_url)
            db.delete(inp)

    proposal = dict(job.proposal or {})
    if proposal:  # a run still mid-pipeline has none yet; build_proposal will
        proposal["likeness"] = {"references": len(wanted)}
        proposal["style"] = {
            "preset": resolve_style(options, has_references=bool(wanted)).key,
            "note": options.get("style_note") or None,
        }
        job.proposal = proposal  # reassign: JSON columns don't track mutation
    record(
        db, "ai.job.references", user=user, wedding=job.wedding,
        target_type="ai_job", target_id=job.id,
        detail={"references": len(wanted), "consented": len(wanted)},
    )
    log_event(logger, "ai.likeness.references_set", job_id=str(job.id),
              wedding_id=str(job.wedding_id), count=len(wanted))
    db.commit()
    db.refresh(job)
    return job


def check_style(preset: str | None, *, has_references: bool) -> None:
    """The style gate, at the point of choosing. 422 with the way out in the
    message — the couple can have the likeness or the photographic look, and
    they get to decide which, knowing that."""
    if has_references and preset in BLOCKED_LIKENESS_STYLES:
        raise HTTPException(
            status_code=422,
            detail=(
                "While photos of you are attached, illustrations stay stylised — "
                "the photographic look isn't available for pictures of real people. "
                "Pick another style, or remove the photos."
            ),
        )


def safe_style_key(preset: str, *, has_references: bool, fallback: str) -> str:
    """The same gate at the point of RENDERING, where it degrades instead of
    raising: a proposal that somehow carries a blocked style alongside
    references is drawn in the fallback style, not refused and not rendered
    photoreal. Belt to check_style's braces."""
    if has_references and preset in BLOCKED_LIKENESS_STYLES:
        log_event(logger, "ai.likeness.style_downgraded", style=preset, to=fallback)
        return fallback
    return preset
