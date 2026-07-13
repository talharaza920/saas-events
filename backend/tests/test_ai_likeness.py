"""Phase 8.5d — likeness: illustrations OF the couple, from photos they consent to.

This is the one feature shipping ahead of its legal framing, so its tests are
the framing it does have. What they pin, in order of how badly it hurts if it
breaks:

* **No consent, no photo.** An upload without the box ticked is refused, and a
  row without `consent_at` is never handed to the image model — even if a
  client posts its id at the references endpoint (which answers 404: there is
  no path that reveals "that photo exists but you may not use it").
* **Stylised only.** With photos attached, the photographic preset is refused
  where it is chosen, and silently downgraded where a prompt is composed —
  belt and braces, because a photoreal rendering of a real person is exactly
  the thing the deferred legal work is about.
* **Off by default, off on demand.** `ai_likeness_enabled` is false in
  DEFAULT_ENTITLEMENTS; revoking it mid-run stops the illustration with a way
  out rather than quietly drawing strangers.
* **A reference is never read.** It is skipped by transcribe, so a face never
  reaches the text model, the facts, or the story.
* **It doesn't outlive the run.** Cancel and apply delete the photo row AND its
  stored object.

Offline throughout: scripted text model, stub media seam that records the
references it was handed, tmp storage.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import app.storage as storage
from app.ai.apply import apply_proposal
from app.ai.edit import edit_proposal
from app.ai.images import illustrate
from app.ai.jobs import advance_job, cancel_job, create_job
from app.ai.likeness import BLOCKED_LIKENESS_STYLES, set_references
from app.ai.providers.fake import FakeTextModel
from app.ai.styles import compose_image_prompt
from app.ai.variants import regenerate_artifact
from app.ai.types import Usage
from app.config import Settings
from app.entitlements import DEFAULT_ENTITLEMENTS
from app.main import app
from app.models import AiInput, AiJob, Plan
from app.routers.ai_admin import get_job_media_model, get_job_text_model
from app.timeutil import utcnow
from tests.helpers import DEV_TOKEN, make_member, make_wedding, user_auth

OWNER = "owner@example.com"
STRANGER = "stranger@example.com"

PNG = b"\x89PNG\r\n\x1a\n" + b"pretend-photo-of-us"

AI_ENTS = {
    "ai_enabled": True,
    "ai_credits_included": 20,
    "ai_arc_generations_included": 1,
    "ai_max_inputs_per_job": 12,
    "ai_max_regens_per_artifact": 3,
    "ai_max_images_per_arc": 6,
    "ai_likeness_enabled": True,
    "ai_max_likeness_references": 3,
}


@pytest.fixture(autouse=True)
def _tmp_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path)
    yield tmp_path


def _settings(**overrides) -> Settings:
    base = dict(
        environment="development", dev_admin_token=DEV_TOKEN,
        ai_text_provider="fake", gemini_api_key="test-gemini-key",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _enable_ai(db, **overrides) -> None:
    ents = dict(AI_ENTS)
    ents.update(overrides)
    db.add(Plan(name="ai-test-plan", is_default=True, entitlements=ents))
    db.commit()


def _fake_text(beats: int = 2) -> FakeTextModel:
    return FakeTextModel(responses={
        "extract.system": {
            "couple_names": {"value": "Alex & Sam", "supported_by": "we're Alex and Sam"},
        },
        "draft_arc.system": {
            "heading": "Alex & Sam",
            "beats": [
                {"text": f"Beat {i}.", "image_prompt": f"scene {i}, warm light"}
                for i in range(beats)
            ],
            "climax": "Join them.",
            "climax_image_prompt": "scene climax, a long table",
        },
        "ground.system": {"unsupported": [], "all_supported": True},
    })


@dataclass
class FakeMedia:
    """The media seam, recording what rode each image call — the references are
    the whole subject of this suite, so they are what it captures."""

    image_calls: list = field(default_factory=list)
    reference_calls: list = field(default_factory=list)

    def transcribe(self, data: bytes, mime: str):
        raise AssertionError("a reference photo must never be transcribed")

    def generate_image(self, prompt: str, references=None):
        self.image_calls.append(prompt)
        self.reference_calls.append(list(references or []))
        return b"\x89PNG\r\n\x1a\n" + str(len(self.image_calls)).encode(), Usage(
            provider="google", model="gemini-3.1-flash-image",
            input_tokens=20, output_tokens=0,
        )


def _reference(db, settings, wedding, *, consented=True, data=PNG) -> AiInput:
    """A reference photo as the upload endpoint would have stored it."""
    url = storage.store_ai_input(settings, wedding.slug, data, "png", "image/png")
    inp = AiInput(
        wedding_id=wedding.id, kind="image", role="reference",
        storage_url=url, mime="image/png", bytes=len(data),
        consent_at=utcnow() if consented else None,
        consent_by="owner-sub" if consented else None,
    )
    db.add(inp)
    db.commit()
    return inp


def _reviewable(db, s, w, *, fake=None, options=None) -> AiJob:
    inp = AiInput(wedding_id=w.id, kind="text", text_content="We're Alex and Sam.")
    db.add(inp)
    db.commit()
    job = create_job(db, s, w, kind="story_arc", input_ids=[inp.id], options=options)
    fake = fake or _fake_text()
    for _ in range(job.steps_total + 2):
        job = advance_job(db, s, job, text_model=fake)
        if job.status == "awaiting_review":
            break
    assert job.status == "awaiting_review"
    return job


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------
def test_likeness_is_off_by_default():
    """The default plan does not put pictures of couples through an image model.
    Someone has to turn this on, per wedding, deliberately."""
    assert DEFAULT_ENTITLEMENTS["ai_likeness_enabled"] is False


def test_upload_without_the_box_ticked_is_refused(db_session, make_client):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-consent")
    make_member(db_session, w, OWNER, "owner")
    client = make_client(gemini_api_key="test-gemini-key")

    r = client.post(
        f"/api/w/{w.slug}/admin/ai/inputs/upload",
        files={"file": ("us.png", PNG, "image/png")},
        data={"role": "reference"},  # no consent
        headers=user_auth(OWNER),
    )
    assert r.status_code == 422
    assert "without your say-so" in r.json()["detail"]
    # And nothing was stored: a refusal must not leave the photo behind.
    assert db_session.execute(select(AiInput)).scalars().all() == []


def test_consent_is_recorded_on_the_photo_itself(db_session, make_client):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-consent-ok")
    make_member(db_session, w, OWNER, "owner")
    client = make_client(gemini_api_key="test-gemini-key")

    r = client.post(
        f"/api/w/{w.slug}/admin/ai/inputs/upload",
        files={"file": ("us.png", PNG, "image/png")},
        data={"role": "reference", "consent": "true"},
        headers=user_auth(OWNER),
    )
    assert r.status_code == 201, r.text
    inp = db_session.execute(select(AiInput)).scalars().one()
    assert inp.role == "reference" and inp.kind == "image"
    assert inp.consent_at is not None and inp.consent_by  # who, and when
    assert (w.storage_bytes_used or 0) == 0  # ai-inputs never meter


def test_a_reference_must_be_an_image_and_needs_the_entitlement(db_session, make_client):
    _enable_ai(db_session, ai_likeness_enabled=False)
    w = make_wedding(db_session, "wed-ref-gate")
    make_member(db_session, w, OWNER, "owner")
    client = make_client(gemini_api_key="test-gemini-key")
    url = f"/api/w/{w.slug}/admin/ai/inputs/upload"

    # Feature off for this plan → 403, not a stored photo.
    r = client.post(url, files={"file": ("us.png", PNG, "image/png")},
                    data={"role": "reference", "consent": "true"}, headers=user_auth(OWNER))
    assert r.status_code == 403

    plan = db_session.execute(select(Plan)).scalars().one()
    plan.entitlements = dict(plan.entitlements, ai_likeness_enabled=True)
    db_session.commit()

    # A voice note is not a photo of you.
    r = client.post(url, files={"file": ("us.mp3", b"audio", "audio/mpeg")},
                    data={"role": "reference", "consent": "true"}, headers=user_auth(OWNER))
    assert r.status_code == 422 and "needs to be an image" in r.json()["detail"]

    # And an unknown role can't smuggle anything through.
    r = client.post(url, files={"file": ("us.png", PNG, "image/png")},
                    data={"role": "training", "consent": "true"}, headers=user_auth(OWNER))
    assert r.status_code == 422 and "Unknown upload role" in r.json()["detail"]


def test_an_unconsented_photo_can_never_be_attached(db_session):
    """The one that matters: even with a valid id, a row whose consent was never
    recorded is 404 — indistinguishable from a photo that doesn't exist."""
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-noconsent")
    s = _settings()
    job = _reviewable(db_session, s, w)
    sneaky = _reference(db_session, s, w, consented=False)

    with pytest.raises(HTTPException) as exc:
        set_references(db_session, s, job, input_ids=[sneaky.id])
    assert exc.value.status_code == 404


