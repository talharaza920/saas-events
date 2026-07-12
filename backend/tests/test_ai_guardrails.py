"""AI guardrails (AI_WIZARD_PLAN Phase 8.3).

Four defences, each pinned with real payloads rather than inspection:
  • the SVG allowlist-rebuild sanitiser (<script>/onload=/url(#)/style all die);
  • the apply allowlist — the ONLY paths AI output can ever write, with the
    invite-tier/slug/status/published non-writability proven against a hostile
    proposal;
  • the daily cost ceiling — trips 503 and QUEUES the job (never fails it);
  • the reap-ai-jobs cron — stuck jobs expired + refunded, orphan inputs swept.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.ai.apply import apply_proposal
from app.ai.jobs import AI_SETTINGS_KEY, advance_job, create_job, reap_expired_jobs
from app.ai.providers.fake import FakeTextModel
from app.ai.svg import SvgSanitizationError, sanitize_glyph
from app.approval import set_approval_rules
from app.config import Settings
from app.models import (
    AiInput,
    AiJob,
    AiUsageLedger,
    AuditLog,
    Guest,
    Plan,
    PlatformSetting,
    StoryArc,
)
from app.timeutil import utcnow
from tests.helpers import DEV_TOKEN, make_wedding

AI_ENTITLEMENTS = {
    "ai_enabled": True,
    "ai_credits_included": 10,
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


def _fake(**response_overrides) -> FakeTextModel:
    responses = {
        "extract.system": {
            "couple_names": {"value": "Alex & Sam", "supported_by": "we're Alex and Sam"},
            "venue_name": {"value": "Fern Hall", "supported_by": "at Fern Hall"},
            "event_date": {"value": "2027-05-01", "supported_by": "on May 1st, 2027"},
        },
        "draft_arc.system": {
            "heading": "Alex & Sam",
            "beats": [
                {"text": "They met **at a bus stop**.", "image_prompt": "a rainy bus stop"},
                {"text": "Sam moved cities; Alex followed.", "image_prompt": "two suitcases"},
            ],
            "climax": "And now — join them.",
        },
        "ground.system": {"unsupported": [], "all_supported": True},
        "glyph.system": {"svg_children": "<circle cx='50' cy='50' r='40'/>", "concept": "a ring"},
    }
    responses.update(response_overrides)
    return FakeTextModel(responses=responses)


def _run_to_review(db, settings, job, fake) -> AiJob:
    for _ in range(job.steps_total):
        job = advance_job(db, settings, job, text_model=fake)
        if job.status not in ("queued", "running"):
            break
    return job


def _reviewable_job(db, wedding, proposal: dict, kind: str = "wizard") -> AiJob:
    """A job sitting in awaiting_review with an arbitrary (possibly hostile)
    stored proposal — apply must be safe against the DB blob, not just against
    what today's pipeline happens to build."""
    job = AiJob(
        wedding_id=wedding.id, kind=kind, status="awaiting_review",
        step=5, steps_total=5, state={}, proposal=proposal,
    )
    db.add(job)
    db.commit()
    return job


# ---------------------------------------------------------------------------
# 1. The SVG sanitiser — allowlist-rebuild, tested with real payloads
# ---------------------------------------------------------------------------
def test_sanitizer_strips_script_and_event_handlers():
    out = sanitize_glyph(
        "<script>alert(1)</script>"
        '<circle cx="50" cy="50" r="40" onload="alert(1)" fill="currentColor"/>'
    )
    assert out == '<circle cx="50" cy="50" r="40" fill="currentColor" />'


def test_sanitizer_drops_foreign_subtrees_hrefs_and_url_refs():
    out = sanitize_glyph(
        '<a href="javascript:alert(1)"><rect x="0" y="0" width="10" height="10"/></a>'
        '<image href="https://evil.example/x.svg"/>'
        '<foreignObject><body onload="x"/></foreignObject>'
        '<path d="M0 0h10" fill="url(#grad)"/>'
    )
    # The <a> subtree dies whole (the rect inside it too); the path survives
    # with its url(#) paint dropped — it inherits currentColor from the wrapper.
    assert out == '<path d="M0 0h10" />'
    assert "href" not in out and "url" not in out


