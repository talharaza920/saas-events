"""AI wizard data model (AI_WIZARD_PLAN Phase 8.0).

Pins the shapes the rest of Phase 8 stands on: the one-active-job-per-wedding
partial unique index (the concurrency ceiling lives in the DB, not in app
code), idempotency-key uniqueness, purge behaviour (PII rows cascade away, the
spend ledger survives with its pointers nulled), the ai_prompts composite key,
and the AI entitlement defaults (off by default).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.entitlements import DEFAULT_ENTITLEMENTS, check_limit, require_feature
from app.models import (
    AiInput,
    AiJob,
    AiJobStatus,
    AiPrompt,
    AiUsageLedger,
    AiVariant,
)
from tests.helpers import make_wedding, platform_auth


def _job(wedding, status: str = AiJobStatus.QUEUED, **kw) -> AiJob:
    return AiJob(wedding_id=wedding.id, kind="story_arc", status=status, **kw)


# ---------------------------------------------------------------------------
# One queued/running job per wedding — enforced by the partial unique index.
# ---------------------------------------------------------------------------
def test_one_active_job_per_wedding(db_session):
    w = make_wedding(db_session, "wed-ai")
    first = _job(w, AiJobStatus.QUEUED)
    db_session.add(first)
    db_session.commit()

    db_session.add(_job(w, AiJobStatus.RUNNING))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # A terminal (or in-review) job releases the slot.
    first.status = AiJobStatus.APPLIED
    db_session.commit()
    db_session.add(_job(w, AiJobStatus.QUEUED))
    db_session.commit()


def test_active_index_is_per_wedding_and_ignores_review(db_session):
    a = make_wedding(db_session, "wed-ai-a")
    b = make_wedding(db_session, "wed-ai-b")
    # Two weddings may each run one job at the same time.
    db_session.add_all([_job(a, AiJobStatus.RUNNING), _job(b, AiJobStatus.RUNNING)])
    db_session.commit()

    # awaiting_review is not an ACTIVE status — a new job may start while a
    # proposal sits in review.
    job_a = db_session.execute(
        select(AiJob).where(AiJob.wedding_id == a.id)
    ).scalars().one()
    job_a.status = AiJobStatus.AWAITING_REVIEW
    db_session.commit()
    db_session.add(_job(a, AiJobStatus.QUEUED))
    db_session.commit()


def test_idempotency_key_unique_per_wedding(db_session):
    a = make_wedding(db_session, "wed-idem-a")
    b = make_wedding(db_session, "wed-idem-b")
    # Terminal statuses so the one-active-job index stays out of the way.
    db_session.add(_job(a, AiJobStatus.APPLIED, idempotency_key="k1"))
    db_session.commit()

    db_session.add(_job(a, AiJobStatus.FAILED, idempotency_key="k1"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Same key on another wedding is fine; so are many NULL keys on one wedding.
    db_session.add(_job(b, AiJobStatus.APPLIED, idempotency_key="k1"))
    db_session.add_all([_job(a, AiJobStatus.CANCELLED), _job(a, AiJobStatus.EXPIRED)])
    db_session.commit()


# ---------------------------------------------------------------------------
# Purge: AI PII rows cascade away with the tenant; the spend ledger survives
# with wedding_id/job_id nulled (same discipline as the audit log).
# ---------------------------------------------------------------------------
def test_purge_cascades_ai_rows_and_keeps_ledger(client, db_session):
    from datetime import timedelta

    from app.timeutil import utcnow

    doomed = make_wedding(db_session, "wed-ai-doomed")
    kept = make_wedding(db_session, "wed-ai-kept")

    for w in (doomed, kept):
        job = _job(w, AiJobStatus.APPLIED)
        db_session.add(job)
        db_session.flush()
        db_session.add(AiInput(wedding_id=w.id, job_id=job.id, kind="text", text_content="hi"))
        db_session.add(AiVariant(wedding_id=w.id, job_id=job.id, artifact="glyph"))
        db_session.add(
            AiUsageLedger(
                wedding_id=w.id, job_id=job.id,
                provider="anthropic", model="claude-opus-4-8", kind="draft",
                cost_usd_micros=150_000,
            )
        )
    doomed.status = "archived"
    doomed.published = False
    doomed.archived_at = utcnow() - timedelta(days=31)
    db_session.commit()

    r = client.post("/api/platform/purge-archived", headers=platform_auth())
    assert r.status_code == 200 and r.json()["count"] == 1

    # PII rows gone for the purged tenant, intact for the live one.
    assert db_session.execute(select(AiJob).where(AiJob.wedding_id == doomed.id)).first() is None
    assert db_session.execute(select(AiInput).where(AiInput.wedding_id == doomed.id)).first() is None
    assert db_session.execute(select(AiVariant).where(AiVariant.wedding_id == doomed.id)).first() is None
    assert db_session.execute(select(AiJob).where(AiJob.wedding_id == kept.id)).first() is not None

    # The money record outlives the tenant, pointers nulled.
    ledgers = db_session.execute(select(AiUsageLedger)).scalars().all()
    assert len(ledgers) == 2
    orphaned = [l for l in ledgers if l.wedding_id is None]
    assert len(orphaned) == 1
    assert orphaned[0].job_id is None
    assert orphaned[0].cost_usd_micros == 150_000


# ---------------------------------------------------------------------------
# ai_prompts: (key, provider, version) composite key; '' = shared fallback.
# ---------------------------------------------------------------------------
def test_ai_prompt_composite_key(db_session):
    db_session.add(AiPrompt(key="extract.system", template="v1"))  # provider '' fallback
    db_session.add(AiPrompt(key="extract.system", provider="anthropic", version=1, template="tuned"))
    db_session.commit()

    db_session.add(AiPrompt(key="extract.system", provider="", version=1, template="dupe"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # A new version of the same (key, provider) is a new row, not an update.
    db_session.add(AiPrompt(key="extract.system", provider="anthropic", version=2, template="tuned2"))
    db_session.commit()


# ---------------------------------------------------------------------------
# Entitlements: AI is off by default and the limits enforce through the
# existing helpers.
# ---------------------------------------------------------------------------
def test_ai_entitlement_defaults():
    assert DEFAULT_ENTITLEMENTS["ai_enabled"] is False
    assert DEFAULT_ENTITLEMENTS["ai_credits_included"] == 0
    assert DEFAULT_ENTITLEMENTS["ai_arc_generations_included"] == 1
    assert DEFAULT_ENTITLEMENTS["ai_max_images_per_arc"] == 6
    assert DEFAULT_ENTITLEMENTS["ai_max_inputs_per_job"] == 12
    assert DEFAULT_ENTITLEMENTS["ai_max_regens_per_artifact"] == 3


def test_ai_feature_gate_and_limits(db_session):
    w = make_wedding(db_session, "wed-ai-ent")

    with pytest.raises(HTTPException) as exc:
        require_feature(db_session, w, "ai_enabled")
    assert exc.value.status_code == 403
    assert "AI assistance" in exc.value.detail

    # 12 inputs is the ceiling: the 13th is refused with a friendly message.
    check_limit(db_session, w, "ai_max_inputs_per_job", current_count=11)
    with pytest.raises(HTTPException) as exc:
        check_limit(db_session, w, "ai_max_inputs_per_job", current_count=12)
    assert exc.value.status_code == 403
