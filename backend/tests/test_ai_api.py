"""AI wizard API surface (AI_WIZARD_PLAN Phase 8.4).

Exercises the wedding-scoped `/api/w/{slug}/admin/ai/*` endpoints and the
platform AI console over HTTP, offline through the FakeTextModel injected via
the `get_job_text_model` dependency. Per CLAUDE.md, EVERY endpoint here ships
with a no-auth 401 and a non-member/wrong-tenant 404 test — that matrix is the
first test in the file. The deeper pipeline/guardrail behaviour is pinned in
test_ai_pipeline.py / test_ai_guardrails.py; this file covers the HTTP seams:
authz, idempotency, regeneration + variants, selection, and the console.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.ai.jobs import create_job
from app.ai.prompts import resolve_spec
from app.ai.providers.fake import FakeTextModel
from app.ai.types import ProviderRefusal
from app.config import Settings
from app.main import app
from app.models import AiVariant, AuditLog, Plan, StoryArc, Wedding
from app.routers.ai_admin import get_job_text_model
from tests.helpers import DEV_TOKEN, make_member, make_wedding, platform_auth, user_auth

OWNER = "owner@example.com"
STRANGER = "stranger@example.com"

AI_ENTS = {
    "ai_enabled": True,
    "ai_credits_included": 10,
    "ai_arc_generations_included": 1,
    "ai_max_inputs_per_job": 12,
    "ai_max_regens_per_artifact": 3,
}


def _enable_ai(db, **overrides) -> None:
    ents = dict(AI_ENTS)
    ents.update(overrides)
    db.add(Plan(name="ai-test-plan", is_default=True, entitlements=ents))
    db.commit()


def _settings() -> Settings:
    return Settings(
        _env_file=None, environment="development", dev_admin_token=DEV_TOKEN,
        ai_text_provider="fake",
    )


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
                {"text": "They met **at a stop**.", "image_prompt": "a rainy street, warm light"},
                {"text": "Sam moved cities; Alex followed.", "image_prompt": "two suitcases by a door"},
            ],
            "climax": "And now — join them.",
        },
        "ground.system": {"unsupported": [], "all_supported": True},
        "glyph.system": {"svg_children": "<circle cx='50' cy='50' r='40'/>", "concept": "a ring"},
    })


@pytest.fixture
def fake() -> FakeTextModel:
    return _fake()


@pytest.fixture
def client(make_client, fake):
    """A client whose advance/regenerate endpoints run against the scripted
    fake — overriding the get_job_text_model dependency, exactly the seam a
    provider swap would use."""
    c = make_client(ai_text_provider="fake")
    app.dependency_overrides[get_job_text_model] = lambda: fake
    return c


def _auth() -> dict:
    return user_auth(OWNER)


def _base(w) -> str:
    return f"/api/w/{w.slug}/admin/ai"


def _wedding_with_owner(db, slug: str = "wed-ai", **wedding_kwargs) -> Wedding:
    w = make_wedding(db, slug, **wedding_kwargs)
    make_member(db, w, OWNER, "owner")
    return w


def _run_to_review(client, w, *, kind: str = "wizard") -> dict:
    input_ids = []
    if kind != "glyph":
        r = client.post(
            f"{_base(w)}/inputs",
            json={"text": "We're Alex and Sam, getting married at Fern Hall on May 1st, 2027."},
            headers=_auth(),
        )
        assert r.status_code == 201, r.text
        input_ids = [r.json()["id"]]
    r = client.post(
        f"{_base(w)}/jobs", json={"kind": kind, "input_ids": input_ids}, headers=_auth()
    )
    assert r.status_code == 201, r.text
    job = r.json()
    for _ in range(job["steps_total"]):
        r = client.post(f"{_base(w)}/jobs/{job['id']}/advance", headers=_auth())
        assert r.status_code == 200, r.text
        job = r.json()
        if job["status"] not in ("queued", "running"):
            break
    assert job["status"] == "awaiting_review", job
    return job


# ---------------------------------------------------------------------------
# The authz matrix — every endpoint: 401 unauthenticated, 404 non-member.
# ---------------------------------------------------------------------------
def test_every_ai_endpoint_401_unauth_404_nonmember(db_session, client):
    _enable_ai(db_session)
    w = _wedding_with_owner(db_session)
    jid = uuid.uuid4()  # authz fires in the dependency, before any job lookup
    vid = str(uuid.uuid4())
    cases = [
        ("post", f"{_base(w)}/inputs", {"text": "hello"}),
        ("post", f"{_base(w)}/jobs", {"kind": "wizard"}),
        ("get", f"{_base(w)}/jobs", None),
        ("get", f"{_base(w)}/jobs/{jid}", None),
        ("post", f"{_base(w)}/jobs/{jid}/advance", {}),
        ("post", f"{_base(w)}/jobs/{jid}/regenerate", {"artifact": "arc.text"}),
        ("post", f"{_base(w)}/jobs/{jid}/select", {"artifact": "arc.text", "variant_id": vid}),
        ("post", f"{_base(w)}/jobs/{jid}/apply", {}),
        ("post", f"{_base(w)}/jobs/{jid}/cancel", None),
        ("get", f"{_base(w)}/credits", None),
    ]
    for method, url, body in cases:
        kwargs = {} if body is None or method == "get" else {"json": body}
        assert getattr(client, method)(url, **kwargs).status_code == 401, url
        r = getattr(client, method)(url, headers=user_auth(STRANGER), **kwargs)
        # Existence is never revealed to a non-member.
        assert r.status_code == 404, (url, r.status_code)


def test_job_of_another_wedding_is_404_through_my_path(db_session, client):
    """The wrong-tenant belt: a member of A using A's own path cannot reach a
    job that belongs to B (same 404 as a nonexistent id)."""
    _enable_ai(db_session)
    mine = _wedding_with_owner(db_session, "wed-mine")
    other = make_wedding(db_session, "wed-other")
    foreign_job = create_job(db_session, _settings(), other, kind="glyph")
    r = client.get(f"{_base(mine)}/jobs/{foreign_job.id}", headers=_auth())
    assert r.status_code == 404
    r = client.post(f"{_base(mine)}/jobs/{foreign_job.id}/cancel", headers=_auth())
    assert r.status_code == 404


def test_suspended_wedding_is_read_only_for_ai(db_session, client):
    _enable_ai(db_session)
    w = _wedding_with_owner(db_session, "wed-susp", status="suspended")
    r = client.post(f"{_base(w)}/inputs", json={"text": "hi"}, headers=_auth())
    assert r.status_code == 403  # mutations refused
    assert client.get(f"{_base(w)}/jobs", headers=_auth()).status_code == 200  # reads stay


def test_platform_ai_endpoints_require_platform_admin(db_session, client):
    for method, url, body in [
        ("get", "/api/platform/ai/prompts", None),
        ("put", "/api/platform/ai/prompts/extract.system", {"template": "x"}),
        ("post", "/api/platform/ai/prompts/extract.system/activate",
         {"provider": "", "version": 1, "active": False}),
        ("get", "/api/platform/ai/usage", None),
        ("get", "/api/platform/settings/ai", None),
        ("put", "/api/platform/settings/ai", {"kill_switch": True}),
    ]:
        kwargs = {} if body is None else {"json": body}
        assert getattr(client, method)(url, **kwargs).status_code == 401, url
        r = getattr(client, method)(url, headers=user_auth(STRANGER), **kwargs)
        assert r.status_code == 403, (url, r.status_code)


# ---------------------------------------------------------------------------
# Inputs + job creation
# ---------------------------------------------------------------------------
def test_input_requires_ai_enabled_and_bounds(db_session, client):
    w = _wedding_with_owner(db_session)  # no plan → ai_enabled defaults False
    r = client.post(f"{_base(w)}/inputs", json={"text": "hi"}, headers=_auth())
    assert r.status_code == 403
    _enable_ai(db_session)
    r = client.post(f"{_base(w)}/inputs", json={"text": "x" * 20_001}, headers=_auth())
    assert r.status_code == 422
    r = client.post(f"{_base(w)}/inputs", json={"text": "our story"}, headers=_auth())
    assert r.status_code == 201
    assert r.json()["kind"] == "text" and r.json()["bytes"] == len("our story")


def test_job_create_idempotency_and_one_active(db_session, client):
    _enable_ai(db_session)
    w = _wedding_with_owner(db_session)
    headers = {**_auth(), "Idempotency-Key": "key-1"}
    first = client.post(f"{_base(w)}/jobs", json={"kind": "glyph"}, headers=headers)
    assert first.status_code == 201
    replay = client.post(f"{_base(w)}/jobs", json={"kind": "glyph"}, headers=headers)
    assert replay.json()["id"] == first.json()["id"]  # same job, no second charge
    conflict = client.post(f"{_base(w)}/jobs", json={"kind": "glyph"}, headers=_auth())
    assert conflict.status_code == 409
    # An unknown kind is refused at the schema edge.
    bad = client.post(f"{_base(w)}/jobs", json={"kind": "banquet"}, headers=_auth())
    assert bad.status_code == 422


# ---------------------------------------------------------------------------
# The full run over HTTP: wizard → review → apply
# ---------------------------------------------------------------------------
def test_wizard_full_run_and_apply_over_http(db_session, client):
    _enable_ai(db_session)
    w = _wedding_with_owner(db_session)
    job = _run_to_review(client, w)

    p = job["proposal"]
    assert p["couple_names"] == "Alex & Sam"
    assert p["event_details"]["venue"]["name"] == "Fern Hall"
    assert p["grounding"]["all_supported"] is True

    r = client.post(
        f"{_base(w)}/jobs/{job['id']}/apply",
        json={"selections": ["story_arc", "event_details"]},
        headers=_auth(),
    )
    assert r.status_code == 200
    assert sorted(r.json()["applied"]) == ["event_details", "story_arc"]

    db_session.expire_all()
    arc = db_session.execute(select(StoryArc)).scalars().one()
    assert arc.content["ai_generated"] is True  # provenance
    w_db = db_session.execute(select(Wedding).where(Wedding.slug == w.slug)).scalar_one()
    assert w_db.event_details["venue"] == "Fern Hall"
    assert w_db.couple_names != "Alex & Sam"  # unselected section untouched
    audit = db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai.job.apply")
    ).scalars().one()
    assert audit.detail["source"] == "ai"

    again = client.post(f"{_base(w)}/jobs/{job['id']}/apply", headers=_auth())
    assert again.status_code == 409  # applied jobs don't apply twice


def test_advance_is_idempotent_per_step_over_http(db_session, client, fake):
    _enable_ai(db_session)
    w = _wedding_with_owner(db_session)
    r = client.post(f"{_base(w)}/inputs", json={"text": "Alex and Sam."}, headers=_auth())
    job_id = client.post(
        f"{_base(w)}/jobs", json={"kind": "wizard", "input_ids": [r.json()["id"]]},
        headers=_auth(),
    ).json()["id"]

    url = f"{_base(w)}/jobs/{job_id}/advance"
    assert client.post(url, json={"expected_step": 0}, headers=_auth()).json()["step"] == 1
    assert client.post(url, json={"expected_step": 1}, headers=_auth()).json()["step"] == 2
    calls = len(fake.calls)
    replay = client.post(url, json={"expected_step": 1}, headers=_auth())
    assert replay.status_code == 200 and replay.json()["step"] == 2
    assert len(fake.calls) == calls  # no double work, no double charge
    assert client.post(url, json={"expected_step": 4}, headers=_auth()).status_code == 409


# ---------------------------------------------------------------------------
# Regeneration + variants
# ---------------------------------------------------------------------------
def test_regenerate_seeds_original_first_free_then_charges(db_session, client, fake):
    _enable_ai(db_session)
    w = _wedding_with_owner(db_session)
    job = _run_to_review(client, w)  # rides the free arc → credits_held 0
    before = len(fake.calls)

    r = client.post(
        f"{_base(w)}/jobs/{job['id']}/regenerate",
        json={"artifact": "arc.text", "steer": "less flowery"},
        headers=_auth(),
    )
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["selected"] is False and v["steer"] == "less flowery"
    assert v["content"]["story_arc"]["heading"] == "Alex & Sam"
    assert v["content"]["grounding"]["all_supported"] is True  # re-grounded

    # The steer note lives in the USER turn only — never the system prompt.
    draft_call = next(c for c in fake.calls[before:] if c.prompt.key == "draft_arc.system")
    assert "<steer>" in draft_call.prompt.user and "less flowery" in draft_call.prompt.user
    assert "less flowery" not in draft_call.prompt.system

    detail = client.get(f"{_base(w)}/jobs/{job['id']}", headers=_auth()).json()
    assert detail["credits_held"] == 0  # the first regen is free
    arc_variants = [x for x in detail["variants"] if x["artifact"] == "arc.text"]
    assert len(arc_variants) == 2  # the original was seeded, nothing destroyed
    assert sum(1 for x in arc_variants if x["selected"]) == 1  # original still the keeper

    r2 = client.post(
        f"{_base(w)}/jobs/{job['id']}/regenerate",
        json={"artifact": "arc.text"}, headers=_auth(),
    )
    assert r2.status_code == 200
    detail = client.get(f"{_base(w)}/jobs/{job['id']}", headers=_auth()).json()
    assert detail["credits_held"] == 1  # the second one draws a credit


def test_regenerate_cap_and_wrong_artifact(db_session, client):
    _enable_ai(db_session, ai_max_regens_per_artifact=1)
    w = _wedding_with_owner(db_session)
    job = _run_to_review(client, w)
    url = f"{_base(w)}/jobs/{job['id']}/regenerate"
    assert client.post(url, json={"artifact": "arc.text"}, headers=_auth()).status_code == 200
    capped = client.post(url, json={"artifact": "arc.text"}, headers=_auth())
    assert capped.status_code == 403  # ai_max_regens_per_artifact
    # A wizard run has no glyph to regenerate.
    assert client.post(url, json={"artifact": "glyph"}, headers=_auth()).status_code == 422


def test_regenerate_refusal_never_charges_or_writes(db_session, client, fake):
    _enable_ai(db_session)
    w = _wedding_with_owner(db_session)
    job = _run_to_review(client, w)
    fake.responses["draft_arc.system"] = ProviderRefusal("content declined")

    r = client.post(
        f"{_base(w)}/jobs/{job['id']}/regenerate",
        json={"artifact": "arc.text"}, headers=_auth(),
    )
    assert r.status_code == 422
    detail = client.get(f"{_base(w)}/jobs/{job['id']}", headers=_auth()).json()
    assert detail["status"] == "awaiting_review"  # the job survives — proposal intact
    assert detail["credits_held"] == 0
    assert detail["variants"] == []  # nothing seeded, nothing appended


def test_select_variant_swaps_proposal_and_back(db_session, client, fake):
    _enable_ai(db_session)
    w = _wedding_with_owner(db_session)
    job = _run_to_review(client, w)
    fake.responses["draft_arc.system"] = {
        "heading": "Sam & Alex",
        "beats": [{"text": "Take two.", "image_prompt": "morning light"}],
    }
    client.post(
        f"{_base(w)}/jobs/{job['id']}/regenerate",
        json={"artifact": "arc.text"}, headers=_auth(),
    )
    detail = client.get(f"{_base(w)}/jobs/{job['id']}", headers=_auth()).json()
    variants = {x["content"]["story_arc"]["heading"]: x for x in detail["variants"]}
    assert set(variants) == {"Alex & Sam", "Sam & Alex"}

    url = f"{_base(w)}/jobs/{job['id']}/select"
    r = client.post(
        url, json={"artifact": "arc.text", "variant_id": variants["Sam & Alex"]["id"]},
        headers=_auth(),
    )
    assert r.status_code == 200
    assert r.json()["proposal"]["story_arc"]["heading"] == "Sam & Alex"

    # Regenerating never destroyed the original — selecting it back restores it.
    r = client.post(
        url, json={"artifact": "arc.text", "variant_id": variants["Alex & Sam"]["id"]},
        headers=_auth(),
    )
    assert r.json()["proposal"]["story_arc"]["heading"] == "Alex & Sam"

    bogus = client.post(
        url, json={"artifact": "arc.text", "variant_id": str(uuid.uuid4())}, headers=_auth()
    )
    assert bogus.status_code == 404


def test_glyph_regeneration_is_sanitised(db_session, client, fake):
    _enable_ai(db_session, ai_arc_generations_included=0)
    w = _wedding_with_owner(db_session)
    job = _run_to_review(client, w, kind="glyph")
    fake.responses["glyph.system"] = {
        "svg_children": "<circle cx='9' cy='9' r='8'/><script>steal()</script>",
        "concept": "a ring",
    }
    r = client.post(
        f"{_base(w)}/jobs/{job['id']}/regenerate",
        json={"artifact": "glyph"}, headers=_auth(),
    )
    assert r.status_code == 200
    content = r.json()["content"]
    assert content["sanitised"] is True
    assert "script" not in content["svg_children"]
    assert content["svg_children"] == '<circle cx="9" cy="9" r="8" />'


def test_cancel_over_http_refunds(db_session, client):
    _enable_ai(db_session)
    w = _wedding_with_owner(db_session)
    job_id = client.post(
        f"{_base(w)}/jobs", json={"kind": "glyph"}, headers=_auth()
    ).json()["id"]
    r = client.post(f"{_base(w)}/jobs/{job_id}/cancel", headers=_auth())
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled" and r.json()["credits_held"] == 0


def test_credits_endpoint(db_session, client):
    _enable_ai(db_session)
    w = _wedding_with_owner(db_session)
    client.post(f"{_base(w)}/jobs", json={"kind": "glyph"}, headers=_auth())  # holds 1
    r = client.get(f"{_base(w)}/credits", headers=_auth())
    assert r.status_code == 200
    assert r.json() == {
        "remaining": 9, "included": 10,
        "arc_generations_used": 0, "arc_generations_included": 1,
    }


# ---------------------------------------------------------------------------
# Platform console: circuit breaker, prompt editor, usage
# ---------------------------------------------------------------------------
def test_ai_settings_roundtrip_and_kill_switch_bites(db_session, client):
    _enable_ai(db_session)
    w = _wedding_with_owner(db_session)

    r = client.get("/api/platform/settings/ai", headers=platform_auth())
    assert r.json() == {"kill_switch": False, "daily_cost_ceiling_usd": 25.0}

    r = client.put(
        "/api/platform/settings/ai",
        json={"kill_switch": True, "daily_cost_ceiling_usd": 5},
        headers=platform_auth(),
    )
    assert r.status_code == 200 and r.json()["kill_switch"] is True

    blocked = client.post(f"{_base(w)}/jobs", json={"kind": "glyph"}, headers=_auth())
    assert blocked.status_code == 503  # tripped before any charge

    assert db_session.execute(
        select(AuditLog).where(AuditLog.action == "platform.settings.ai")
    ).scalars().first() is not None


def test_prompt_editor_save_activate_rollback(db_session, client):
    listing = client.get("/api/platform/ai/prompts", headers=platform_auth()).json()
    defaults = [p for p in listing if p["is_code_default"]]
    assert sorted(p["key"] for p in defaults) == [
        "draft_arc.system", "extract.system", "extract_guests.system", "glyph.system", "ground.system"
    ]
    assert all(p["is_effective"] for p in defaults)  # nothing overridden yet

    r = client.put(
        "/api/platform/ai/prompts/extract.system",
        json={"template": "Extract precisely. Nulls beat guesses."},
        headers=platform_auth(),
    )
    assert r.status_code == 201 or r.status_code == 200
    saved = r.json()
    assert saved["version"] == 1 and saved["active"] and saved["is_effective"]
    assert resolve_spec(
        db_session, "extract.system", provider="fake"
    ).template.startswith("Extract precisely")

    # Rollback = deactivate; resolution falls back to the code default.
    r = client.post(
        "/api/platform/ai/prompts/extract.system/activate",
        json={"provider": "", "version": 1, "active": False},
        headers=platform_auth(),
    )
    assert r.status_code == 200 and r.json()["is_effective"] is False
    assert resolve_spec(db_session, "extract.system", provider="fake").version == 0

    assert client.put(
        "/api/platform/ai/prompts/never.heard.of.it",
        json={"template": "x"}, headers=platform_auth(),
    ).status_code == 404
    assert db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai.prompt.save")
    ).scalars().first() is not None


def test_usage_summary_after_a_run(db_session, client):
    _enable_ai(db_session)
    w = _wedding_with_owner(db_session)
    _run_to_review(client, w)
    # The fake provider prices at $0 — seed one real-cost row so the money
    # widgets have something to show.
    from app.models import AiUsageLedger
    db_session.add(AiUsageLedger(
        wedding_id=w.id, provider="anthropic", model="claude-opus-4-8",
        kind="draft", cost_usd_micros=2_500_000,
    ))
    db_session.commit()

    r = client.get("/api/platform/ai/usage", headers=platform_auth())
    assert r.status_code == 200
    usage = r.json()
    assert usage["today_usd"] == 2.5
    assert usage["kill_switch"] is False and usage["ceiling_usd"] == 25.0
    assert usage["jobs_by_status"] == {"awaiting_review": 1}
    assert {"extract", "draft", "ground"} <= set(usage["by_kind"])
    assert sum(d["calls"] for d in usage["days"]) == 4  # 3 fake calls + seeded row
    assert usage["top_weddings"][0]["slug"] == w.slug
    assert usage["top_weddings"][0]["usd"] == 2.5