def test_sanitizer_drops_style_class_id_and_non_currentcolor_fill():
    out = sanitize_glyph(
        "<style>rect{fill:red}</style>"
        '<rect x="1" y="1" width="5" height="5" fill="#ff0000" style="stroke:red" class="x" id="y"/>'
    )
    assert out == '<rect x="1" y="1" width="5" height="5" />'


def test_sanitizer_keeps_groups_drops_text_and_is_idempotent():
    src = '<g transform="rotate(45 50 50)"><circle cx="1" cy="1" r="1"/>sneaky text</g><text>hi</text>'
    out = sanitize_glyph(src)
    assert out == '<g transform="rotate(45 50 50)"><circle cx="1" cy="1" r="1" /></g>'
    assert sanitize_glyph(out) == out  # a sanitised glyph re-sanitises to itself


def test_sanitizer_rejects_unparseable_entities_and_all_dropped():
    with pytest.raises(SvgSanitizationError):
        sanitize_glyph('<circle cx="1"')  # unbalanced
    with pytest.raises(SvgSanitizationError):
        sanitize_glyph("<circle r='&xxe;'/>")  # undefined entity → parse error
    with pytest.raises(SvgSanitizationError):
        sanitize_glyph("<script>alert(1)</script>")  # nothing drawable survives


def test_sanitizer_enforces_bounds():
    with pytest.raises(SvgSanitizationError):
        sanitize_glyph('<circle cx="1" cy="1" r="1"/>' * 100)  # too many nodes
    with pytest.raises(SvgSanitizationError):
        sanitize_glyph("<g>" * 8 + '<circle cx="1" cy="1" r="1"/>' + "</g>" * 8)  # too deep


