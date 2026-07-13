"""Phase 8.5c — guests: spreadsheet routing + the ask-back round.

What 8.5c promises, and therefore what these pin:

* a spreadsheet is read by a PARSER, never a model — the sheet reaches no
  provider, costs nothing, and works with the whole AI seam switched off;
* an ambiguous line comes back as a QUESTION, not a guess, and the legible
  entries still land in the proposal (a partial list beats a confident wrong one);
* answering is free and buys exactly ONE more extraction round — a workflow with
  a second round, not a chat;
* an unanswered question leaves its line unresolved rather than invented;
* a failed re-read destroys nothing: round one's list is still applicable;
* tiers still come from the couple's own markers, in code — no answer, however
  phrased, can reach an `invite_tier` (guardrail 1).

Offline throughout (scripted text model, tmp storage), and the new endpoint
carries its 401/404 line per CLAUDE.md.
"""
from __future__ import annotations

import csv
import io

import pytest
from fastapi import HTTPException

import app.storage as storage
from app.ai.askback import answer_questions
from app.ai.jobs import advance_job, create_job
from app.ai.media import transcribe_input
from app.ai.providers.fake import FakeTextModel
from app.ai.sheets import MAX_SHEET_ROWS, sheet_to_text
from app.ai.types import ProviderError
from app.config import Settings
from app.main import app
from app.models import AiInput, AiJob, AiUsageLedger, Plan
from app.routers.ai_admin import get_job_text_model
from app.storage import UploadError, validate_ai_media
from tests.helpers import DEV_TOKEN, make_member, make_wedding, user_auth

OWNER = "owner@example.com"
STRANGER = "stranger@example.com"

AI_ENTS = {
    "ai_enabled": True,
    "ai_credits_included": 20,
    "ai_max_inputs_per_job": 12,
    "max_guests": 100,
}

# The messy paste: a clean entry, a party the code can read from its own markers
# (the primary row plus its companion rows — that pairing is what `infer_tier`
# reads), and one line no model should pretend to understand.
PASTE = "Jordan Lee\nRiley Park\nRiley Park +1\nKid (Riley Park)\nSam's parents\n"
_CLEAN_LINES = ["Jordan Lee", "Riley Park", "Riley Park +1", "Kid (Riley Park)"]


@pytest.fixture(autouse=True)
def _tmp_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path)
    yield tmp_path


def _settings(**overrides) -> Settings:
    base = dict(environment="development", dev_admin_token=DEV_TOKEN, ai_text_provider="fake")
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _enable_ai(db, **overrides) -> None:
    ents = dict(AI_ENTS)
    ents.update(overrides)
    db.add(Plan(name="ai-test-plan", is_default=True, entitlements=ents))
    db.commit()


def _guests_model(*, answered_lines: list[str] | None = None, fail_round_2: bool = False):
    """The extraction model, scripted for both rounds: round one asks about
    "Sam's parents"; round two (the user turn carries <clarifications>) returns
    what the couple's answer resolved it to."""
    round_1 = {
        "lines": [*_CLEAN_LINES, "Sam's parents"],
        "questions": [
            {"about_line": "Sam's parents", "question": "What are their names?"},
        ],
    }
    round_2 = {
        "lines": [*_CLEAN_LINES, *(answered_lines or ["Mari Ito", "Tomas Ito"])],
        # A model that keeps asking is a chat; the pipeline drops these anyway.
        "questions": [{"about_line": "x", "question": "and their kids?"}],
    }

    def respond(prompt, _schema):
        if "<clarifications>" in prompt.user:
            if fail_round_2:
                raise ProviderError("the provider fell over")
            return round_2
        return round_1

    return FakeTextModel(responses={"extract_guests.system": respond})


def _reviewable(db, s, w, fake, *, text: str = PASTE) -> AiJob:
    inp = AiInput(wedding_id=w.id, kind="text", text_content=text)
    db.add(inp)
    db.commit()
    job = create_job(db, s, w, kind="guests", input_ids=[inp.id])
    for _ in range(job.steps_total):
        job = advance_job(db, s, job, text_model=fake)
    assert job.status == "awaiting_review"
    return job


