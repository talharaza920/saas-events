"""AI job pipeline (AI_WIZARD_PLAN Phase 8.1b).

Runs the whole state machine offline through the fake adapter: create (gates:
feature flag, kill switch, credits/free-arc, one-active, idempotency, tenancy
on inputs) → advance step-by-step → awaiting_review with a proposal — plus
every terminal path (refusal, provider error, cancel, expiry) refunding the
hold and sweeping inputs.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.ai.jobs import (
    AI_SETTINGS_KEY,
    advance_job,
    cancel_job,
    create_job,
)
from app.ai.providers.fake import FakeTextModel
from app.ai.types import ProviderRefusal
from app.config import Settings
from app.models import (
    AiInput,
    AiJob,
    AiUsageLedger,
    AuditLog,
    Plan,
    PlatformSetting,
)
from app.timeutil import utcnow
from tests.helpers import DEV_TOKEN, make_wedding

AI_ENTITLEMENTS = {
    "ai_enabled": True,
    "ai_credits_included": 0,
    "ai_arc_generations_included": 1,
    "ai_max_inputs_per_job": 12,
}


def _settings(**overrides) -> Settings:
    base = dict(
        environment="development", dev_admin_token=DEV_TOKEN, ai_text_provider="fake"
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _enable_ai(db, **entitlement_overrides) -> None:
    ents = dict(AI_ENTITLEMENTS)
    ents.update(entitlement_overrides)
    db.add(Plan(name="ai-test-plan", is_default=True, entitlements=ents))
    db.commit()


def _add_text_input(db, wedding, text: str) -> AiInput:
    inp = AiInput(wedding_id=wedding.id, kind="text", text_content=text)
    db.add(inp)
    db.commit()
    return inp


def _fake() -> FakeTextModel:
    return FakeTextModel(responses={
        "extract.system": {
            "couple_names": {"value": "Alex & Sam", "supported_by": "we're Alex and Sam"},
            "venue_name": {"value": "Fern Hall", "supported_by": "at Fern Hall"},
            "event_date": {"value": "2027-05-01", "supported_by": "on May 1st, 2027"},
        },
        "draft_arc.system": {
            "heading": "Alex & Sam",
            "beats": [
                {"text": "They met **at a bus stop**.", "image_prompt": "a rainy bus stop, warm light"},
                {"text": "Sam moved cities; Alex followed.", "image_prompt": "two suitcases by a door"},
            ],
            "climax": "And now — join them.",
        },
        "ground.system": {"unsupported": [], "all_supported": True},
        "glyph.system": {"svg_children": "<circle cx='50' cy='50' r='40'/>", "concept": "a ring"},
    })


def _run_to_review(db, settings, job, fake) -> AiJob:
    for _ in range(job.steps_total):
        job = advance_job(db, settings, job, text_model=fake)
        if job.status != "running" and job.status not in ("queued",):
            break
    return job


# ---------------------------------------------------------------------------
# Creation gates
# ---------------------------------------------------------------------------
def test_create_requires_ai_enabled(db_session):
    w = make_wedding(db_session, "wed-gate")
    with pytest.raises(HTTPException) as exc:
        create_job(db_session, _settings(), w, kind="wizard")
    assert exc.value.status_code == 403
    assert "AI assistance" in exc.value.detail


def test_create_respects_kill_switch(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-kill")
    db_session.add(PlatformSetting(key=AI_SETTINGS_KEY, value={"kill_switch": True}))
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        create_job(db_session, _settings(), w, kind="wizard")
    assert exc.value.status_code == 503


def test_one_active_job_and_idempotency(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-active")
    job = create_job(db_session, _settings(), w, kind="wizard", idempotency_key="k1")
    assert (job.status, job.steps_total, job.credits_held) == ("queued", 5, 0)  # free arc

    # Same key → same job, no second charge; new key → 409 (DB partial index).
    assert create_job(db_session, _settings(), w, kind="wizard", idempotency_key="k1").id == job.id
    with pytest.raises(HTTPException) as exc:
        create_job(db_session, _settings(), w, kind="wizard", idempotency_key="k2")
    assert exc.value.status_code == 409

    # Audit trail rode the creation commit.
    assert db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai.job.create")
    ).scalars().first() is not None


def test_credits_free_arc_then_charge_then_refuse(db_session):
    _enable_ai(db_session, ai_credits_included=5, ai_arc_generations_included=1)
    w = make_wedding(db_session, "wed-credits")
    s = _settings()

    first = create_job(db_session, s, w, kind="wizard")
    assert first.credits_held == 0  # the included free arc
    cancel_job(db_session, first)  # cancelled = refunded AND frees the allowance…

    free_again = create_job(db_session, s, w, kind="wizard")
    assert free_again.credits_held == 0  # …so the next run is still free
    free_again.status = "applied"  # simulate the couple applying it
    db_session.commit()

    charged = create_job(db_session, s, w, kind="story_arc")
    assert charged.credits_held == 3  # allowance spent → story_arc costs 3
    charged.status = "applied"
    db_session.commit()

    with pytest.raises(HTTPException) as exc:  # 5 - 3 = 2 left, wizard costs 5
        create_job(db_session, s, w, kind="wizard")
    assert exc.value.status_code == 403 and "AI credits" in exc.value.detail


def test_inputs_are_tenant_scoped(db_session):
    _enable_ai(db_session)
    mine = make_wedding(db_session, "wed-mine")
    other = make_wedding(db_session, "wed-other")
    foreign_input = _add_text_input(db_session, other, "someone else's wedding")
    with pytest.raises(HTTPException) as exc:
        create_job(db_session, _settings(), mine, kind="wizard", input_ids=[foreign_input.id])
    assert exc.value.status_code == 404  # existence hidden, never claimed


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------
def test_wizard_runs_to_review_with_proposal(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-run")
    s = _settings()
    inp = _add_text_input(
        db_session, w,
        "We're Alex and Sam, getting married at Fern Hall on May 1st, 2027.",
    )
    fake = _fake()
    job = create_job(db_session, s, w, kind="wizard", input_ids=[inp.id])

    job = _run_to_review(db_session, s, job, fake)

    assert job.status == "awaiting_review"
    assert job.step == job.steps_total == 5
    # Transcribe: media→text before any model call; the input keeps its transcript.
    db_session.refresh(inp)
    assert "Fern Hall" in inp.transcript
    # Three text-LLM calls (extract/draft/ground) — resolve is code, no model.
    assert [c.prompt.key for c in fake.calls] == [
        "extract.system", "draft_arc.system", "ground.system"
    ]
    ledger = db_session.execute(select(AiUsageLedger)).scalars().all()
    assert sorted(r.kind for r in ledger) == ["draft", "extract", "ground"]
    assert all(r.job_id == job.id for r in ledger)

    p = job.proposal
    assert p["kind"] == "wizard" and p["source"] == "ai"
    assert p["couple_names"] == "Alex & Sam"
    assert p["story_arc"]["heading"] == "Alex & Sam"
    assert p["grounding"]["all_supported"] is True
    # No Places key → the venue is the couple's own words, nothing invented.
    assert p["event_details"]["venue"] == {"name": "Fern Hall", "address": None}
    assert p["event_details"]["date"]["value"] == "2027-05-01"

    # Advancing a finished job is an idempotent no-op.
    again = advance_job(db_session, s, job, text_model=fake)
    assert again.status == "awaiting_review" and len(fake.calls) == 3


def test_step_replay_is_noop_and_future_step_conflicts(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-replay")
    s = _settings()
    inp = _add_text_input(db_session, w, "Alex and Sam, Fern Hall.")
    fake = _fake()
    job = create_job(db_session, s, w, kind="wizard", input_ids=[inp.id])
    job = advance_job(db_session, s, job, text_model=fake, expected_step=0)  # transcribe
    assert job.step == 1

    replay = advance_job(db_session, s, job, text_model=fake, expected_step=0)
    assert replay.step == 1 and len(fake.calls) == 0  # no double work

    with pytest.raises(HTTPException) as exc:
        advance_job(db_session, s, job, text_model=fake, expected_step=3)
    assert exc.value.status_code == 409


def test_glyph_job_and_options_clamping(db_session):
    _enable_ai(db_session, ai_credits_included=10, ai_arc_generations_included=0)
    w = make_wedding(db_session, "wed-glyph")
    s = _settings()
    fake = _fake()
    job = create_job(
        db_session, s, w, kind="glyph", options={"beat_count": 99, "tone": "x" * 500}
    )
    assert job.credits_held == 1
    assert job.state["options"]["beat_count"] == 8  # clamped
    assert len(job.state["options"]["tone"]) == 120  # bounded

    job = _run_to_review(db_session, s, job, fake)  # glyph needs no inputs
    assert job.status == "awaiting_review"
    # 8.3: the allowlist-rebuild sanitiser runs inside the glyph step, so the
    # proposal only ever carries the re-serialised form.
    assert job.proposal["glyph"]["sanitised"] is True
    assert job.proposal["glyph"]["svg_children"] == '<circle cx="50" cy="50" r="40" />'


# ---------------------------------------------------------------------------
# Terminal paths — every one refunds and sweeps inputs
# ---------------------------------------------------------------------------
def _assert_refunded_and_swept(db, job):
    assert job.credits_held == 0
    assert db.execute(
        select(AiInput).where(AiInput.job_id == job.id)
    ).scalars().first() is None


def test_refusal_fails_job_and_refunds(db_session):
    _enable_ai(db_session, ai_credits_included=10, ai_arc_generations_included=0)
    w = make_wedding(db_session, "wed-refusal")
    s = _settings()
    inp = _add_text_input(db_session, w, "our story")
    fake = _fake()
    fake.responses["draft_arc.system"] = ProviderRefusal("content declined")

    job = create_job(db_session, s, w, kind="wizard", input_ids=[inp.id])
    assert job.credits_held == 5
    job = _run_to_review(db_session, s, job, fake)

    assert job.status == "failed"
    assert "declined" in job.error
    _assert_refunded_and_swept(db_session, job)
    # The refused draft call never charged: only extract reached the ledger.
    assert [r.kind for r in db_session.execute(select(AiUsageLedger)).scalars()] == ["extract"]


def test_media_input_without_gemini_fails_cleanly(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-media")
    s = _settings()
    photo = AiInput(wedding_id=w.id, kind="image", storage_url="http://x/y.jpg")
    db_session.add(photo)
    db_session.commit()

    job = create_job(db_session, s, w, kind="wizard", input_ids=[photo.id])
    job = advance_job(db_session, s, job, text_model=_fake())  # transcribe step
    assert job.status == "failed"
    assert "Gemini" in job.error or "media" in job.error.lower()
    _assert_refunded_and_swept(db_session, job)


def test_cancel_and_expiry_refund(db_session):
    _enable_ai(db_session, ai_credits_included=10, ai_arc_generations_included=0)
    w = make_wedding(db_session, "wed-cancel")
    s = _settings()

    job = create_job(db_session, s, w, kind="wizard")
    cancelled = cancel_job(db_session, job)
    assert cancelled.status == "cancelled" and cancelled.credits_held == 0
    with pytest.raises(HTTPException):  # cancelling twice conflicts
        cancel_job(db_session, cancelled)

    job2 = create_job(db_session, s, w, kind="wizard")
    job2.expires_at = utcnow() - timedelta(minutes=1)
    db_session.commit()
    job2 = advance_job(db_session, s, job2, text_model=_fake())
    assert job2.status == "expired"
    assert job2.credits_held == 0
