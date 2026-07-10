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
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.credits import compute_hold, refund_hold
from app.ai.ledger import record_usage
from app.ai.media import MAX_TRANSCRIPT_CHARS, transcribe_input
from app.ai.prompts import render_prompt
from app.ai.resolve import resolve_venue
from app.ai.schemas import DraftArc, ExtractedFacts, GlyphOutput, GroundingReport
from app.ai.types import EFFORT_VALUES, ProviderError, ProviderRefusal, TextModel
from app.audit_log import record
from app.config import Settings
from app.entitlements import check_limit, require_feature
from app.models import (
    AiInput,
    AiJob,
    AiJobKind,
    AiJobStatus,
    PlatformSetting,
    Wedding,
)
from app.obs import log_event
from app.timeutil import as_utc, utcnow

logger = logging.getLogger("app.ai")

# Fixed step order per kind. The `images` fan-out (Nano Banana, one request
# per beat) and the `guests` kind land with the media/image seam — both are
# additive entries here.
STEPS: dict[str, tuple[str, ...]] = {
    AiJobKind.WIZARD: ("transcribe", "extract", "resolve", "draft", "ground"),
    AiJobKind.STORY_ARC: ("transcribe", "extract", "draft", "ground"),
    AiJobKind.GLYPH: ("transcribe", "glyph"),
}

# Stuck `running` jobs past this are expired (hold refunded) by the reap cron.
EXPIRES_AFTER = timedelta(hours=2)

# Platform circuit breaker, editable from the console (Phase 8.4). Checked
# before any provider call — same read-with-defaults pattern as approval.py.
AI_SETTINGS_KEY = "ai"
DEFAULT_AI_SETTINGS = {"kill_switch": False, "daily_cost_ceiling_usd": 25.0}


def get_ai_settings(db: Session) -> dict:
    row = db.get(PlatformSetting, AI_SETTINGS_KEY)
    out = dict(DEFAULT_AI_SETTINGS)
    if row is not None and isinstance(row.value, dict):
        out.update(row.value)
    return out


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
    expected_step: int | None = None,
) -> AiJob:
    """Run exactly one pipeline step. Idempotent per step: a replayed advance
    (expected_step < the current step) is a no-op returning current state;
    an advance from the future is a 409."""
    if job.status == AiJobStatus.AWAITING_REVIEW:
        return job  # already done — replays are harmless
    if job.status not in AiJobStatus.ACTIVE:
        raise HTTPException(status_code=409, detail=f"Job is {job.status}")
    if expected_step is not None:
        if expected_step < job.step:
            return job  # replay of a step that already ran
        if expected_step > job.step:
            raise HTTPException(status_code=409, detail=f"Job is on step {job.step}")
    if job.expires_at is not None and as_utc(job.expires_at) < utcnow():
        _terminate(db, job, AiJobStatus.EXPIRED, "run took too long and expired")
        db.commit()
        return job
    if get_ai_settings(db)["kill_switch"]:
        raise HTTPException(
            status_code=503, detail="AI assistance is temporarily paused — try again later"
        )

    job.status = AiJobStatus.RUNNING
    step_name = STEPS[job.kind][job.step]
    try:
        _run_step(db, settings, job, step_name, text_model)
    except ProviderRefusal as exc:
        _terminate(db, job, AiJobStatus.FAILED, f"the model declined this request: {exc}")
        db.commit()
        return job
    except ProviderError as exc:
        _terminate(db, job, AiJobStatus.FAILED, str(exc))
        db.commit()
        return job

    job.step += 1
    if job.step >= job.steps_total:
        job.proposal = _build_proposal(job)
        job.status = AiJobStatus.AWAITING_REVIEW
        log_event(logger, "ai.job.review", job_id=str(job.id), kind=job.kind,
                  wedding_id=str(job.wedding_id))
    db.commit()
    db.refresh(job)
    return job


def cancel_job(db: Session, job: AiJob) -> AiJob:
    if job.status not in (*AiJobStatus.ACTIVE, AiJobStatus.AWAITING_REVIEW):
        raise HTTPException(status_code=409, detail=f"Job is {job.status}")
    _terminate(db, job, AiJobStatus.CANCELLED, None)
    db.commit()
    return job


def _terminate(db: Session, job: AiJob, status: str, error: str | None) -> None:
    """Move to a terminal status: refund the hold (a failed/cancelled/expired
    run never costs the couple) and delete raw inputs (transcripts and all —
    consent-based retention arrives with the inputs API in 8.4)."""
    job.status = status
    job.error = error
    refund_hold(job)
    for inp in db.execute(select(AiInput).where(AiInput.job_id == job.id)).scalars():
        db.delete(inp)
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
# ---------------------------------------------------------------------------
def _run_step(
    db: Session, settings: Settings, job: AiJob, step_name: str, text_model: TextModel
) -> None:
    state = dict(job.state or {})
    runner = {
        "transcribe": _step_transcribe,
        "extract": _step_extract,
        "resolve": _step_resolve,
        "draft": _step_draft,
        "ground": _step_ground,
        "glyph": _step_glyph,
    }[step_name]
    runner(db, settings, job, state, text_model)
    job.state = state  # reassign: JSON columns don't track in-place mutation


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


def _step_transcribe(db, settings, job, state, text_model) -> None:
    """Media → text (no text LLM involved). The joined, bounded transcript is
    the ONLY form of the submission any later step sees."""
    inputs = db.execute(
        select(AiInput).where(AiInput.job_id == job.id).order_by(AiInput.created_at)
    ).scalars().all()
    parts = []
    for inp in inputs:
        transcript = transcribe_input(settings, inp)
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
    # UNTRUSTED until the 8.3 allowlist-rebuild sanitiser runs at apply time.
    state["glyph"] = {**glyph.model_dump(), "sanitised": False}


# ---------------------------------------------------------------------------
# Proposal — the reviewable diff. Never auto-applied; the 8.4 apply endpoint
# writes only its allowlisted paths and re-checks entitlements at apply time.
# ---------------------------------------------------------------------------
def _build_proposal(job: AiJob) -> dict:
    state = job.state or {}
    proposal: dict = {"kind": job.kind, "source": "ai"}
    if job.kind in (AiJobKind.WIZARD, AiJobKind.STORY_ARC):
        proposal["story_arc"] = state.get("draft")
        proposal["grounding"] = state.get("grounding")
    if job.kind == AiJobKind.WIZARD:
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
