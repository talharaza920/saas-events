"""Phase 8.1c: the Gemini media seam, the Nano Banana images fan-out, and the
`guests` kind.

Everything runs offline: the text model is the scripted FakeTextModel and the
media seam is a stub with the same two-method surface as GeminiMedia (the
real adapter's request shape is pinned separately with an injected SDK-client
stub). Storage is a tmp dir. Per CLAUDE.md, the new endpoint ships with its
401/404 matrix, and the guests tests pin the invite-tier secret: the model
returns raw lines, tiers are computed in code, and a tampered proposal tier
is ignored at apply time.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import app.storage as storage
from app.ai.apply import apply_proposal
from app.ai.images import illustrate, pending_targets
from app.ai.jobs import advance_job, cancel_job, create_job
from app.ai.media import GeminiMedia, transcribe_input
from app.ai.pricing import cost_usd_micros
from app.ai.providers.fake import FakeTextModel
from app.ai.types import ProviderRefusal, Usage
from app.ai.variants import regenerate_artifact, select_variant
from app.config import Settings
from app.main import app
from app.models import AiInput, AiJob, AiUsageLedger, AiVariant, Guest, Plan
from app.routers.ai_admin import get_job_media_model, get_job_text_model
from tests.helpers import DEV_TOKEN, make_member, make_wedding, user_auth

OWNER = "owner@example.com"
STRANGER = "stranger@example.com"

AI_ENTS = {
    "ai_enabled": True,
    "ai_credits_included": 10,
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


def _enable_ai(db, **entitlement_overrides) -> None:
    ents = dict(AI_ENTS)
    ents.update(entitlement_overrides)
    db.add(Plan(name="ai-test-plan", is_default=True, entitlements=ents))
    db.commit()


def _fake_text(beats: int = 3) -> FakeTextModel:
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
        "extract_guests.system": {
            "lines": [
                "Jordan Lee",
                "Riley Park",
                "Riley Park +1",
                "Casey Nguyen",
                "Casey Nguyen +1",
                "Kid (Casey Nguyen)",
                "Sasha Chen +1",  # companion with no primary row → unresolved
            ]
        },
    })


@dataclass
class FakeMedia:
    """Same two-call surface as GeminiMedia; deterministic, offline."""

    transcript: str = "voice note says: married at Fern Hall"
    refuse_transcribe: bool = False
    refuse_image_prompts: tuple[str, ...] = ()
    image_calls: list = field(default_factory=list)
    # What likeness references (8.5d) rode each image call — [] on every call
    # unless the couple attached consented photos of themselves.
    reference_calls: list = field(default_factory=list)

    def transcribe(self, data: bytes, mime: str):
        if self.refuse_transcribe:
            raise ProviderRefusal("blocked content")
        return self.transcript, Usage(
            provider="google", model="gemini-3.5-flash",
            input_tokens=1000, output_tokens=100, request_id="g-1",
        )

    def generate_image(self, prompt: str, references=None):
        self.image_calls.append(prompt)
        self.reference_calls.append(list(references or []))
        if any(marker in prompt for marker in self.refuse_image_prompts):
            raise ProviderRefusal("content filter")
        return b"fake-png-bytes-" + str(len(self.image_calls)).encode(), Usage(
            provider="google", model="gemini-3.1-flash-image",
            input_tokens=20, output_tokens=0, request_id=f"g-img-{len(self.image_calls)}",
        )


def _add_text_input(db, wedding, text: str = "We're Alex and Sam.") -> AiInput:
    inp = AiInput(wedding_id=wedding.id, kind="text", text_content=text)
    db.add(inp)
    db.commit()
    return inp


def _run_to_review(db, settings, job, fake, media=None) -> AiJob:
    for _ in range(job.steps_total + 2):
        job = advance_job(db, settings, job, text_model=fake, media_model=media)
        if job.status not in ("queued", "running"):
            break
    return job


def _ledger(db, kind: str) -> list[AiUsageLedger]:
    return db.execute(
        select(AiUsageLedger).where(AiUsageLedger.kind == kind)
    ).scalars().all()


# ---------------------------------------------------------------------------
# Media inputs: upload endpoint
# ---------------------------------------------------------------------------
def _upload(client, w, *, name="note.mp3", mime="audio/mpeg", data=b"audio-bytes",
            headers=None):
    return client.post(
        f"/api/w/{w.slug}/admin/ai/inputs/upload",
        files={"file": (name, data, mime)},
        headers=headers or user_auth(OWNER),
    )


def test_upload_media_input_stores_file_and_row(db_session, make_client):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-up")
    make_member(db_session, w, OWNER, "owner")
    client = make_client(gemini_api_key="test-gemini-key")

    r = _upload(client, w)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "audio" and body["bytes"] == len(b"audio-bytes")
    inp = db_session.get(AiInput, __import__("uuid").UUID(body["id"]))
    assert inp.storage_url and "/media/ai-inputs/wed-up/" in inp.storage_url
    assert inp.mime == "audio/mpeg"
    # The bytes are really there, under the transient (unmetered) namespace.
    assert storage.load_media_bytes(_settings(), inp.storage_url) == b"audio-bytes"
    assert (w.storage_bytes_used or 0) == 0  # ai-inputs never meter


def test_upload_rejects_bad_type_oversize_and_missing_key(db_session, make_client):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-upbad")
    make_member(db_session, w, OWNER, "owner")
    client = make_client(gemini_api_key="test-gemini-key")

    r = _upload(client, w, name="x.exe", mime="application/x-msdownload")
    assert r.status_code == 422 and "Unsupported file type" in r.json()["detail"]

    r = _upload(client, w, data=b"0" * (storage.MAX_AI_MEDIA_BYTES + 1))
    assert r.status_code == 422 and "too large" in r.json()["detail"]

    no_key = make_client(gemini_api_key="")
    r = _upload(no_key, w)
    assert r.status_code == 422 and "paste text instead" in r.json()["detail"]


def test_upload_endpoint_401_unauth_404_nonmember(db_session, make_client):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-upauth")
    make_member(db_session, w, OWNER, "owner")
    client = make_client(gemini_api_key="test-gemini-key")
    r = client.post(
        f"/api/w/{w.slug}/admin/ai/inputs/upload",
        files={"file": ("a.mp3", b"x", "audio/mpeg")},
    )
    assert r.status_code == 401
    r = _upload(client, w, headers=user_auth(STRANGER))
    assert r.status_code == 404  # existence never revealed


# ---------------------------------------------------------------------------
# Transcription through the pipeline
# ---------------------------------------------------------------------------
def _media_input(db, settings, w, *, mime="audio/mpeg", kind="audio") -> AiInput:
    url = storage.store_ai_input(settings, w.slug, b"raw-media", "mp3", mime)
    inp = AiInput(wedding_id=w.id, kind=kind, storage_url=url, mime=mime, bytes=9)
    db.add(inp)
    db.commit()
    return inp


def test_transcribe_media_input_feeds_pipeline_and_ledgers(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-tr")
    s = _settings()
    inp = _media_input(db_session, s, w)
    media = FakeMedia()
    job = create_job(db_session, s, w, kind="story_arc", input_ids=[inp.id])
    job = advance_job(db_session, s, job, text_model=_fake_text(), media_model=media)
    assert job.status == "running" and job.step == 1
    assert "Fern Hall" in job.state["submission"]
    rows = _ledger(db_session, "transcribe")
    assert len(rows) == 1 and rows[0].provider == "google"
    assert rows[0].model == "gemini-3.5-flash" and rows[0].cost_usd_micros > 0


def test_transcribe_without_key_or_refused_fails_job_and_sweeps(db_session, tmp_path):
    _enable_ai(db_session)
    s = _settings()

    w1 = make_wedding(db_session, "wed-tr-nokey")
    inp = _media_input(db_session, s, w1)
    job = create_job(db_session, s, w1, kind="story_arc", input_ids=[inp.id])
    no_key = _settings(gemini_api_key="")
    job = advance_job(db_session, no_key, job, text_model=_fake_text())
    assert job.status == "failed" and "GEMINI_API_KEY" in job.error

    w2 = make_wedding(db_session, "wed-tr-refuse")
    inp2 = _media_input(db_session, s, w2)
    url2 = inp2.storage_url
    job2 = create_job(db_session, s, w2, kind="story_arc", input_ids=[inp2.id])
    job2 = advance_job(db_session, s, job2, text_model=_fake_text(),
                       media_model=FakeMedia(refuse_transcribe=True))
    assert job2.status == "failed" and job2.credits_held == 0
    # The input row AND its stored bytes are gone (raw PII).
    assert db_session.execute(
        select(AiInput).where(AiInput.wedding_id == w2.id)
    ).scalars().all() == []
    with pytest.raises(storage.UploadError):
        storage.load_media_bytes(s, url2)


# ---------------------------------------------------------------------------
# Illustration — an explicit stage since 8.5b (app/ai/images.py), never part of
# the run. The staged wizard's own rules (style, edits, credits) live in
# test_ai_staged_story.py; these cover the Gemini/storage/sweep plumbing.
# ---------------------------------------------------------------------------
def _illustrated(db, s, w, media, *, beats=3, targets=None) -> AiJob:
    inp = _add_text_input(db, w)
    job = create_job(db, s, w, kind="story_arc", input_ids=[inp.id])
    job = _run_to_review(db, s, job, _fake_text(beats=beats), media)
    assert job.proposal["beat_images"] == {}  # the run itself renders nothing
    return illustrate(db, s, job, targets=targets, media_model=media)


def test_illustrate_renders_in_batches_ledgers_and_meters(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-img")
    s = _settings()
    media = FakeMedia()
    # 3 beats + the climax panel = 4 targets, IMAGES_PER_CALL at a time.
    job = _illustrated(db_session, s, w, media, beats=3)
    assert set(job.proposal["beat_images"]) == {"0", "1"}
    job = illustrate(db_session, s, job, media_model=media)
    assert set(job.proposal["beat_images"]) == {"0", "1", "2", "climax"}
    assert pending_targets(job) == []

    rows = _ledger(db_session, "image")
    assert len(rows) == 4
    assert all(r.images == 1 and r.model == "gemini-3.1-flash-image" for r in rows)
    assert all(r.cost_usd_micros == 67_000 for r in rows)  # $0.067/image
    assert (w.storage_bytes_used or 0) > 0  # generated art IS metered
    # The text run rode the free-arc allowance (hold 0); the 4 images are
    # 1 credit each, added to the same hold so a cancel refunds them.
    assert job.credits_held == 4


def test_illustrate_refusal_leaves_one_panel_text_only(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-img-refuse")
    s = _settings()
    media = FakeMedia(refuse_image_prompts=("scene 1",))
    job = _illustrated(db_session, s, w, media, beats=2, targets=["0", "1"])
    assert set(job.proposal["beat_images"]) == {"0"}  # beat 1 stays text-only
    assert "1" in job.proposal["images_refused"]
    assert job.credits_held == 1  # the refused panel charged nothing


def test_illustrate_without_images_configured_is_refused_cleanly(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-img-nokey")
    s = _settings(gemini_api_key="")
    inp = _add_text_input(db_session, w)
    job = create_job(db_session, s, w, kind="story_arc", input_ids=[inp.id])
    job = _run_to_review(db_session, s, job, _fake_text(beats=2))
    assert job.status == "awaiting_review"  # the TEXT run is unaffected

    with pytest.raises(HTTPException) as exc:
        illustrate(db_session, s, job, media_model=FakeMedia())
    assert exc.value.status_code == 422
    assert job.proposal["beat_images"] == {}
    assert _ledger(db_session, "image") == []


def test_illustrate_respects_the_per_arc_cap(db_session):
    _enable_ai(db_session, ai_max_images_per_arc=1)
    w = make_wedding(db_session, "wed-img-cap")
    s = _settings()
    media = FakeMedia()
    job = _illustrated(db_session, s, w, media, beats=3)
    assert set(job.proposal["beat_images"]) == {"0"}
    assert len(media.image_calls) == 1
    with pytest.raises(HTTPException) as exc:
        illustrate(db_session, s, job, media_model=media)
    assert exc.value.status_code == 403


def test_cancel_sweeps_generated_images_and_frees_bytes(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-img-cancel")
    s = _settings()
    job = _illustrated(db_session, s, w, FakeMedia(), beats=1)
    urls = list(job.proposal["beat_images"].values())
    assert len(urls) == 2 and (w.storage_bytes_used or 0) > 0  # beat 0 + climax

    cancel_job(db_session, s, job)
    assert (w.storage_bytes_used or 0) == 0
    assert job.credits_held == 0  # the images were refunded with the hold
    for url in urls:
        with pytest.raises(storage.UploadError):
            storage.load_media_bytes(s, url)


def test_apply_writes_beat_and_climax_images_and_sweeps_the_unkept(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-img-apply")
    s = _settings()
    media = FakeMedia()
    job = _illustrated(db_session, s, w, media, beats=1)  # beat 0 + climax
    original_beat0 = job.proposal["beat_images"]["0"]

    # Regenerate beat 0's art and keep the new one.
    variant = regenerate_artifact(
        db_session, s, job, artifact="arc.beat.0", text_model=_fake_text(),
        media_model=media,
    )
    assert variant.image_url and variant.image_url != original_beat0
    # Variant 0 (the original) was seeded so nothing is destroyed.
    seeded = db_session.execute(
        select(AiVariant).where(AiVariant.artifact == "arc.beat.0")
    ).scalars().all()
    assert len(seeded) == 2 and seeded[0].image_url == original_beat0
    select_variant(db_session, job, artifact="arc.beat.0", variant_id=variant.id)
    assert job.proposal["beat_images"]["0"] == variant.image_url

    result = apply_proposal(db_session, s, w, job)
    assert result["applied"] == ["story_arc"]
    arc = w.story_arcs[0].content
    assert arc["beats"][0]["image"] == variant.image_url
    assert arc["climax"]["image"] == job.proposal["beat_images"]["climax"]
    # The unselected original beat-0 image is gone; the kept two remain.
    with pytest.raises(storage.UploadError):
        storage.load_media_bytes(s, original_beat0)
    assert storage.load_media_bytes(s, variant.image_url)


def test_selecting_a_regenerated_arc_text_clears_stale_beat_art(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-img-swap")
    s = _settings()
    fake = _fake_text(beats=2)
    inp = _add_text_input(db_session, w)
    job = create_job(db_session, s, w, kind="story_arc", input_ids=[inp.id])
    job = _run_to_review(db_session, s, job, fake, FakeMedia())
    job = illustrate(db_session, s, job, targets=["0", "1"], media_model=FakeMedia())
    assert len(job.proposal["beat_images"]) == 2

    new_text = regenerate_artifact(
        db_session, s, job, artifact="arc.text", text_model=fake,
    )
    select_variant(db_session, job, artifact="arc.text", variant_id=new_text.id)
    assert job.proposal["beat_images"] == {}  # new scenes have no art yet

    original = db_session.execute(
        select(AiVariant).where(AiVariant.artifact == "arc.text")
    ).scalars().first()
    select_variant(db_session, job, artifact="arc.text", variant_id=original.id)
    assert len(job.proposal["beat_images"]) == 2  # going back restores its art


# ---------------------------------------------------------------------------
# The guests kind — the model returns raw lines; tiers are computed in code.
# ---------------------------------------------------------------------------
def test_guests_run_assigns_tiers_deterministically(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-guests")
    s = _settings()
    inp = _add_text_input(db_session, w, "guest list: Jordan, Riley +1, Casey family")
    job = create_job(db_session, s, w, kind="guests", input_ids=[inp.id])
    job = _run_to_review(db_session, s, job, _fake_text())
    assert job.status == "awaiting_review"
    by_name = {g["name"]: g for g in job.proposal["guests"]}
    assert by_name["Jordan Lee"]["invite_tier"] == "solo"
    assert by_name["Riley Park"]["invite_tier"] == "plus_one"
    assert by_name["Casey Nguyen"]["invite_tier"] == "plus_family"
    assert job.proposal["guests_unresolved"] == ["Sasha Chen +1"]


def test_guests_apply_creates_rows_and_ignores_tampered_tiers(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-guests-apply")
    s = _settings()
    inp = _add_text_input(db_session, w)
    job = create_job(db_session, s, w, kind="guests", input_ids=[inp.id])
    job = _run_to_review(db_session, s, job, _fake_text())

    # Hostile stored proposal: lie about the tier, try to target arcs.
    proposal = dict(job.proposal)
    tampered = [dict(g) for g in proposal["guests"]]
    for g in tampered:
        g["invite_tier"] = "plus_family"
        g["story_arc_ids"] = ["some-arc"]
    proposal["guests"] = tampered
    job.proposal = proposal
    db_session.commit()

    result = apply_proposal(db_session, s, w, job)
    assert result["applied"] == ["guests"]
    guests = db_session.execute(
        select(Guest).where(Guest.wedding_id == w.id)
    ).scalars().all()
    by_name = {g.name: g for g in guests}
    # Tier came from infer_tier over companion counts — the lie was ignored.
    assert by_name["Jordan Lee"].invite_tier.value == "solo"
    assert by_name["Riley Park"].invite_tier.value == "plus_one"
    assert by_name["Casey Nguyen"].invite_tier.value == "plus_family"
    for g in guests:
        assert g.story_arc_ids is None  # AI never targets arcs at guests
        assert g.seed_meta == {"ai_generated": True}
        assert len(g.slug) >= 20  # real credential-grade slugs
        assert g.greeting_name == g.name
    assert by_name["Casey Nguyen"].expected_party_size == 3


def test_guests_apply_rechecks_max_guests_and_kind_isolation(db_session):
    _enable_ai(db_session, max_guests=2)
    w = make_wedding(db_session, "wed-guests-cap")
    s = _settings()
    inp = _add_text_input(db_session, w)
    job = create_job(db_session, s, w, kind="guests", input_ids=[inp.id])
    job = _run_to_review(db_session, s, job, _fake_text())
    with pytest.raises(HTTPException) as exc:  # 4 drafts > 2 allowed
        apply_proposal(db_session, s, w, job)
    assert exc.value.status_code == 403
    assert db_session.execute(select(Guest)).scalars().all() == []


def test_guests_empty_extraction_fails_cleanly(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-guests-empty")
    s = _settings()
    inp = _add_text_input(db_session, w)
    fake = FakeTextModel(responses={"extract_guests.system": {"lines": []}})
    job = create_job(db_session, s, w, kind="guests", input_ids=[inp.id])
    job = _run_to_review(db_session, s, job, fake)
    assert job.status == "failed" and "No guest names" in job.error
    assert job.credits_held == 0  # refunded


# ---------------------------------------------------------------------------
# HTTP seams for the new pieces
# ---------------------------------------------------------------------------
def test_http_guests_run_and_beat_regen(db_session, make_client):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-http")
    make_member(db_session, w, OWNER, "owner")
    client = make_client(ai_text_provider="fake", gemini_api_key="test-gemini-key")
    fake = _fake_text(beats=2)
    media = FakeMedia()
    app.dependency_overrides[get_job_text_model] = lambda: fake
    app.dependency_overrides[get_job_media_model] = lambda: media
    base = f"/api/w/{w.slug}/admin/ai"
    auth = user_auth(OWNER)

    r = client.post(f"{base}/inputs", json={"text": "our guest list"}, headers=auth)
    r = client.post(f"{base}/jobs", json={"kind": "guests", "input_ids": [r.json()["id"]]},
                    headers=auth)
    assert r.status_code == 201, r.text
    job = r.json()
    for _ in range(job["steps_total"] + 2):
        job = client.post(f"{base}/jobs/{job['id']}/advance", headers=auth).json()
        if job["status"] not in ("queued", "running"):
            break
    assert job["status"] == "awaiting_review"
    assert job["proposal"]["guests"][0]["name"] == "Jordan Lee"

    # A guests job has no beat images to regenerate.
    r = client.post(f"{base}/jobs/{job['id']}/regenerate",
                    json={"artifact": "arc.beat.0"}, headers=auth)
    assert r.status_code == 422

    # A story run CAN regenerate a beat image over HTTP.
    r = client.post(f"{base}/inputs", json={"text": "our story"}, headers=auth)
    r = client.post(f"{base}/jobs", json={"kind": "story_arc", "input_ids": [r.json()["id"]]},
                    headers=auth)
    story = r.json()
    for _ in range(story["steps_total"] + 2):
        story = client.post(f"{base}/jobs/{story['id']}/advance", headers=auth).json()
        if story["status"] not in ("queued", "running"):
            break
    assert story["status"] == "awaiting_review"
    r = client.post(f"{base}/jobs/{story['id']}/regenerate",
                    json={"artifact": "arc.beat.1", "steer": "make it snowy"},
                    headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["image_url"]
    assert "make it snowy" in media.image_calls[-1]  # steer rides the scene text
    # Out-of-range beat is refused against the job's real beat count.
    r = client.post(f"{base}/jobs/{story['id']}/regenerate",
                    json={"artifact": "arc.beat.7"}, headers=auth)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Pricing + adapter request shape
# ---------------------------------------------------------------------------
def test_image_pricing_is_flat_per_image_and_unknown_records_zero():
    usage = Usage(provider="google", model="gemini-3.1-flash-image",
                  input_tokens=50, output_tokens=0)
    assert cost_usd_micros(usage, images=2) == 134_000
    unknown = Usage(provider="google", model="brand-new-image-model",
                    input_tokens=50, output_tokens=0)
    assert cost_usd_micros(unknown, images=1) == 0  # auditable zero, never a guess


class _StubGeminiClient:
    """Pin the request shape GeminiMedia sends through google-genai."""

    class _Models:
        def __init__(self, outer):
            self.outer = outer

        def generate_content(self, *, model, contents):
            self.outer.requests.append({"model": model, "contents": contents})
            return self.outer.response

    def __init__(self, response):
        self.requests = []
        self.response = response
        self.models = self._Models(self)


def test_gemini_adapter_transcribe_request_shape_and_refusal():
    gtypes = pytest.importorskip("google.genai.types")

    class Resp:
        text = "  a transcript  "
        prompt_feedback = None
        usage_metadata = type("U", (), {"prompt_token_count": 7, "candidates_token_count": 3})()
        response_id = "resp-1"

    stub = _StubGeminiClient(Resp())
    media = GeminiMedia(_settings(), client=stub)
    text, usage = media.transcribe(b"bytes", "audio/mpeg")
    assert text == "a transcript"
    assert usage.provider == "google" and usage.input_tokens == 7
    req = stub.requests[0]
    assert req["model"] == "gemini-3.5-flash"
    assert isinstance(req["contents"][0], str) and "verbatim" in req["contents"][0]
    assert isinstance(req["contents"][1], gtypes.Part)

    class Blocked:
        text = None
        prompt_feedback = type("F", (), {"block_reason": "SAFETY"})()
        usage_metadata = None

    media_blocked = GeminiMedia(_settings(), client=_StubGeminiClient(Blocked()))
    with pytest.raises(ProviderRefusal):
        media_blocked.transcribe(b"bytes", "audio/mpeg")


def test_media_input_without_stored_file_fails_cleanly(db_session):
    w = make_wedding(db_session, "wed-nofile")
    inp = AiInput(wedding_id=w.id, kind="audio", storage_url=None, mime="audio/mpeg")
    db_session.add(inp)
    db_session.commit()
    from app.ai.types import ProviderError

    with pytest.raises(ProviderError):
        transcribe_input(_settings(), inp, media=FakeMedia())
