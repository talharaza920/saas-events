"""Phase 8.5b — the staged story wizard.

What 8.5b actually promises, and therefore what these pin:

* a `story_arc` run parks at review as TEXT (no image call, no image credit);
* the couple can EDIT the draft for free, and their words lose the model's
  grounding flags rather than keeping a receipt nobody asked for;
* images are an explicit click: beat 0 first, the rest on demand, 1 credit
  each, and a cancelled run refunds all of it;
* the style is an allowlisted key + an untrusted note, and the note can only
  reach an image prompt — never a system prompt, never the story text.

Offline throughout (scripted text model, stubbed media seam, tmp storage), and
each endpoint carries its 401/404 line per CLAUDE.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fastapi import HTTPException

import app.storage as storage
from app.ai.edit import edit_proposal
from app.ai.images import illustrate, illustration_targets, pending_targets
from app.ai.jobs import advance_job, create_job
from app.ai.media import FakePainter, get_media_model, sniff_image_mime
from app.ai.pricing import cost_usd_micros
from app.ai.providers.fake import FakeTextModel
from app.ai.styles import STYLE_PRESETS, compose_image_prompt
from app.ai.types import ProviderRefusal, Usage
from app.config import Settings
from app.main import app
from app.models import AiInput, AiJob, Plan
from app.routers.ai_admin import get_job_media_model, get_job_text_model
from tests.helpers import DEV_TOKEN, make_member, make_wedding, user_auth

OWNER = "owner@example.com"
STRANGER = "stranger@example.com"

AI_ENTS = {
    "ai_enabled": True,
    "ai_credits_included": 20,
    "ai_arc_generations_included": 1,
    "ai_max_inputs_per_job": 12,
    "ai_max_regens_per_artifact": 3,
    "ai_max_images_per_arc": 6,
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
            "intro": "Six years and a patient cat.",
            "beats": [
                {"text": f"Beat {i}.", "image_prompt": f"scene {i}, warm light"}
                for i in range(beats)
            ],
            "climax": "Join them.",
            "climax_image_prompt": "a long table under strung lights",
        },
        "ground.system": {
            "unsupported": [
                {"draft_text": "Six years and a patient cat.",
                 "reason": "The submission never says how long."},
                {"draft_text": "Beat 1.", "reason": "No support for this."},
            ],
            "all_supported": False,
        },
    })


@dataclass
class FakeMedia:
    refuse_image_prompts: tuple[str, ...] = ()
    image_calls: list = field(default_factory=list)

    def transcribe(self, data: bytes, mime: str):  # pragma: no cover - text inputs only
        raise AssertionError("no media inputs in these tests")

    def generate_image(self, prompt: str):
        self.image_calls.append(prompt)
        if any(m in prompt for m in self.refuse_image_prompts):
            raise ProviderRefusal("content filter")
        return b"png-" + str(len(self.image_calls)).encode(), Usage(
            provider="google", model="gemini-3.1-flash-image",
            input_tokens=20, output_tokens=0,
        )


def _reviewable(db, s, w, *, beats=2, fake=None, options=None) -> AiJob:
    inp = AiInput(wedding_id=w.id, kind="text", text_content="We're Alex and Sam.")
    db.add(inp)
    db.commit()
    job = create_job(db, s, w, kind="story_arc", input_ids=[inp.id], options=options)
    fake = fake or _fake_text(beats=beats)
    for _ in range(job.steps_total):
        job = advance_job(db, s, job, text_model=fake)
        if job.status == "awaiting_review":
            break
    assert job.status == "awaiting_review"
    return job


# ---------------------------------------------------------------------------
# Text first: the run costs no image money at all
# ---------------------------------------------------------------------------
def test_story_run_parks_text_only_and_lists_its_panels(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-staged")
    s = _settings()
    media = FakeMedia()
    job = _reviewable(db_session, s, w, beats=3)

    assert media.image_calls == []
    assert job.proposal["beat_images"] == {}
    assert (w.storage_bytes_used or 0) == 0
    # The climax is a panel like any other — it is illustrated, and it is last.
    assert [k for k, _ in illustration_targets(job.proposal)] == ["0", "1", "2", "climax"]
    assert pending_targets(job) == ["0", "1", "2", "climax"]


# ---------------------------------------------------------------------------
# Style: an allowlisted key + an untrusted note, image prompts only
# ---------------------------------------------------------------------------
def test_style_preset_and_note_shape_only_the_image_prompt(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-style")
    s = _settings()
    fake = _fake_text()
    media = FakeMedia()
    job = _reviewable(
        db_session, s, w, fake=fake,
        options={"style_preset": "watercolor", "style_note": "lots of blue"},
    )
    # The story text never learns about the style: the draft call's user turn
    # carries the tone, not the illustration style.
    draft_call = next(c for c in fake.calls if c.prompt.key == "draft_arc.system")
    assert "watercolor" not in draft_call.prompt.user
    assert "lots of blue" not in draft_call.prompt.user

    job = illustrate(db_session, s, job, targets=["0"], media_model=media)
    prompt = media.image_calls[0]
    assert STYLE_PRESETS["watercolor"].description.split(":")[0].lower() in prompt.lower()
    assert "lots of blue" in prompt
    # The guardrails come after the couple's words, so a note can't talk past them.
    assert prompt.index("lots of blue") < prompt.index("No recognisable real people")


def test_unknown_style_key_falls_back_instead_of_failing(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-style-bad")
    s = _settings()
    job = _reviewable(db_session, s, w, options={"style_preset": "hologram"})
    assert job.proposal["style"]["preset"] == "storybook"  # the default, not an error
    assert "storybook" in compose_image_prompt("a scene", {"style_preset": "hologram"}).lower()


def test_style_can_be_changed_at_review_without_touching_the_text(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-restyle")
    s = _settings()
    media = FakeMedia()
    job = _reviewable(db_session, s, w)
    before = dict(job.proposal["story_arc"])

    job = edit_proposal(db_session, job, style_preset="anime", style_note="dusk tones")
    assert job.proposal["style"] == {"preset": "anime", "note": "dusk tones"}
    assert job.proposal["story_arc"] == before  # not a word moved

    illustrate(db_session, s, job, targets=["0"], media_model=media)
    assert "anime" in media.image_calls[0].lower()

    with pytest.raises(HTTPException) as exc:
        edit_proposal(db_session, job, style_preset="not-a-style")
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# Direct edits: free, bounded, and they drop the model's grounding flags
# ---------------------------------------------------------------------------
def test_editing_a_beat_flags_it_and_drops_its_grounding_claim(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-edit")
    s = _settings()
    job = _reviewable(db_session, s, w)
    assert len(job.proposal["grounding"]["unsupported"]) == 2

    arc = dict(job.proposal["story_arc"])
    arc["beats"] = [dict(b) for b in arc["beats"]]
    arc["beats"][1]["text"] = "We eloped to the kitchen and burnt the pancakes."
    job = edit_proposal(db_session, job, story_arc=arc)

    assert job.proposal["story_arc"]["beats"][1]["text"].startswith("We eloped")
    assert job.proposal["user_edited"] == ["beats.1.text"]
    # The claim about the rewritten line is gone (their own words need no
    # receipt); the claim about the untouched intro is still there.
    claims = [c["draft_text"] for c in job.proposal["grounding"]["unsupported"]]
    assert claims == ["Six years and a patient cat."]
    assert job.proposal["grounding"]["all_supported"] is False


def test_edits_revalidate_through_the_draft_schema(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-edit-bad")
    s = _settings()
    job = _reviewable(db_session, s, w)

    for bad in (
        {"heading": "x" * 200, "beats": [{"text": "a", "image_prompt": "b"}]},  # too long
        {"heading": "Fine", "beats": []},  # no beats
        {"heading": "Fine", "beats": [{"text": "a", "image_prompt": "b"}],
         "sneaky": "extra"},  # extra=forbid
    ):
        with pytest.raises(HTTPException) as exc:
            edit_proposal(db_session, job, story_arc=bad)
        assert exc.value.status_code == 422
    assert job.proposal["story_arc"]["heading"] == "Alex & Sam"  # untouched


def test_editing_a_scene_unpairs_its_now_stale_art(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-edit-img")
    s = _settings()
    job = _reviewable(db_session, s, w)
    job = illustrate(db_session, s, job, targets=["0", "1"], media_model=FakeMedia())
    assert set(job.proposal["beat_images"]) == {"0", "1"}

    arc = dict(job.proposal["story_arc"])
    arc["beats"] = [dict(b) for b in arc["beats"]]
    arc["beats"][0]["image_prompt"] = "a completely different scene"
    job = edit_proposal(db_session, job, story_arc=arc)
    # Beat 0's art illustrated a scene that no longer exists; beat 1 is intact.
    assert set(job.proposal["beat_images"]) == {"1"}
    assert pending_targets(job) == ["0", "climax"]


# ---------------------------------------------------------------------------
# Metering: 1 credit per image, and a cancelled run refunds every one of them
# ---------------------------------------------------------------------------
def test_images_charge_one_credit_each_and_stop_at_the_balance(db_session):
    # 3 held by the text run + 2 images = 5, the wedding's whole balance.
    _enable_ai(db_session, ai_credits_included=5, ai_arc_generations_included=0)
    w = make_wedding(db_session, "wed-credits")
    s = _settings()
    media = FakeMedia()
    job = _reviewable(db_session, s, w, beats=3)
    assert job.credits_held == 3

    job = illustrate(db_session, s, job, media_model=media)  # beats 0, 1
    assert job.credits_held == 5 and len(job.proposal["beat_images"]) == 2

    with pytest.raises(HTTPException) as exc:  # nothing left for beat 2
        illustrate(db_session, s, job, media_model=media)
    assert exc.value.status_code == 403 and "credits" in exc.value.detail
    assert len(media.image_calls) == 2  # the refusal is BEFORE the provider call


# ---------------------------------------------------------------------------
# HTTP surface: authz matrix + the couple's happy path end to end
# ---------------------------------------------------------------------------
@pytest.fixture()
def http(db_session, make_client):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-http")
    make_member(db_session, w, OWNER, "owner")
    client = make_client(gemini_api_key="test-gemini-key")
    fake, media = _fake_text(beats=2), FakeMedia()
    app.dependency_overrides[get_job_text_model] = lambda: fake
    app.dependency_overrides[get_job_media_model] = lambda: media
    yield client, w, media
    app.dependency_overrides.pop(get_job_text_model, None)
    app.dependency_overrides.pop(get_job_media_model, None)


def _run(client, w) -> str:
    r = client.post(f"/api/w/{w.slug}/admin/ai/inputs",
                    json={"text": "We're Alex and Sam."}, headers=user_auth(OWNER))
    job = client.post(
        f"/api/w/{w.slug}/admin/ai/jobs",
        json={"kind": "story_arc", "input_ids": [r.json()["id"]]},
        headers=user_auth(OWNER),
    ).json()
    while job["status"] in ("queued", "running"):
        job = client.post(
            f"/api/w/{w.slug}/admin/ai/jobs/{job['id']}/advance",
            json={"expected_step": job["step"]}, headers=user_auth(OWNER),
        ).json()
    assert job["status"] == "awaiting_review"
    return job["id"]


def test_staged_endpoints_authz_matrix(http):
    client, w, _ = http
    job_id = _run(client, w)
    for method, path, body in (
        ("GET", "styles", None),
        ("PATCH", f"jobs/{job_id}/proposal", {"style_preset": "anime"}),
        ("POST", f"jobs/{job_id}/illustrate", {"targets": ["0"]}),
    ):
        url = f"/api/w/{w.slug}/admin/ai/{path}"
        kwargs = {"json": body} if body is not None else {}
        assert client.request(method, url, **kwargs).status_code == 401  # unauthenticated
        # A non-member gets the same 404 as a wedding that never existed.
        r = client.request(method, url, headers=user_auth(STRANGER), **kwargs)
        assert r.status_code == 404


def test_the_couples_path_confirm_then_first_image_then_the_rest(http):
    client, w, media = http
    job_id = _run(client, w)
    base = f"/api/w/{w.slug}/admin/ai/jobs/{job_id}"

    styles = client.get(f"/api/w/{w.slug}/admin/ai/styles", headers=user_auth(OWNER)).json()
    assert {"key": "storybook", "label": "Storybook"} in styles

    # 1. Fix a line and pick a style — free, no provider call.
    job = client.get(base, headers=user_auth(OWNER)).json()
    arc = job["proposal"]["story_arc"]
    arc["beats"][0]["text"] = "They met under one umbrella."
    job = client.patch(
        base + "/proposal",
        json={"story_arc": arc, "style_preset": "line_art"},
        headers=user_auth(OWNER),
    ).json()
    assert job["proposal"]["user_edited"] == ["beats.0.text"]
    assert media.image_calls == []
    assert job["credits_held"] == 0  # editing is free (and this arc was too)

    # 2. Illustrate beat 0 only, and iterate the style on that one image.
    job = client.post(base + "/illustrate", json={"targets": ["0"]},
                      headers=user_auth(OWNER)).json()
    assert list(job["proposal"]["beat_images"]) == ["0"]
    assert job["credits_held"] == 1  # 1 credit for the image
    first_image = job["proposal"]["beat_images"]["0"]

    variant = client.post(base + "/regenerate",
                          json={"artifact": "arc.beat.0", "steer": "brighter"},
                          headers=user_auth(OWNER)).json()
    assert variant["image_url"] and variant["image_url"] != first_image
    assert "brighter" in media.image_calls[-1]  # steer rides the image prompt

    # 3. Then the rest, including the climax panel.
    job = client.post(base + "/illustrate", json={}, headers=user_auth(OWNER)).json()
    assert set(job["proposal"]["beat_images"]) == {"0", "1", "climax"}

    applied = client.post(base + "/apply", json={"selections": ["story_arc"]},
                          headers=user_auth(OWNER)).json()
    assert applied["applied"] == ["story_arc"]
    arc_row = w.story_arcs[0].content
    assert arc_row["beats"][0]["text"] == "They met under one umbrella."
    assert arc_row["climax"]["image"]


def test_the_dev_painter_never_exists_in_production():
    """AI_FAKE_IMAGES paints placeholders so the wizard can be demoed offline.
    A real wedding must never get one, so production can't construct it — the
    same stance as the dev admin token."""
    dev = _settings(ai_fake_images=True, gemini_api_key="")
    assert dev.ai_images_available and not dev.ai_images_enabled
    assert isinstance(get_media_model(dev), FakePainter)

    prod = _settings(environment="production", ai_fake_images=True, gemini_api_key="")
    assert not prod.ai_images_available
    assert not isinstance(get_media_model(prod), FakePainter)

    # A real key is never shadowed by the painter, dev or not.
    real = _settings(ai_fake_images=True, gemini_api_key="k")
    assert not isinstance(get_media_model(real), FakePainter)

    # It paints something the storage path will actually accept, and its usage
    # row is well-formed and free — the rest of the suite stubs the media seam,
    # so this is the only place the painter's real output is exercised.
    data, usage = get_media_model(dev).generate_image("a rainy bus stop")
    blob, ext = storage.prepare_image(data, sniff_image_mime(data))
    assert blob and ext == "png"
    assert usage.provider == "fake" and cost_usd_micros(usage) == 0


def test_illustrating_a_panel_that_has_no_scene_is_422(http):
    client, w, _ = http
    job_id = _run(client, w)
    r = client.post(
        f"/api/w/{w.slug}/admin/ai/jobs/{job_id}/illustrate",
        json={"targets": ["7"]}, headers=user_auth(OWNER),
    )
    assert r.status_code == 422