def test_glyph_step_sanitises_before_the_proposal_is_built(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-glyph-clean")
    fake = _fake(**{"glyph.system": {
        "svg_children": '<script>alert(1)</script><circle cx="50" cy="50" r="40"/>',
        "concept": "a ring",
    }})
    job = create_job(db_session, _settings(), w, kind="glyph")
    job = _run_to_review(db_session, _settings(), job, fake)
    assert job.status == "awaiting_review"
    assert job.proposal["glyph"]["sanitised"] is True
    assert "script" not in job.proposal["glyph"]["svg_children"]


def test_glyph_step_fails_cleanly_when_nothing_survives(db_session):
    _enable_ai(db_session, ai_arc_generations_included=0)
    w = make_wedding(db_session, "wed-glyph-evil")
    fake = _fake(**{"glyph.system": {"svg_children": "<script>only</script>", "concept": "x"}})
    job = create_job(db_session, _settings(), w, kind="glyph")
    assert job.credits_held == 1
    job = _run_to_review(db_session, _settings(), job, fake)
    assert job.status == "failed"
    assert job.credits_held == 0  # an unusable mark never costs the couple


# ---------------------------------------------------------------------------
# 2. The apply allowlist — the model proposes, code disposes
# ---------------------------------------------------------------------------
def test_apply_wizard_end_to_end_writes_only_allowlisted_paths(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-apply", published=False)
    w.event_details = {"dress_code": "Garden evening", "venue": "Old Hall"}
    db_session.commit()
    s = _settings()
    inp = _add_text_input(db_session, w, "We're Alex and Sam, Fern Hall, May 1st 2027.")
    job = create_job(db_session, s, w, kind="wizard", input_ids=[inp.id])
    job = _run_to_review(db_session, s, job, _fake())
    assert job.status == "awaiting_review"

    result = apply_proposal(db_session, _settings(), w, job)

    assert sorted(result["applied"]) == ["couple_names", "event_details", "story_arc"]
    db_session.refresh(w)
    assert w.couple_names == "Alex & Sam"
    assert w.content["nav"]["brand"] == "Alex & Sam"
    assert w.content["brand"]["wordmark_text"] == "Alex & Sam"
    assert w.event_details["venue"] == "Fern Hall"
    assert w.event_details["date_display"] == "2027-05-01"
    assert w.event_details["dress_code"] == "Garden evening"  # untouched keys survive
    assert w.slug == "wed-apply" and w.published is False and w.status == "active"

    arcs = db_session.execute(select(StoryArc).where(StoryArc.wedding_id == w.id)).scalars().all()
    assert len(arcs) == 1
    assert arcs[0].content["ai_generated"] is True  # provenance stamped
    assert arcs[0].content["beats"] == [
        {"text": "They met **at a bus stop**."},
        {"text": "Sam moved cities; Alex followed."},
    ]
    assert job.status == "applied"
    audit = db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai.job.apply")
    ).scalars().one()
    assert audit.detail["source"] == "ai"

    with pytest.raises(HTTPException) as exc:  # applying twice conflicts
        apply_proposal(db_session, _settings(), w, job)
    assert exc.value.status_code == 409


def test_apply_cannot_write_invite_tier_slug_status_or_published(db_session):
    """The sacred test: a hostile stored proposal full of forbidden keys
    changes nothing outside the allowlist — no guests, no tier, no slug,
    no publish, no settings, no theme."""
    w = make_wedding(db_session, "wed-hostile", published=False)
    job = _reviewable_job(db_session, w, {
        "kind": "wizard", "source": "ai",
        "couple_names": "New & Names",
        "invite_tier": "plus_family",
        "slug": "hacked",
        "status": "active",
        "published": True,
        "settings": {"admins_can_publish": True},
        "theme_tokens": {"colors": {"primary": "#000000"}},
        "guests": [{"name": "Mallory", "invite_tier": "plus_family", "story_arc_ids": []}],
        "event_details": {
            "slug": "nope",
            "invite_tier": "plus_family",
            "date": {"value": "May Day", "supported_by": "x"},
            "venue": {"name": "Fern Hall", "invite_tier": "plus_family", "maps_url": "m"},
        },
    })

    result = apply_proposal(db_session, _settings(), w, job)

    assert sorted(result["applied"]) == ["couple_names", "event_details"]
    db_session.refresh(w)
    assert w.couple_names == "New & Names"  # the allowlisted write happened…
    # …and nothing else did:
    assert w.slug == "wed-hostile" and w.published is False and w.status == "active"
    assert w.settings is None and w.theme_tokens is None
    assert db_session.execute(select(Guest)).scalars().all() == []  # never creates guests
    assert "slug" not in w.event_details and "invite_tier" not in w.event_details
    assert "invite_tier" not in (w.event_details.get("venue") or "")
    assert w.event_details == {"date_display": "May Day", "venue": "Fern Hall", "map_url": "m"}


def test_apply_selection_subset_unknown_selection_and_wrong_tenant(db_session):
    w = make_wedding(db_session, "wed-select")
    other = make_wedding(db_session, "wed-not-mine")
    proposal = {
        "couple_names": "Only & Names",
        "story_arc": {"heading": "H", "beats": [{"text": "b", "image_prompt": "i"}]},
    }
    job = _reviewable_job(db_session, w, proposal)

    with pytest.raises(HTTPException) as exc:  # tenancy belt inside apply itself
        apply_proposal(db_session, _settings(), other, job)
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        apply_proposal(db_session, _settings(), w, job, selections=["story_arc", "membership"])
    assert exc.value.status_code == 422  # unknown selection is refused, not ignored

    result = apply_proposal(db_session, _settings(), w, job, selections=["story_arc"])
    assert result["applied"] == ["story_arc"]
    db_session.refresh(w)
    assert w.couple_names == "Wed Select"  # unselected section untouched
    assert db_session.execute(select(StoryArc)).scalars().one().title == "H"


def test_apply_rechecks_story_arc_entitlement_at_apply_time(db_session):
    _enable_ai(db_session, max_story_arcs=0)  # plan changed while in review
    w = make_wedding(db_session, "wed-arc-limit")
    job = _reviewable_job(db_session, w, {
        "story_arc": {"heading": "H", "beats": [{"text": "b", "image_prompt": "i"}]},
    })
    with pytest.raises(HTTPException) as exc:
        apply_proposal(db_session, _settings(), w, job)
    assert exc.value.status_code == 403
    assert job.status == "awaiting_review"  # still reviewable after the refusal
    assert db_session.execute(select(StoryArc)).scalars().all() == []


def test_apply_runs_the_banned_word_scan(db_session):
    w = make_wedding(db_session, "wed-banned")
    set_approval_rules(db_session, {"banned_words": ["bus stop"]})
    db_session.commit()
    job = _reviewable_job(db_session, w, {
        "couple_names": "Fine & Names",
        "story_arc": {"heading": "H", "beats": [{"text": "met at a Bus Stop", "image_prompt": "i"}]},
    })
    with pytest.raises(HTTPException) as exc:
        apply_proposal(db_session, _settings(), w, job)
    assert exc.value.status_code == 422
    db_session.refresh(w)
    assert w.couple_names == "Wed Banned"  # nothing was written, not even clean sections
    assert job.status == "awaiting_review"


def test_apply_glyph_stores_only_the_sanitised_form(db_session):
    w = make_wedding(db_session, "wed-glyph-apply")
    w.content = {"brand": {"icon_mode": "default", "icon_url": None}}
    db_session.commit()
    # Hostile stored proposal — apply must re-sanitise, not trust the DB blob.
    job = _reviewable_job(db_session, w, {
        "glyph": {
            "svg_children": '<circle cx="50" cy="50" r="40"/><script>alert(1)</script>',
            "concept": "a ring", "sanitised": True,  # lies
        },
    }, kind="glyph")

    result = apply_proposal(db_session, _settings(), w, job)

    assert result["applied"] == ["glyph"]
    db_session.refresh(w)
    assert w.content["brand"]["icon_svg"] == '<circle cx="50" cy="50" r="40" />'
    assert w.content["brand"]["icon_mode"] == "default"  # rendering opt-in is the owner's call

    evil = _reviewable_job(db_session, w, {
        "glyph": {"svg_children": "<script>only</script>", "concept": "x"},
    }, kind="glyph")
    with pytest.raises(HTTPException) as exc:
        apply_proposal(db_session, _settings(), w, evil)
    assert exc.value.status_code == 422


def test_apply_with_nothing_applicable_is_422(db_session):
    w = make_wedding(db_session, "wed-empty")
    job = _reviewable_job(db_session, w, {"kind": "wizard", "source": "ai"})
    with pytest.raises(HTTPException) as exc:
        apply_proposal(db_session, _settings(), w, job)
    assert exc.value.status_code == 422
    assert job.status == "awaiting_review"


# ---------------------------------------------------------------------------
# 3. The daily cost ceiling — trips 503 and queues, never fails
# ---------------------------------------------------------------------------
def _spend(db, micros: int) -> None:
    db.add(AiUsageLedger(provider="fake", model="fake-model", kind="draft",
                         cost_usd_micros=micros))
    db.commit()


def test_daily_ceiling_queues_the_job_instead_of_failing(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-ceiling")
    s = _settings()
    db_session.add(PlatformSetting(key=AI_SETTINGS_KEY,
                                   value={"daily_cost_ceiling_usd": 0.01}))
    _spend(db_session, 20_000)  # $0.02 spent today — over the $0.01 ceiling
    inp = _add_text_input(db_session, w, "Alex and Sam, Fern Hall.")
    job = create_job(db_session, s, w, kind="wizard", input_ids=[inp.id])

    with pytest.raises(HTTPException) as exc:
        advance_job(db_session, s, job, text_model=_fake())
    assert exc.value.status_code == 503
    assert exc.value.headers["Retry-After"]
    db_session.refresh(job)
    assert job.status == "queued" and job.step == 0  # queued, not failed
    assert job.error is None

    # Ceiling lifted from the console → the same job resumes where it sat.
    db_session.get(PlatformSetting, AI_SETTINGS_KEY).value = {"daily_cost_ceiling_usd": 100.0}
    db_session.commit()
    job = advance_job(db_session, s, job, text_model=_fake())
    assert job.step == 1 and job.status == "running"


def test_daily_ceiling_zero_disables_the_check(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-no-ceiling")
    s = _settings()
    db_session.add(PlatformSetting(key=AI_SETTINGS_KEY, value={"daily_cost_ceiling_usd": 0}))
    _spend(db_session, 50_000_000)  # $50 today — irrelevant, ceiling off
    inp = _add_text_input(db_session, w, "Alex and Sam.")
    job = create_job(db_session, s, w, kind="wizard", input_ids=[inp.id])
    job = advance_job(db_session, s, job, text_model=_fake())
    assert job.step == 1


# ---------------------------------------------------------------------------
# 4. The reap-ai-jobs cron
# ---------------------------------------------------------------------------
def test_reap_expires_stuck_jobs_and_sweeps_orphan_inputs(db_session):
    _enable_ai(db_session)
    s = _settings()
    stuck_w = make_wedding(db_session, "wed-stuck")
    fresh_w = make_wedding(db_session, "wed-fresh")

    stuck_inp = _add_text_input(db_session, stuck_w, "never finished")
    stuck = create_job(db_session, s, stuck_w, kind="wizard", input_ids=[stuck_inp.id])
    stuck.expires_at = utcnow() - timedelta(minutes=5)
    fresh = create_job(db_session, s, fresh_w, kind="wizard")

    old_orphan = _add_text_input(db_session, fresh_w, "uploaded and abandoned")
    old_orphan.created_at = utcnow() - timedelta(days=2)
    new_orphan = _add_text_input(db_session, fresh_w, "uploaded a minute ago")
    db_session.commit()

    result = reap_expired_jobs(db_session, _settings())

    assert [e["job_id"] for e in result["expired"]] == [str(stuck.id)]
    assert result["orphan_inputs_swept"] == 1
    db_session.refresh(stuck)
    assert stuck.status == "expired" and stuck.credits_held == 0
    remaining = {i.id for i in db_session.execute(select(AiInput)).scalars()}
    assert remaining == {new_orphan.id}  # stuck job's input + old orphan both gone
    db_session.refresh(fresh)
    assert fresh.status == "queued"  # a live job is never touched

    assert reap_expired_jobs(db_session, _settings()) == {"expired": [], "orphan_inputs_swept": 0}


def test_reap_cron_endpoint_requires_the_shared_secret(client, make_client, db_session):
    # No CRON_SECRET configured → the route doesn't exist.
    assert client.get("/api/internal/cron/reap-ai-jobs").status_code == 404

    secured = make_client(cron_secret="s3cret-cron")
    assert secured.post("/api/internal/cron/reap-ai-jobs").status_code == 401
    assert secured.get(
        "/api/internal/cron/reap-ai-jobs", headers={"Authorization": "Bearer wrong"}
    ).status_code == 401

    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-cron-reap")
    job = create_job(db_session, _settings(), w, kind="wizard")
    job.expires_at = utcnow() - timedelta(hours=1)
    db_session.commit()

    r = secured.get(
        "/api/internal/cron/reap-ai-jobs", headers={"Authorization": "Bearer s3cret-cron"}
    )
    assert r.status_code == 200
    assert [e["job_id"] for e in r.json()["expired"]] == [str(job.id)]
    db_session.refresh(job)
    assert job.status == "expired"