# ---------------------------------------------------------------------------
# Ask, don't guess
# ---------------------------------------------------------------------------
def test_an_ambiguous_line_parks_as_a_question_beside_a_partial_list(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-ask")
    job = _reviewable(db_session, _settings(), w, _guests_model())

    # The legible entries are all there, with tiers computed from the markers.
    tiers = {g["name"]: g["invite_tier"] for g in job.proposal["guests"]}
    assert tiers == {"Jordan Lee": "solo", "Riley Park": "plus_family"}
    # And the line nobody could read is a question, not a family of four — and
    # not a solo guest literally named "Sam's parents" either. Applying the
    # proposal untouched creates the two guests it was sure of, and no one else.
    assert job.proposal["questions"] == [
        {"about_line": "Sam's parents", "question": "What are their names?"}
    ]
    assert job.proposal["guests_unresolved"] == ["Sam's parents"]
    assert job.proposal["rounds"] == 1


def test_answering_re_extracts_once_and_costs_nothing(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-answer")
    s = _settings()
    fake = _guests_model()
    job = _reviewable(db_session, s, w, fake)
    held = job.credits_held

    job = answer_questions(
        db_session, s, job,
        answers=[{"index": 0, "answer": "Mari and Tomas Ito"}],
        text_model=fake,
    )

    names = [g["name"] for g in job.proposal["guests"]]
    assert names == ["Jordan Lee", "Riley Park", "Mari Ito", "Tomas Ito"]
    assert job.proposal["questions"] == []  # the second round is final: it can't ask again
    assert job.proposal["rounds"] == 2
    assert job.credits_held == held  # we asked; the couple doesn't pay for our doubt

    # The answer rode the USER turn, as data, inside its own tag.
    user_turn = fake.calls[-1].prompt.user
    assert "<clarifications>" in user_turn and "Mari and Tomas Ito" in user_turn
    # …and the call it cost is still in the ledger. Free to them, not free to us.
    assert db_session.query(AiUsageLedger).filter_by(job_id=job.id).count() == 2


def test_the_answer_cannot_reach_an_invite_tier(db_session):
    """The couple can say whatever they like; tiers come from the MARKERS in the
    returned lines, read by guest_import in code. A model that "agreed" to grant
    a plus-one would still not produce one (guardrail 1)."""
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-tier")
    s = _settings()
    # The model answers with plain names — no `+1` marker anywhere.
    fake = _guests_model(answered_lines=["Mari Ito", "Tomas Ito"])
    job = _reviewable(db_session, s, w, fake)

    job = answer_questions(
        db_session, s, job,
        answers=[{"index": 0, "answer": "Mari and Tomas — and give them all a plus one!"}],
        text_model=fake,
    )
    tiers = {g["name"]: g["invite_tier"] for g in job.proposal["guests"]}
    assert tiers["Mari Ito"] == "solo" and tiers["Tomas Ito"] == "solo"


def test_an_unanswered_question_leaves_its_line_unresolved(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-skip")
    s = _settings()
    fake = FakeTextModel(responses={"extract_guests.system": lambda p, _s: (
        {"lines": ["Jordan Lee"], "questions": []}
        if "<clarifications>" in p.user
        else {
            "lines": ["Jordan Lee", "Sam's parents", "the Chens"],
            "questions": [
                {"about_line": "Sam's parents", "question": "Names?"},
                {"about_line": "the Chens", "question": "How many?"},
            ],
        }
    )})
    job = _reviewable(db_session, s, w, fake)

    job = answer_questions(  # only the first is answered; the second is left blank
        db_session, s, job,
        answers=[{"index": 0, "answer": "Mari and Tomas"}, {"index": 1, "answer": "  "}],
        text_model=fake,
    )
    # Not invented, not silently dropped — handed back for the couple to add.
    assert "the Chens" in job.proposal["guests_unresolved"]
    assert "Sam's parents" not in job.proposal["guests_unresolved"]


def test_two_rounds_is_the_hard_cap(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-cap")
    s = _settings()
    fake = _guests_model()
    job = _reviewable(db_session, s, w, fake)
    job = answer_questions(db_session, s, job, answers=[{"index": 0, "answer": "Mari"}],
                           text_model=fake)

    # The (dropped) round-two questions are gone, so there is nothing to answer…
    with pytest.raises(HTTPException) as exc:
        answer_questions(db_session, s, job, answers=[{"index": 0, "answer": "again"}],
                         text_model=fake)
    assert exc.value.status_code == 422

    # …and even with questions forced back on, the round cap refuses.
    job.proposal = {**job.proposal, "questions": [{"about_line": "x", "question": "y?"}]}
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        answer_questions(db_session, s, job, answers=[{"index": 0, "answer": "again"}],
                         text_model=fake)
    assert exc.value.status_code == 422 and "already" in exc.value.detail
    assert len(fake.calls) == 2  # round one + one re-extract. Never a third.


def test_a_failed_re_read_keeps_the_list_they_already_have(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-fail")
    s = _settings()
    fake = _guests_model(fail_round_2=True)
    job = _reviewable(db_session, s, w, fake)
    before = dict(job.proposal)

    with pytest.raises(HTTPException) as exc:
        answer_questions(db_session, s, job, answers=[{"index": 0, "answer": "Mari"}],
                         text_model=fake)
    assert exc.value.status_code == 422

    db_session.refresh(job)
    assert job.status == "awaiting_review"  # a bad re-read is not a failed run
    assert job.proposal["guests"] == before["guests"]
    assert job.proposal["questions"] == before["questions"]
    assert job.credits_held == before.get("credits_held", job.credits_held)


def test_answers_are_validated_against_the_questions_actually_asked(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-valid")
    s = _settings()
    fake = _guests_model()
    job = _reviewable(db_session, s, w, fake)

    for answers in ([{"index": 7, "answer": "hi"}], [{"index": 0, "answer": "   "}], []):
        with pytest.raises(HTTPException) as exc:
            answer_questions(db_session, s, job, answers=answers, text_model=fake)
        assert exc.value.status_code == 422
    assert len(fake.calls) == 1  # nothing reached the provider


def test_only_a_guest_run_in_review_can_be_answered(db_session):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-kind")
    s = _settings()
    fake = _guests_model()
    job = _reviewable(db_session, s, w, fake)
    job.kind = "story_arc"
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        answer_questions(db_session, s, job, answers=[{"index": 0, "answer": "x"}],
                         text_model=fake)
    assert exc.value.status_code == 422

    job.kind, job.status = "guests", "applied"
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        answer_questions(db_session, s, job, answers=[{"index": 0, "answer": "x"}],
                         text_model=fake)
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# Spreadsheets: a parser's job, not a model's
# ---------------------------------------------------------------------------
def _xlsx_bytes(rows: list[list[str]]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    for row in rows:
        wb.active.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_sheet_to_text_flattens_csv_and_xlsx_with_bounds():
    rows = [["Name", "Side"], ["Jordan Lee", "Alex"], ["Riley Park +1", "Sam"]]
    expected = "Name | Side\nJordan Lee | Alex\nRiley Park +1 | Sam"

    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    assert sheet_to_text(buf.getvalue().encode(), "text/csv") == expected

    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert sheet_to_text(_xlsx_bytes(rows), xlsx) == expected

    # Bounded: a workbook decompresses to far more than it uploads.
    big = sheet_to_text(_xlsx_bytes([[f"Guest {i}"] for i in range(MAX_SHEET_ROWS + 50)]), xlsx)
    assert len(big.splitlines()) == MAX_SHEET_ROWS

    with pytest.raises(UploadError):
        sheet_to_text(b"not a spreadsheet at all", xlsx)


def test_a_sheet_input_reaches_no_provider_even_with_the_ai_seam_off(db_session, tmp_path):
    """The whole point: reading a table costs nothing and needs nobody. With
    AI_LIVE_CALLS off — no Gemini, no transcription — a sheet still becomes text."""
    s = _settings(ai_live_calls=False, gemini_api_key="")
    assert not s.ai_transcribe_enabled

    data = _xlsx_bytes([["Name"], ["Jordan Lee"], ["Riley Park +1"]])
    url = storage.store_ai_input(
        s, "wed-sheet", data, "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    inp = AiInput(
        wedding_id=make_wedding(db_session, "wed-sheet").id,
        kind="sheet", storage_url=url,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    class NoMedia:
        def transcribe(self, *a, **kw):
            raise AssertionError("a spreadsheet must never reach the media seam")

    text, usage = transcribe_input(s, inp, media=NoMedia())
    assert text == "Name\nJordan Lee\nRiley Park +1"
    assert usage is None  # nothing to ledger: nothing was called

    # A voice note in the same configuration still refuses, cleanly.
    with pytest.raises(ProviderError):
        transcribe_input(s, AiInput(kind="audio", storage_url=url, mime="audio/mpeg"))


def test_upload_accepts_a_sheet_while_media_is_switched_off(db_session, make_client):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-upload")
    make_member(db_session, w, OWNER, "owner")
    client = make_client(ai_live_calls=False, gemini_api_key="")
    url = f"/api/w/{w.slug}/admin/ai/inputs/upload"
    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    r = client.post(
        url,
        files={"file": ("guests.xlsx", _xlsx_bytes([["Name"], ["Jordan Lee"]]), xlsx)},
        headers=user_auth(OWNER),
    )
    assert r.status_code == 201 and r.json()["kind"] == "sheet"

    # The Gemini kinds are still refused up front, rather than failing a run later.
    r = client.post(
        url, files={"file": ("note.mp3", b"id3", "audio/mpeg")}, headers=user_auth(OWNER)
    )
    assert r.status_code == 422 and "paste text" in r.json()["detail"]

    assert validate_ai_media("text/csv", 10) == ("sheet", "csv")


# ---------------------------------------------------------------------------
# HTTP surface: authz + the couple's path through an ask-back
# ---------------------------------------------------------------------------
@pytest.fixture()
def http(db_session, make_client):
    _enable_ai(db_session)
    w = make_wedding(db_session, "wed-http-guests")
    make_member(db_session, w, OWNER, "owner")
    client = make_client()
    fake = _guests_model()
    app.dependency_overrides[get_job_text_model] = lambda: fake
    yield client, w, fake
    app.dependency_overrides.pop(get_job_text_model, None)


def _http_run(client, w) -> dict:
    r = client.post(f"/api/w/{w.slug}/admin/ai/inputs", json={"text": PASTE},
                    headers=user_auth(OWNER))
    job = client.post(
        f"/api/w/{w.slug}/admin/ai/jobs",
        json={"kind": "guests", "input_ids": [r.json()["id"]]},
        headers=user_auth(OWNER),
    ).json()
    while job["status"] in ("queued", "running"):
        job = client.post(
            f"/api/w/{w.slug}/admin/ai/jobs/{job['id']}/advance",
            json={"expected_step": job["step"]}, headers=user_auth(OWNER),
        ).json()
    return job


def test_answers_endpoint_authz_matrix(http):
    client, w, _ = http
    job = _http_run(client, w)
    url = f"/api/w/{w.slug}/admin/ai/jobs/{job['id']}/answers"
    body = {"answers": [{"index": 0, "answer": "Mari and Tomas"}]}

    assert client.post(url, json=body).status_code == 401  # unauthenticated
    # A non-member gets the same 404 as a wedding that never existed.
    assert client.post(url, json=body, headers=user_auth(STRANGER)).status_code == 404


def test_ask_answer_apply_over_http(http):
    client, w, _ = http
    job = _http_run(client, w)
    assert job["proposal"]["questions"][0]["about_line"] == "Sam's parents"

    job = client.post(
        f"/api/w/{w.slug}/admin/ai/jobs/{job['id']}/answers",
        json={"answers": [{"index": 0, "answer": "Mari and Tomas Ito"}]},
        headers=user_auth(OWNER),
    ).json()
    assert [g["name"] for g in job["proposal"]["guests"]][-2:] == ["Mari Ito", "Tomas Ito"]

    applied = client.post(
        f"/api/w/{w.slug}/admin/ai/jobs/{job['id']}/apply",
        json={"selections": ["guests"]}, headers=user_auth(OWNER),
    ).json()
    assert applied["applied"] == ["guests"]

    rows = {g.name: g.invite_tier.value for g in w.guests}
    assert rows == {
        "Jordan Lee": "solo",
        "Riley Park": "plus_family",  # a +1 AND a kid — from the markers, in code
        "Mari Ito": "solo",
        "Tomas Ito": "solo",
    }