def test_references_are_scoped_to_the_wedding(db_session):
    _enable_ai(db_session)
    mine = make_wedding(db_session, "wed-mine")
    theirs = make_wedding(db_session, "wed-theirs")
    s = _settings()
    job = _reviewable(db_session, s, mine)
    other = _reference(db_session, s, theirs)

    with pytest.raises(HTTPException) as exc:
        set_references(db_session, s, job, input_ids=[other.id])
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# The photos reach the image model — and nothing else
# ---------------------------------------------------------------------------
def test_consented_photos_ride_the_image_call_and_nothing_else(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-refs")
    s = _settings()
    fake = _fake_text()
    job = _reviewable(db_session, s, w, fake=fake)
    photo = _reference(db_session, s, w)

    job = set_references(db_session, s, job, input_ids=[photo.id])
    assert job.proposal["likeness"] == {"references": 1}

    media = FakeMedia()
    job = illustrate(db_session, s, job, targets=["0"], media_model=media)

    # The photo bytes went to the image model…
    assert media.reference_calls == [[(PNG, "image/png")]]
    # …and the prompt asks for a LIKENESS instead of the faceless-figures rule.
    prompt = media.image_calls[0]
    assert "resemble them" in prompt
    assert "faceless" not in prompt
    # …and the text model never saw a photo at all: it was never transcribed,
    # so it isn't in the submission the draft was written from.
    draft = next(c for c in fake.calls if c.prompt.key == "draft_arc.system")
    assert "photo" not in draft.prompt.user.lower()
    assert job.proposal["beat_images"]["0"]


def test_no_references_keeps_the_faceless_rule(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-norefs")
    s = _settings()
    job = _reviewable(db_session, s, w)

    media = FakeMedia()
    illustrate(db_session, s, job, targets=["0"], media_model=media)
    assert media.reference_calls == [[]]
    assert "faceless" in media.image_calls[0]
    assert "resemble them" not in media.image_calls[0]


def test_a_redo_of_a_panel_keeps_the_couple_in_it(db_session):
    """A regenerated panel must not quietly come back with strangers."""
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-redo")
    s = _settings()
    job = _reviewable(db_session, s, w)
    photo = _reference(db_session, s, w)
    job = set_references(db_session, s, job, input_ids=[photo.id])
    media = FakeMedia()
    job = illustrate(db_session, s, job, targets=["0"], media_model=media)

    regenerate_artifact(
        db_session, s, job, artifact="arc.beat.0", steer="brighter",
        text_model=_fake_text(), media_model=media,
    )
    assert media.reference_calls[-1] == [(PNG, "image/png")]
    assert "resemble them" in media.image_calls[-1]


# ---------------------------------------------------------------------------
# Stylised only
# ---------------------------------------------------------------------------
def test_the_photographic_style_is_refused_while_photos_are_attached(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-style-block")
    s = _settings()
    job = _reviewable(db_session, s, w)
    photo = _reference(db_session, s, w)
    job = set_references(db_session, s, job, input_ids=[photo.id])

    with pytest.raises(HTTPException) as exc:
        edit_proposal(db_session, job, style_preset="hyper_realistic")
    assert exc.value.status_code == 422
    assert "stay stylised" in exc.value.detail

    # The other way round is refused too: photos can't be attached to a run
    # that's already set to the photographic look.
    other = make_wedding(db_session, "wed-style-block-2")
    photoreal = _reviewable(db_session, s, other, options={"style_preset": "hyper_realistic"})
    ref2 = _reference(db_session, s, other)
    with pytest.raises(HTTPException) as exc:
        set_references(db_session, s, photoreal, input_ids=[ref2.id])
    assert exc.value.status_code == 422

    # A watercolour of the two of them is fine — the block is on realism, not
    # on likeness.
    job = edit_proposal(db_session, job, style_preset="watercolor")
    assert job.proposal["style"]["preset"] == "watercolor"


def test_a_blocked_style_never_renders_photoreal_even_if_it_gets_stored(db_session):
    """Belt to check_style's braces: compose the prompt directly from options
    that (somehow) pair references with the blocked preset, and it comes out in
    the default stylised look — not refused, and not photorealistic."""
    assert "hyper_realistic" in BLOCKED_LIKENESS_STYLES
    options = {"style_preset": "hyper_realistic"}

    without = compose_image_prompt("a picnic", options, has_references=False)
    assert "photographic image" in without

    with_refs = compose_image_prompt("a picnic", options, has_references=True)
    assert "photographic image" not in with_refs
    assert "storybook" in with_refs  # DEFAULT_STYLE
    assert "never as a photograph" in with_refs


def test_the_plan_cap_holds_even_for_photos_claimed_at_job_creation(db_session):
    """`create_job` claims inputs by id and can't tell a reference from a voice
    note, so the cap can't live only at the references endpoint. The render path
    is where every photo must pass, so that is where it's enforced."""
    _enable_ai(db_session, ai_max_likeness_references=2)
    w = make_wedding(db_session, "wed-cap")
    s = _settings()
    text = AiInput(wedding_id=w.id, kind="text", text_content="We're Alex and Sam.")
    db_session.add(text)
    db_session.commit()
    photos = [_reference(db_session, s, w, data=PNG + bytes([i])) for i in range(4)]

    job = create_job(
        db_session, s, w, kind="story_arc",
        input_ids=[text.id, *[p.id for p in photos]],  # straight past the endpoint
    )
    fake = _fake_text()
    for _ in range(job.steps_total + 2):
        job = advance_job(db_session, s, job, text_model=fake)
        if job.status == "awaiting_review":
            break

    media = FakeMedia()
    illustrate(db_session, s, job, targets=["0"], media_model=media)
    assert len(media.reference_calls[0]) == 2  # not 4


# ---------------------------------------------------------------------------
# Switching it off, and cleaning up
# ---------------------------------------------------------------------------
def test_revoking_the_plan_stops_the_illustration_with_a_way_out(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-revoke")
    s = _settings()
    job = _reviewable(db_session, s, w)
    photo = _reference(db_session, s, w)
    job = set_references(db_session, s, job, input_ids=[photo.id])

    plan = db_session.execute(select(Plan)).scalars().one()
    plan.entitlements = dict(plan.entitlements, ai_likeness_enabled=False)
    db_session.commit()

    media = FakeMedia()
    with pytest.raises(HTTPException) as exc:
        illustrate(db_session, s, job, targets=["0"], media_model=media)
    assert exc.value.status_code == 403
    assert "remove your photos" in exc.value.detail
    assert media.image_calls == []  # nothing rendered, nothing charged

    # The way out works WITH THE FEATURE STILL OFF — that is the whole point:
    # the illustrate endpoint just told them to remove the photos, and a removal
    # that 403s because the plan lost the feature is not a way out.
    url = photo.storage_url
    job = set_references(db_session, s, job, input_ids=[])
    assert job.proposal["likeness"] == {"references": 0}
    assert db_session.get(AiInput, photo.id) is None
    with pytest.raises(storage.UploadError):
        storage.load_media_bytes(s, url)  # the photo itself, gone

    job = illustrate(db_session, s, job, targets=["0"], media_model=media)
    assert media.reference_calls == [[]]  # scenes, no couple


def test_a_reference_never_outlives_its_run(db_session):
    """Cancel and apply are terminal for a photo of someone's face: the row goes,
    and the stored object goes with it."""
    _enable_ai(db_session)
    s = _settings()

    w = make_wedding(db_session, "wed-cancel-ref")
    job = _reviewable(db_session, s, w)
    photo = _reference(db_session, s, w)
    set_references(db_session, s, job, input_ids=[photo.id])
    cancelled_url = photo.storage_url
    cancel_job(db_session, s, job)
    assert db_session.get(AiInput, photo.id) is None
    with pytest.raises(storage.UploadError):
        storage.load_media_bytes(s, cancelled_url)

    w2 = make_wedding(db_session, "wed-apply-ref")
    job2 = _reviewable(db_session, s, w2)
    photo2 = _reference(db_session, s, w2)
    job2 = set_references(db_session, s, job2, input_ids=[photo2.id])
    media = FakeMedia()
    job2 = illustrate(db_session, s, job2, targets=["0"], media_model=media)
    applied_url = photo2.storage_url
    kept_art = job2.proposal["beat_images"]["0"]
    result = apply_proposal(db_session, s, w2, job2)
    assert "story_arc" in result["applied"]
    assert db_session.get(AiInput, photo2.id) is None
    with pytest.raises(storage.UploadError):
        storage.load_media_bytes(s, applied_url)
    # The ILLUSTRATION it produced survives — that's the thing they bought.
    assert w2.story_arcs[0].content["beats"][0]["image"] == kept_art
    assert storage.load_media_bytes(s, kept_art)


# ---------------------------------------------------------------------------
# HTTP: the endpoint, and its authz line
# ---------------------------------------------------------------------------
def test_references_endpoint_over_http_and_its_authz(db_session, make_client):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-http-ref")
    make_member(db_session, w, OWNER, "owner")
    client = make_client(gemini_api_key="test-gemini-key")
    fake = _fake_text()
    media = FakeMedia()
    app.dependency_overrides[get_job_text_model] = lambda: fake
    app.dependency_overrides[get_job_media_model] = lambda: media
    base = f"/api/w/{w.slug}/admin/ai"
    auth = user_auth(OWNER)

    # The UI is told it may offer the control at all.
    credits = client.get(f"{base}/credits", headers=auth).json()
    assert credits["likeness_available"] is True
    assert credits["max_likeness_references"] == 3
    styles = client.get(f"{base}/styles", headers=auth).json()
    assert {"key": "hyper_realistic", "label": "Photographic", "likeness_blocked": True} in styles

    r = client.post(f"{base}/inputs", json={"text": "our story"}, headers=auth)
    r = client.post(f"{base}/jobs", json={"kind": "story_arc", "input_ids": [r.json()["id"]]},
                    headers=auth)
    job = r.json()
    for _ in range(job["steps_total"] + 2):
        job = client.post(f"{base}/jobs/{job['id']}/advance", headers=auth).json()
        if job["status"] not in ("queued", "running"):
            break
    assert job["status"] == "awaiting_review"

    up = client.post(
        f"{base}/inputs/upload",
        files={"file": ("us.png", PNG, "image/png")},
        data={"role": "reference", "consent": "true"},
        headers=auth,
    )
    assert up.status_code == 201

    refs = f"{base}/jobs/{job['id']}/references"
    assert client.post(refs, json={"input_ids": [up.json()["id"]]}).status_code == 401
    assert client.post(refs, json={"input_ids": [up.json()["id"]]},
                       headers=user_auth(STRANGER)).status_code == 404

    r = client.post(refs, json={"input_ids": [up.json()["id"]]}, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["proposal"]["likeness"] == {"references": 1}

    r = client.post(f"{base}/jobs/{job['id']}/illustrate", json={"targets": ["0"]}, headers=auth)
    assert r.status_code == 200, r.text
    assert media.reference_calls == [[(PNG, "image/png")]]

    app.dependency_overrides.clear()
