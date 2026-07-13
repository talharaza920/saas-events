"""AI job state machine (AI_WIZARD_PLAN Phase 8.1 "Pipeline").

The wizard is a WORKFLOW, not an agent: the control flow below is fixed, each
step's output is schema-validated, and the order never varies. Every step is
one short call driven by the client hitting /advance — no long request, no
hosted loop, and every provider call runs inside our tenancy/authz/audit
seams.

    create_job ─▶ queued ─(advance)▶ running ─(step…step)▶ awaiting_review
                     │                  │
                     └── cancel ──▶ cancelled (refund)     failed (refund)
                                                           expired (refund)

The model proposes; code disposes: the finished job carries a `proposal`
blob a human reviews and applies (apply endpoint = Phase 8.4, behind its own
allowlist). Nothing here writes wedding content.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.credits import compute_hold, refund_hold
from app.ai.ledger import cost_usd_today, record_usage
from app.ai.media import (
    GeminiMedia,
    MAX_TRANSCRIPT_CHARS,
    get_media_model,
    sniff_image_mime,
    transcribe_input,
)
from app.ai.prompts import render_prompt
from app.ai.resolve import resolve_venue
from app.ai.schemas import (
    DraftArc,
    ExtractedFacts,
    GlyphOutput,
    GroundingReport,
    GuestLines,
)
from app.ai.svg import SvgSanitizationError, sanitize_glyph
from app.ai.types import EFFORT_VALUES, ProviderError, ProviderRefusal, TextModel
from app.audit_log import record
from app.config import Settings
from app.entitlements import check_limit, check_storage, effective_entitlements, require_feature
from app.guest_import import build_guests
from app.models import (
    AiInput,
    AiJob,
    AiJobKind,
    AiJobStatus,
    PlatformSetting,
    Wedding,
)
from app.obs import log_event
from app.storage import delete_media_object, prepare_image, store_image, UploadError
from app.timeutil import as_utc, utcnow

logger = logging.getLogger("app.ai")

# Fixed step order per kind. `images` is the Nano Banana fan-out (one request
# per beat) — it processes a couple of beats per /advance call and repeats
# until every beat is done, so no single HTTP request runs long.
STEPS: dict[str, tuple[str, ...]] = {
    AiJobKind.DETAILS: ("transcribe", "extract", "resolve"),
    AiJobKind.STORY_ARC: ("transcribe", "extract", "draft", "images", "ground"),
    AiJobKind.GLYPH: ("transcribe", "glyph"),
    AiJobKind.GUESTS: ("transcribe", "guests"),
}

# How many beat images one /advance call generates (each is ~5–15 s at the
# provider — two keeps the request comfortably under serverless timeouts).
IMAGES_PER_ADVANCE = 2

# Stuck `running` jobs past this are expired (hold refunded) by the reap cron.
EXPIRES_AFTER = timedelta(hours=2)
# Inputs uploaded but never claimed by a job are raw PII — the reap cron
# deletes them once they're clearly abandoned.
ORPHAN_INPUT_TTL = timedelta(hours=24)

# Platform circuit breaker, editable from the console (Phase 8.4). Checked
# before any provider call — same read-with-defaults pattern as approval.py.
AI_SETTINGS_KEY = "ai"
# The circuit breaker, plus the platform-wide text-model choice. Every text_*
# value is "" by default, meaning "use the env bootstrap" — the console can
# override the model without a redeploy (ids churn), and clearing a field puts
# it back rather than leaving a stale pin. See ai/runtime.effective_settings.
DEFAULT_AI_SETTINGS = {
    "kill_switch": False,
    "daily_cost_ceiling_usd": 25.0,
    "text_provider": "",
    "text_model": "",
    "text_effort": "",
}


def get_ai_settings(db: Session) -> dict:
    row = db.get(PlatformSetting, AI_SETTINGS_KEY)
    out = dict(DEFAULT_AI_SETTINGS)
    if row is not None and isinstance(row.value, dict):
        out.update(row.value)
    return out


def set_ai_settings(db: Session, values: dict) -> dict:
    """Stage (caller commits) the circuit-breaker settings from the platform
    console. Only the known keys are stored — a stray key in the payload can't
    grow the blob into config nothing reads."""
    merged = dict(DEFAULT_AI_SETTINGS)
    for key in DEFAULT_AI_SETTINGS:
        if key in values:
            merged[key] = values[key]
    row = db.get(PlatformSetting, AI_SETTINGS_KEY)
    if row is None:
        db.add(PlatformSetting(key=AI_SETTINGS_KEY, value=merged))
    else:
        row.value = merged
    return merged


def check_circuit_breaker(
    db: Session,
    *,
    ceiling_detail: str = "AI is at capacity right now — try again later",
) -> None:
    """The platform circuit breaker (guardrail 6), checked before ANY provider
    call — advance and regenerate both. Kill switch → 503; daily cost ceiling
    → 503 + Retry-After with no job-state change, so in-flight runs queue
    rather than fail (a platform budget event never burns held credits)."""
    ai_settings = get_ai_settings(db)
    if ai_settings["kill_switch"]:
        raise HTTPException(
            status_code=503, detail="AI assistance is temporarily paused — try again later"
        )
    ceiling = ai_settings.get("daily_cost_ceiling_usd")
    if isinstance(ceiling, (int, float)) and not isinstance(ceiling, bool) and ceiling > 0:
        if cost_usd_today(db) >= ceiling:
            log_event(logger, "ai.ceiling.tripped", ceiling_usd=ceiling)
            raise HTTPException(
                status_code=503,
                detail=ceiling_detail,
                headers={"Retry-After": "1800"},
            )


def _dump(obj: dict) -> str:
    # sort_keys so identical state renders identical prompt bytes (caching).
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
def create_job(
    db: Session,
    settings: Settings,
    wedding: Wedding,
    *,
    kind: str,
    input_ids: list | None = None,
    created_by: str | None = None,
    idempotency_key: str | None = None,
    options: dict | None = None,
) -> AiJob:
    """Create a queued job. Raises 403 (feature/credits), 404 (bad inputs),
    409 (a run already active), 503 (kill switch)."""
    if kind not in STEPS:
        raise HTTPException(status_code=422, detail=f"Unknown AI job kind {kind!r}")
    require_feature(db, wedding, "ai_enabled")
    if get_ai_settings(db)["kill_switch"]:
        raise HTTPException(
            status_code=503, detail="AI assistance is temporarily paused — try again later"
        )

    # A retried POST with the same key returns the same job, never a second charge.
    if idempotency_key:
        existing = db.execute(
            select(AiJob).where(
                AiJob.wedding_id == wedding.id,
                AiJob.idempotency_key == idempotency_key,
            )
        ).scalars().first()
        if existing is not None:
            return existing

    # Friendly-path check BEFORE the credit math (an active run shouldn't
    # surface as "out of credits"); the partial unique index below stays the
    # backstop that actually holds under concurrent instances.
    active = db.execute(
        select(AiJob).where(
            AiJob.wedding_id == wedding.id, AiJob.status.in_(AiJobStatus.ACTIVE)
        )
    ).scalars().first()
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail="An AI run is already in progress for this wedding — wait for it to finish or cancel it",
        )

    inputs: list[AiInput] = []
    if input_ids:
        check_limit(db, wedding, "ai_max_inputs_per_job", current_count=0, adding=len(input_ids))
        inputs = db.execute(
            select(AiInput).where(
                AiInput.wedding_id == wedding.id,  # tenancy: never claim across weddings
                AiInput.id.in_(input_ids),
                AiInput.job_id.is_(None),
            )
        ).scalars().all()
        if len(inputs) != len(set(input_ids)):
            raise HTTPException(status_code=404, detail="Input not found")

    hold = compute_hold(db, wedding, kind)
    job = AiJob(
        wedding_id=wedding.id,
        kind=kind,
        status=AiJobStatus.QUEUED,
        steps_total=len(STEPS[kind]),
        state={"options": _bounded_options(options)},
        credits_held=hold,
        idempotency_key=idempotency_key,
        created_by=created_by,
        expires_at=utcnow() + EXPIRES_AFTER,
    )
    db.add(job)
    try:
        db.flush()  # surfaces the one-active-job partial unique index NOW
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An AI run is already in progress for this wedding — wait for it to finish or cancel it",
        )
    for inp in inputs:
        inp.job_id = job.id
    record(db, "ai.job.create", wedding=wedding, target_type="ai_job", target_id=job.id,
           detail={"kind": kind, "credits_held": hold, "inputs": len(inputs)})
    db.commit()
    db.refresh(job)
    return job


def advance_job(
    db: Session,
    settings: Settings,
    job: AiJob,
    *,
    text_model: TextModel,
    media_model: GeminiMedia | None = None,
    expected_step: int | None = None,
) -> AiJob:
    """Run exactly one pipeline step. Idempotent per step: a replayed advance
    (expected_step < the current step) is a no-op returning current state;
    an advance from the future is a 409. The `images` fan-out may leave the
    job ON its step (partial progress saved in state) — the client just keeps
    advancing until awaiting_review."""
    if job.status == AiJobStatus.AWAITING_REVIEW:
        return job  # already done — replays are harmless
    if job.status not in AiJobStatus.ACTIVE:
        raise HTTPException(status_code=409, detail=f"Job is {job.status}")
    if job.kind not in STEPS:
        # A row from before a kind was retired (8.5a demoted `wizard`). Retire
        # it cleanly with a refund rather than KeyError-ing on its step list.
        _terminate(db, settings, job, AiJobStatus.EXPIRED,
                   "this run is from an older version of the assistant — start a new one")
        db.commit()
        return job
    if expected_step is not None:
        if expected_step < job.step:
            return job  # replay of a step that already ran
        if expected_step > job.step:
            raise HTTPException(status_code=409, detail=f"Job is on step {job.step}")
    if job.expires_at is not None and as_utc(job.expires_at) < utcnow():
        _terminate(db, settings, job, AiJobStatus.EXPIRED, "run took too long and expired")
        db.commit()
        return job
    # Tripping the ceiling QUEUES the job rather than failing it — no state
    # change here, the client retries after the window (and if it never
    # resumes, the reap cron expires it with a full refund).
    check_circuit_breaker(
        db, ceiling_detail="AI is at capacity right now — your run is saved and will continue later"
    )

    job.status = AiJobStatus.RUNNING
    step_name = STEPS[job.kind][job.step]
    try:
        step_done = _run_step(db, settings, job, step_name, text_model, media_model)
    except ProviderRefusal as exc:
        _terminate(db, settings, job, AiJobStatus.FAILED,
                   f"the model declined this request: {exc}")
        db.commit()
        return job
    except ProviderError as exc:
        _terminate(db, settings, job, AiJobStatus.FAILED, str(exc))
        db.commit()
        return job

    if step_done is not False:  # False = repeat me (images fan-out mid-flight)
        job.step += 1
    if job.step >= job.steps_total:
        job.proposal = _build_proposal(job)
        job.status = AiJobStatus.AWAITING_REVIEW
        log_event(logger, "ai.job.review", job_id=str(job.id), kind=job.kind,
                  wedding_id=str(job.wedding_id))
    db.commit()
    db.refresh(job)
    return job


def reap_expired_jobs(db: Session, settings: Settings, *, now: datetime | None = None) -> dict:
    """The reap-ai-jobs cron body (plan 8.3 §9): move stuck queued/running
    jobs past their `expires_at` to `expired` — hold refunded, inputs swept —
    and delete orphan inputs (uploaded but never claimed by any job) older
    than ORPHAN_INPUT_TTL, since raw submissions are PII that must not linger.
    Timestamp compares happen in Python (as_utc) so SQLite's naive storage
    can't skew them, same as purge.py. Commits once at the end.
    """
    now = now or utcnow()
    expired: list[dict] = []
    active = db.execute(
        select(AiJob).where(AiJob.status.in_(AiJobStatus.ACTIVE))
    ).scalars().all()
    for job in active:
        if job.expires_at is not None and as_utc(job.expires_at) < now:
            _terminate(db, settings, job, AiJobStatus.EXPIRED, "run took too long and expired")
            expired.append(
                {"job_id": str(job.id), "wedding_id": str(job.wedding_id), "kind": job.kind}
            )

    orphan_cutoff = now - ORPHAN_INPUT_TTL
    orphans_swept = 0
    for inp in db.execute(select(AiInput).where(AiInput.job_id.is_(None))).scalars():
        if inp.created_at is not None and as_utc(inp.created_at) < orphan_cutoff:
            _delete_input(db, settings, inp)
            orphans_swept += 1

    if expired or orphans_swept:
        db.commit()
    return {"expired": expired, "orphan_inputs_swept": orphans_swept}


def cancel_job(db: Session, settings: Settings, job: AiJob) -> AiJob:
    if job.status not in (*AiJobStatus.ACTIVE, AiJobStatus.AWAITING_REVIEW):
        raise HTTPException(status_code=409, detail=f"Job is {job.status}")
    _terminate(db, settings, job, AiJobStatus.CANCELLED, None)
    db.commit()
    return job


def _delete_input(db: Session, settings: Settings, inp: AiInput) -> None:
    """Delete an input row AND its stored media object (raw PII — the row
    going away must take the voice note in the bucket with it)."""
    if inp.storage_url:
        delete_media_object(settings, inp.storage_url)
    db.delete(inp)


def sweep_generated_images(
    db: Session, settings: Settings, job: AiJob, *, keep: set[str]
) -> None:
    """Delete generated beat images not in `keep` (terminated run: all of
    them; applied run: everything the final proposal didn't reference) and
    give the bytes back to the wedding's storage counter. Deletion is
    best-effort; the counter only moves for URLs we actually tracked."""
    state = job.state or {}
    image_bytes: dict = state.get("image_bytes") or {}
    freed = 0
    for url, size in image_bytes.items():
        if url in keep:
            continue
        delete_media_object(settings, url)
        if isinstance(size, int) and not isinstance(size, bool):
            freed += size
    if freed and job.wedding is not None:
        job.wedding.storage_bytes_used = max((job.wedding.storage_bytes_used or 0) - freed, 0)
    # Only the kept URLs remain accounted to this job.
    state = dict(state)
    state["image_bytes"] = {u: b for u, b in image_bytes.items() if u in keep}
    job.state = state


def _terminate(db: Session, settings: Settings, job: AiJob, status: str, error: str | None) -> None:
    """Move to a terminal status: refund the hold (a failed/cancelled/expired
    run never costs the couple), delete raw inputs (transcripts, and their
    stored media objects — consent-based retention is a later refinement) and
    sweep any generated beat images that will now never be applied."""
    job.status = status
    job.error = error
    refund_hold(job)
    for inp in db.execute(select(AiInput).where(AiInput.job_id == job.id)).scalars():
        _delete_input(db, settings, inp)
    sweep_generated_images(db, settings, job, keep=set())
    log_event(logger, "ai.job.terminal", job_id=str(job.id), status=status,
              wedding_id=str(job.wedding_id), error=(error or "")[:200] or None)


def _bounded_options(options: dict | None) -> dict:
    """The only owner-supplied knobs a job accepts, clamped."""
    options = options or {}
    out: dict = {}
    beat_count = options.get("beat_count")
    if isinstance(beat_count, int) and not isinstance(beat_count, bool):
        out["beat_count"] = min(max(beat_count, 2), 8)
    tone = options.get("tone")
    if isinstance(tone, str) and tone.strip():
        out["tone"] = tone.strip()[:120]
    return out


# ---------------------------------------------------------------------------
# Steps — each mutates job.state and stages ledger rows; caller commits.
# A runner returning False means "not finished, run me again" (the images
# fan-out); anything else advances to the next step.
# ---------------------------------------------------------------------------
def _run_step(
    db: Session,
    settings: Settings,
    job: AiJob,
    step_name: str,
    text_model: TextModel,
    media_model: GeminiMedia | None = None,
) -> bool | None:
    state = dict(job.state or {})
    runner = {
        "transcribe": _step_transcribe,
        "extract": _step_extract,
        "resolve": _step_resolve,
        "draft": _step_draft,
        "images": _step_images,
        "ground": _step_ground,
        "glyph": _step_glyph,
        "guests": _step_guests,
    }[step_name]
    if step_name in ("transcribe", "images"):
        done = runner(db, settings, job, state, media_model)
    else:
        done = runner(db, settings, job, state, text_model)
    job.state = state  # reassign: JSON columns don't track in-place mutation
    return done


def _generate(
    db: Session,
    settings: Settings,
    job: AiJob,
    state: dict,
    text_model: TextModel,
    *,
    key: str,
    user: str,
    schema,
    variables: dict | None = None,
    ledger_kind: str,
):
    prompt = render_prompt(
        db, key, provider=settings.ai_text_provider, user=user, variables=variables
    )
    effort = prompt.effort if prompt.effort in EFFORT_VALUES else settings.ai_text_effort
    if effort not in EFFORT_VALUES:
        effort = "high"
    completion = text_model.generate_structured(prompt, schema, effort=effort)
    record_usage(db, wedding_id=job.wedding_id, job_id=job.id,
                 kind=ledger_kind, usage=completion.usage)
    state.setdefault("generation", {})[ledger_kind] = {
        "prompt_key": prompt.key, "prompt_version": prompt.version,
        "provider": completion.usage.provider, "model": completion.usage.model,
    }
    return completion.output


def _step_transcribe(db, settings, job, state, media_model) -> None:
    """Media → text (no text LLM involved; media kinds go through the Gemini
    seam and their calls are ledgered). The joined, bounded transcript is the
    ONLY form of the submission any later step sees."""
    inputs = db.execute(
        select(AiInput).where(AiInput.job_id == job.id).order_by(AiInput.created_at)
    ).scalars().all()
    parts = []
    for inp in inputs:
        transcript, usage = transcribe_input(settings, inp, media=media_model)
        if usage is not None:
            record_usage(db, wedding_id=job.wedding_id, job_id=job.id,
                         kind="transcribe", usage=usage)
        inp.transcript = transcript
        parts.append(transcript)
    state["submission"] = "\n\n".join(p for p in parts if p)[:MAX_TRANSCRIPT_CHARS]
    if not state["submission"] and job.kind != AiJobKind.GLYPH:
        raise ProviderError("Nothing to work from — add some text about your wedding first")


def _step_extract(db, settings, job, state, text_model) -> None:
    facts = _generate(
        db, settings, job, state, text_model,
        key="extract.system",
        user=f"<submission>\n{state.get('submission', '')}\n</submission>",
        schema=ExtractedFacts,
        ledger_kind="extract",
    )
    state["facts"] = facts.model_dump()


def _step_resolve(db, settings, job, state, text_model) -> None:
    """Plain code, no model — the address comes from Places or not at all."""
    facts = state.get("facts") or {}
    venue = (facts.get("venue_name") or {}).get("value")
    city = (facts.get("city") or {}).get("value")
    resolved = resolve_venue(settings, venue, city=city) if venue else None
    state["venue"] = resolved.as_dict() if resolved else None


def _step_draft(db, settings, job, state, text_model) -> None:
    options = state.get("options") or {}
    tone = options.get("tone") or "warm, specific, unsentimental"
    user = (
        f"<submission>\n{state.get('submission', '')}\n</submission>\n"
        f"<facts>\n{_dump(state.get('facts') or {})}\n</facts>\n"
        f"<style>\n{tone}\n</style>"
    )
    draft = _generate(
        db, settings, job, state, text_model,
        key="draft_arc.system", user=user, schema=DraftArc,
        variables={"beat_count": options.get("beat_count", 4)},
        ledger_kind="draft",
    )
    state["draft"] = draft.model_dump()


def _step_images(db, settings, job, state, media_model) -> bool:
    """The Nano Banana fan-out (plan step 5): one image request per beat,
    IMAGES_PER_ADVANCE per call — returns False while beats remain so the
    client simply advances again. Degrades, never blocks: no Gemini key, a
    content-filter refusal on one scene, or a full storage quota all leave
    the affected beats text-only (they render as feathered panels) rather
    than failing a run the couple already paid a hold for."""
    beats = (state.get("draft") or {}).get("beats") or []
    if not settings.ai_images_enabled:
        if beats:
            state["images_skipped"] = "illustrations are turned off"
        return True
    cap = effective_entitlements(db, job.wedding).get("ai_max_images_per_arc", 0)
    if not isinstance(cap, int) or isinstance(cap, bool):
        cap = 0
    images = dict(state.get("images") or {})
    refused = dict(state.get("images_refused") or {})
    image_bytes = dict(state.get("image_bytes") or {})
    pending = [
        i for i in range(min(len(beats), cap))
        if str(i) not in images and str(i) not in refused
    ]

    media = media_model or get_media_model(settings)
    for i in pending[:IMAGES_PER_ADVANCE]:
        prompt = (beats[i].get("image_prompt") or "").strip()
        if not prompt:
            refused[str(i)] = "no scene description"
            continue
        try:
            data, usage = media.generate_image(prompt)
        except ProviderRefusal as exc:
            # This scene only — the run continues, the beat stays text-only.
            log_event(logger, "ai.image.refused", job_id=str(job.id), beat=i)
            refused[str(i)] = str(exc)[:200]
            continue
        record_usage(db, wedding_id=job.wedding_id, job_id=job.id,
                     kind="image", usage=usage, images=1)
        mime = sniff_image_mime(data)
        try:
            blob, ext = prepare_image(data, mime)
        except UploadError as exc:
            refused[str(i)] = f"unusable image ({exc})"
            continue
        try:
            check_storage(db, job.wedding, adding_bytes=len(blob))
        except HTTPException:
            state["images_skipped"] = "this wedding's storage is full"
            state["images"], state["images_refused"] = images, refused
            state["image_bytes"] = image_bytes
            return True  # keep what we have; stop generating
        url = store_image(settings, job.wedding.slug, blob, ext, mime)
        job.wedding.storage_bytes_used = (job.wedding.storage_bytes_used or 0) + len(blob)
        images[str(i)] = url
        image_bytes[url] = len(blob)

    state["images"], state["images_refused"] = images, refused
    state["image_bytes"] = image_bytes
    return len(pending) <= IMAGES_PER_ADVANCE


def _step_guests(db, settings, job, state, text_model) -> None:
    """Guest extraction: the model returns each entry EXACTLY as written
    (names + raw "+1"/kid markers); the deterministic guest_import parser then
    collapses companions and assigns tiers IN CODE. The model never sees,
    names, or suggests a tier — that is guardrail 1, not a style choice."""
    lines = _generate(
        db, settings, job, state, text_model,
        key="extract_guests.system",
        user=f"<submission>\n{state.get('submission', '')}\n</submission>",
        schema=GuestLines,
        ledger_kind="extract",
    )
    drafts, unresolved = build_guests([{"name": line} for line in lines.lines])
    state["guests"] = [
        {
            "name": d.name,
            "invite_tier": d.invite_tier.value,  # computed by infer_tier, in code
            "adult_companions": d.adult_companions,
            "child_companions": d.child_companions,
        }
        for d in drafts
    ]
    state["guests_unresolved"] = [u["name"] for u in unresolved]
    if not state["guests"]:
        raise ProviderError(
            "No guest names found in what you shared — paste the list itself and try again"
        )


def _step_ground(db, settings, job, state, text_model) -> None:
    """The one genuinely agentic addition: a second call that reads SOURCE and
    DRAFT side by side and flags every unsupported claim. Hallucinating a
    wedding venue is the worst thing this feature can do; this catches it
    before a human ever sees the arc as 'done'."""
    user = (
        f"SOURCE:\n{state.get('submission', '')}\n\n"
        f"DRAFT:\n{_dump(state.get('draft') or {})}"
    )
    report = _generate(
        db, settings, job, state, text_model,
        key="ground.system", user=user, schema=GroundingReport,
        ledger_kind="ground",
    )
    state["grounding"] = report.model_dump()


def _step_glyph(db, settings, job, state, text_model) -> None:
    glyph = _generate(
        db, settings, job, state, text_model,
        key="glyph.system",
        user=f"<submission>\n{state.get('submission', '')}\n</submission>",
        schema=GlyphOutput,
        ledger_kind="glyph",
    )
    # Allowlist-rebuild NOW, so the review UI never renders raw model output.
    # An unusable mark is a failed generation (refunded), never rendered anyway.
    try:
        children = sanitize_glyph(glyph.svg_children)
    except SvgSanitizationError as exc:
        raise ProviderError(f"the generated mark wasn't usable ({exc}) — try again")
    state["glyph"] = {"svg_children": children, "concept": glyph.concept, "sanitised": True}


# ---------------------------------------------------------------------------
# Proposal — the reviewable diff. Never auto-applied; the 8.4 apply endpoint
# writes only its allowlisted paths and re-checks entitlements at apply time.
# ---------------------------------------------------------------------------
def _build_proposal(job: AiJob) -> dict:
    state = job.state or {}
    proposal: dict = {"kind": job.kind, "source": "ai"}
    if job.kind == AiJobKind.STORY_ARC:
        proposal["story_arc"] = state.get("draft")
        proposal["grounding"] = state.get("grounding")
        # Generated beat art rides NEXT TO the draft (never inside it — the
        # draft revalidates through DraftArc at apply, whose schema the model
        # owns; an `image` field there would invite the model to fill it).
        proposal["beat_images"] = state.get("images") or {}
    if job.kind == AiJobKind.GUESTS:
        proposal["guests"] = state.get("guests") or []
        proposal["guests_unresolved"] = state.get("guests_unresolved") or []
    if job.kind == AiJobKind.DETAILS:
        facts = state.get("facts") or {}
        details: dict = {}
        for field, target in (("event_date", "date"), ("event_time", "time")):
            fact = facts.get(field)
            if fact:
                details[target] = {"value": fact["value"], "supported_by": fact["supported_by"]}
        venue = state.get("venue")
        venue_fact = facts.get("venue_name")
        if venue:  # resolved: real address from Places
            details["venue"] = venue
        elif venue_fact:  # unresolved: the couple's own words, nothing invented
            details["venue"] = {"name": venue_fact["value"], "address": None}
        proposal["event_details"] = details
        if facts.get("couple_names"):
            proposal["couple_names"] = facts["couple_names"]["value"]
    if job.kind == AiJobKind.GLYPH:
        proposal["glyph"] = state.get("glyph")
    return proposal
