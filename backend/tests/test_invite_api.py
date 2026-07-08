"""Guest-facing invite + RSVP API, on an in-memory SQLite DB (no Supabase).

Covers the security-critical contract: the tier is never exposed, capabilities
are correct per tier, and the RSVP submit enforces companion caps + question
visibility so a tampered client can't widen its own invite.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import (
    Guest,
    InviteTier,
    Question,
    QuestionApplies,
    QuestionScope,
    QuestionType,
    QuestionVisibility,
    Wedding,
)


def _add_question(db, wedding, **kw):
    """Add a Question with sensible defaults for the new scope/type fields."""
    kw.setdefault("qtype", QuestionType.text)
    kw.setdefault("scope", QuestionScope.invitee)
    kw.setdefault("applies_to", QuestionApplies.everyone)
    q = Question(wedding_id=wedding.id, **kw)
    db.add(q)
    db.commit()
    return q


@pytest.fixture
def db_session():
    # StaticPool + one shared connection so the TestClient's worker thread sees
    # the same in-memory DB the fixture populated.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def wedding(db_session):
    w = Wedding(
        slug="alex-and-sam",
        couple_names="Alex & Sam",
        status="active",
        event_details={"venue": "The Garden Hall", "date_iso": "2027-01-01"},
        content={"cover": {"tagline": "Ever after"}},
        theme_tokens=None,
    )
    db_session.add(w)
    db_session.commit()
    return w


def _add_guest(db, wedding, *, slug, name, tier, invited=True, greeting_name=None,
               party_members=None):
    g = Guest(
        wedding_id=wedding.id,
        slug=slug,
        name=name,
        invite_tier=tier,
        invited=invited,
        # Greeting is mandatory now; default to the first name when a test omits it.
        greeting_name=greeting_name or (name.split(" ")[0] if name else "Guest"),
        party_members=party_members,
    )
    db.add(g)
    db.commit()
    return g


# --- resolution + content --------------------------------------------------
def test_invite_returns_wedding_content_and_greeting(client, db_session, wedding):
    _add_guest(db_session, wedding, slug="solo-x", name="Riley Khan", tier=InviteTier.solo)
    r = client.get("/api/i/solo-x")
    assert r.status_code == 200
    body = r.json()
    assert body["wedding"]["couple_names"] == "Alex & Sam"
    assert body["wedding"]["event_details"]["venue"] == "The Garden Hall"
    assert body["guest"] == {
        "name": "Riley Khan",
        "first_name": "Riley",
        "greeting_name": "Riley",  # defaulted to the first name when not set
        "email": None,
        "phone": None,
        "party_members": [],
    }
    assert body["rsvp"] is None


def test_invite_greeting_name_override_is_returned(client, db_session, wedding):
    # An invitee-level greeting override (e.g. a couple) is surfaced verbatim so the
    # cover can render "Dear John & Jane,"; first_name still reflects the full name.
    _add_guest(
        db_session,
        wedding,
        slug="couple-x",
        name="John Smith",
        tier=InviteTier.plus_one,
        greeting_name="John & Jane",
    )
    body = client.get("/api/i/couple-x").json()
    assert body["guest"]["greeting_name"] == "John & Jane"
    assert body["guest"]["first_name"] == "John"
    assert body["guest"]["name"] == "John Smith"


def test_party_members_returned_and_clamped_to_tier(client, db_session, wedding):
    # A plus_one guest gets its (capped) prefill party; a solo guest gets [] even if
    # the stored party has stray members (anti-tamper — never leaks/grants a companion).
    _add_guest(
        db_session, wedding, slug="p1-prefill", name="Lead", tier=InviteTier.plus_one,
        party_members=[{"kind": "adult", "name": "Alex"}, {"kind": "child", "name": "Nope"}],
    )
    body = client.get("/api/i/p1-prefill").json()
    assert body["guest"]["party_members"] == [{"kind": "adult", "name": "Alex"}]  # child dropped

    _add_guest(
        db_session, wedding, slug="solo-prefill", name="Only", tier=InviteTier.solo,
        party_members=[{"kind": "adult", "name": "Ghost"}],
    )
    solo = client.get("/api/i/solo-prefill").json()
    assert solo["guest"]["party_members"] == []


def test_rsvp_writes_back_primary_name(client, db_session, wedding):
    g = _add_guest(db_session, wedding, slug="wb", name="Old Name", tier=InviteTier.solo)
    r = client.post("/api/i/wb/rsvp", json={"attending": True, "name": "New Name"})
    assert r.status_code == 200
    db_session.refresh(g)
    assert g.name == "New Name"
    # A blank/omitted name never wipes the stored one.
    client.post("/api/i/wb/rsvp", json={"attending": True, "name": "   "})
    db_session.refresh(g)
    assert g.name == "New Name"


def test_unknown_slug_is_404(client, wedding):
    assert client.get("/api/i/does-not-exist").status_code == 404


def test_uninvited_guest_is_404(client, db_session, wedding):
    _add_guest(db_session, wedding, slug="u", name="Nope", tier=InviteTier.solo, invited=False)
    assert client.get("/api/i/u").status_code == 404


def test_inactive_wedding_is_404(client, db_session, wedding):
    wedding.status = "draft"
    db_session.commit()
    _add_guest(db_session, wedding, slug="g", name="Someone", tier=InviteTier.solo)
    assert client.get("/api/i/g").status_code == 404


# --- the tier must never leak ---------------------------------------------
def test_tier_string_is_never_in_the_payload(client, db_session, wedding):
    _add_guest(db_session, wedding, slug="fam", name="Jordan", tier=InviteTier.plus_family)
    raw = client.get("/api/i/fam").text
    assert "plus_family" not in raw
    assert "invite_tier" not in raw
    assert "tier" not in raw  # not even the word


def test_capabilities_per_tier(client, db_session, wedding):
    _add_guest(db_session, wedding, slug="s", name="Solo", tier=InviteTier.solo)
    _add_guest(db_session, wedding, slug="p1", name="Plus One", tier=InviteTier.plus_one)
    _add_guest(db_session, wedding, slug="pf", name="Family", tier=InviteTier.plus_family)

    solo = client.get("/api/i/s").json()["capabilities"]
    assert solo == {
        "allow_plus_one": False,
        "allow_kids": False,
        "max_adult_companions": 0,
        "max_child_companions": 0,
        "adults_multi": False,
    }
    p1 = client.get("/api/i/p1").json()["capabilities"]
    assert p1["allow_plus_one"] and not p1["allow_kids"] and p1["max_adult_companions"] == 1
    # plus_one keeps the single +1 toggle — NOT the add/remove adults list.
    assert p1["adults_multi"] is False
    pf = client.get("/api/i/pf").json()["capabilities"]
    assert pf["allow_plus_one"] and pf["allow_kids"] and pf["max_child_companions"] >= 1
    # plus_family renders the multi-adult add/remove list; default caps are 4/4.
    assert pf["adults_multi"] is True
    assert pf["max_adult_companions"] == 4 and pf["max_child_companions"] == 4


# --- question visibility ---------------------------------------------------
def test_question_visibility_filters_by_tier(client, db_session, wedding):
    db_session.add_all(
        [
            Question(
                wedding_id=wedding.id, prompt="Song?", qtype=QuestionType.text,
                visibility=QuestionVisibility.all, sort_order=1,
            ),
            Question(
                wedding_id=wedding.id, prompt="Highchair needed?", qtype=QuestionType.yesno,
                visibility=QuestionVisibility.tier, visibility_ref=["plus_family"], sort_order=2,
            ),
        ]
    )
    db_session.commit()
    _add_guest(db_session, wedding, slug="s", name="Solo", tier=InviteTier.solo)
    _add_guest(db_session, wedding, slug="pf", name="Family", tier=InviteTier.plus_family)

    solo_qs = client.get("/api/i/s").json()["questions"]
    assert [q["prompt"] for q in solo_qs] == ["Song?"]
    fam_qs = client.get("/api/i/pf").json()["questions"]
    assert {q["prompt"] for q in fam_qs} == {"Song?", "Highchair needed?"}


# --- RSVP submit + tier enforcement ---------------------------------------
def test_solo_can_rsvp_without_companions(client, db_session, wedding):
    _add_guest(db_session, wedding, slug="s", name="Solo", tier=InviteTier.solo)
    r = client.post("/api/i/s/rsvp", json={"attending": True})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "attending": True, "companion_count": 0}
    # Round-trips on re-fetch.
    again = client.get("/api/i/s").json()
    assert again["rsvp"]["attending"] is True


def test_solo_cannot_smuggle_a_companion(client, db_session, wedding):
    _add_guest(db_session, wedding, slug="s", name="Solo", tier=InviteTier.solo)
    r = client.post(
        "/api/i/s/rsvp",
        json={"attending": True, "companions": [{"kind": "adult", "name": "Gatecrash"}]},
    )
    assert r.status_code == 422


def test_plus_one_allows_one_adult_not_two(client, db_session, wedding):
    _add_guest(db_session, wedding, slug="p1", name="Plus One", tier=InviteTier.plus_one)
    ok = client.post(
        "/api/i/p1/rsvp",
        json={"attending": True, "companions": [{"kind": "adult", "name": "Partner"}]},
    )
    assert ok.status_code == 200 and ok.json()["companion_count"] == 1
    too_many = client.post(
        "/api/i/p1/rsvp",
        json={
            "attending": True,
            "companions": [{"kind": "adult", "name": "A"}, {"kind": "adult", "name": "B"}],
        },
    )
    assert too_many.status_code == 422


def test_plus_one_cannot_bring_a_child(client, db_session, wedding):
    _add_guest(db_session, wedding, slug="p1", name="Plus One", tier=InviteTier.plus_one)
    r = client.post(
        "/api/i/p1/rsvp",
        json={"attending": True, "companions": [{"kind": "child", "name": "Kid"}]},
    )
    assert r.status_code == 422


def test_family_can_bring_partner_and_kids(client, db_session, wedding):
    _add_guest(db_session, wedding, slug="pf", name="Family", tier=InviteTier.plus_family)
    r = client.post(
        "/api/i/pf/rsvp",
        json={
            "attending": True,
            "companions": [
                {"kind": "adult", "name": "Spouse"},
                {"kind": "child", "name": "Kid 1"},
                {"kind": "child", "name": "Kid 2"},
            ],
        },
    )
    assert r.status_code == 200 and r.json()["companion_count"] == 3


def _set_party_caps(db, wedding, **party):
    """Merge a content.rsvp.party config onto the wedding (per-wedding companion caps)."""
    content = dict(wedding.content or {})
    rsvp = dict(content.get("rsvp") or {})
    rsvp["party"] = party
    content["rsvp"] = rsvp
    wedding.content = content
    db.commit()


def test_family_can_bring_multiple_adults_up_to_configured_cap(client, db_session, wedding):
    """plus_family supports several additional adults (not just one +1), capped by the
    wedding's content.rsvp.party.max_adults."""
    _set_party_caps(db_session, wedding, adults_enabled=True, max_adults=3, kids_enabled=True, max_kids=4)
    _add_guest(db_session, wedding, slug="pf", name="Family", tier=InviteTier.plus_family)
    caps = client.get("/api/i/pf").json()["capabilities"]
    assert caps["max_adult_companions"] == 3 and caps["adults_multi"] is True
    # 3 adults → OK.
    ok = client.post(
        "/api/i/pf/rsvp",
        json={"attending": True, "companions": [
            {"kind": "adult", "name": "Mum"},
            {"kind": "adult", "name": "Wife"},
            {"kind": "adult", "name": "Brother"},
        ]},
    )
    assert ok.status_code == 200 and ok.json()["companion_count"] == 3
    # 4 adults → over the configured cap → 422 (generic, no tier leak).
    over = client.post(
        "/api/i/pf/rsvp",
        json={"attending": True, "companions": [
            {"kind": "adult", "name": f"A{i}"} for i in range(4)
        ]},
    )
    assert over.status_code == 422
    assert "plus_family" not in over.text and "tier" not in over.json()


def test_family_kids_section_can_be_switched_off(client, db_session, wedding):
    """Turning the kids group off zeroes the child cap so a plus_family invite reads as
    a generic adults-only companion list."""
    _set_party_caps(db_session, wedding, adults_enabled=True, max_adults=5, kids_enabled=False, max_kids=4)
    _add_guest(db_session, wedding, slug="pf", name="Family", tier=InviteTier.plus_family)
    caps = client.get("/api/i/pf").json()["capabilities"]
    assert caps["allow_kids"] is False and caps["max_child_companions"] == 0
    assert caps["max_adult_companions"] == 5
    # A child companion is now rejected (kids off).
    r = client.post(
        "/api/i/pf/rsvp",
        json={"attending": True, "companions": [{"kind": "child", "name": "Kid"}]},
    )
    assert r.status_code == 422


# --- per-person questions: scope, applies_to, kid-age-as-question (Phase 1) --
def test_required_child_question_enforced_per_kid(client, db_session, wedding):
    """An 'Age' number question (person scope, children only, required) must be
    answered for each child — this is how kid-age is now made mandatory."""
    age_q = _add_question(
        db_session, wedding, prompt="Age", qtype=QuestionType.number,
        required=True, scope=QuestionScope.person, applies_to=QuestionApplies.children,
    )
    _add_guest(db_session, wedding, slug="pf", name="Family", tier=InviteTier.plus_family)
    # Child with no age answer → 422.
    missing = client.post(
        "/api/i/pf/rsvp",
        json={"attending": True, "companions": [{"kind": "child", "name": "Kid"}]},
    )
    assert missing.status_code == 422
    # Child WITH the age answer → 200.
    ok = client.post(
        "/api/i/pf/rsvp",
        json={
            "attending": True,
            "companions": [
                {"kind": "child", "name": "Kid", "answers": [
                    {"question_id": str(age_q.id), "value": {"number": 6}},
                ]},
            ],
        },
    )
    assert ok.status_code == 200


def test_per_person_answers_round_trip(client, db_session, wedding):
    diet_q = _add_question(
        db_session, wedding, prompt="Any dietary needs?", qtype=QuestionType.multi_choice,
        options=["Halal", "Vegetarian", "No beef"], scope=QuestionScope.person,
        applies_to=QuestionApplies.everyone,
    )
    _add_guest(db_session, wedding, slug="pf", name="Family", tier=InviteTier.plus_family)
    r = client.post(
        "/api/i/pf/rsvp",
        json={
            "attending": True,
            # The primary's own dietary is a party answer (companion_id NULL).
            "answers": [{"question_id": str(diet_q.id), "value": {"choices": ["Vegetarian"]}}],
            "companions": [
                {"kind": "adult", "name": "Partner", "answers": [
                    {"question_id": str(diet_q.id), "value": {"choices": ["No beef"]}},
                ]},
                {"kind": "child", "name": "Kid", "answers": [
                    {"question_id": str(diet_q.id), "value": {"choices": ["Halal"]}},
                ]},
            ],
        },
    )
    assert r.status_code == 200
    body = client.get("/api/i/pf").json()["rsvp"]
    assert body["answers"][0]["value"] == {"choices": ["Vegetarian"]}
    comps = body["companions"]
    adult = next(c for c in comps if c["kind"] == "adult")
    child = next(c for c in comps if c["kind"] == "child")
    assert adult["answers"][0]["value"] == {"choices": ["No beef"]}
    assert child["answers"][0]["value"] == {"choices": ["Halal"]}


def test_answer_for_inapplicable_person_rejected(client, db_session, wedding):
    """A children-only question answered for an adult companion → 422."""
    kid_q = _add_question(
        db_session, wedding, prompt="Age", qtype=QuestionType.number,
        scope=QuestionScope.person, applies_to=QuestionApplies.children,
    )
    _add_guest(db_session, wedding, slug="pf", name="Family", tier=InviteTier.plus_family)
    r = client.post(
        "/api/i/pf/rsvp",
        json={
            "attending": True,
            "companions": [
                {"kind": "adult", "name": "Partner", "answers": [
                    {"question_id": str(kid_q.id), "value": {"number": 30}},
                ]},
            ],
        },
    )
    assert r.status_code == 422


# --- invitee contacts (Phase 1) --------------------------------------------
def test_contacts_validated_and_normalized(client, db_session, wedding):
    _add_guest(db_session, wedding, slug="s", name="Solo", tier=InviteTier.solo)
    # Bad email → 422
    assert (
        client.post(
            "/api/i/s/rsvp", json={"attending": True, "email": "not-an-email"}
        ).status_code
        == 422
    )
    # Bad phone → 422
    assert (
        client.post(
            "/api/i/s/rsvp", json={"attending": True, "phone": "123"}
        ).status_code
        == 422
    )
    # Valid: national SG number normalizes to E.164, returned for prefill.
    r = client.post(
        "/api/i/s/rsvp",
        json={"attending": True, "email": "Guest@Example.com", "phone": "91234567"},
    )
    assert r.status_code == 200
    guest = client.get("/api/i/s").json()["guest"]
    # Contacts come back MASKED (links get forwarded; the holder of a link must
    # not learn a saved contact). The mask still proves save + normalization:
    # email-validator lowercased the domain, the phone became E.164.
    assert guest["email"] == "G•••@example.com"
    assert guest["phone"] == "+65 •••• 4567"


def test_blank_contact_does_not_wipe_saved_value(client, db_session, wedding):
    _add_guest(db_session, wedding, slug="s", name="Solo", tier=InviteTier.solo)
    client.post("/api/i/s/rsvp", json={"attending": True, "phone": "91234567"})
    # A later submit with no phone leaves the saved one intact.
    client.post("/api/i/s/rsvp", json={"attending": True})
    masked = client.get("/api/i/s").json()["guest"]["phone"]
    assert masked == "+65 •••• 4567"
    # Re-submitting the masked prefill verbatim also means "unchanged" — it is
    # neither validated as a phone number nor stored.
    client.post("/api/i/s/rsvp", json={"attending": True, "phone": masked})
    assert client.get("/api/i/s").json()["guest"]["phone"] == masked


def test_rsvp_is_upserted_not_duplicated(client, db_session, wedding):
    from app.models import Rsvp

    _add_guest(db_session, wedding, slug="s", name="Solo", tier=InviteTier.solo)
    client.post("/api/i/s/rsvp", json={"attending": True})
    client.post("/api/i/s/rsvp", json={"attending": False, "notes": "changed my mind"})
    assert db_session.query(Rsvp).count() == 1
    body = client.get("/api/i/s").json()
    assert body["rsvp"]["attending"] is False
    assert body["rsvp"]["notes"] == "changed my mind"


def test_rejects_answer_to_hidden_question(client, db_session, wedding):
    hidden = Question(
        wedding_id=wedding.id, prompt="VIP only", qtype=QuestionType.text,
        visibility=QuestionVisibility.tier, visibility_ref=["plus_family"], sort_order=1,
    )
    db_session.add(hidden)
    db_session.commit()
    _add_guest(db_session, wedding, slug="s", name="Solo", tier=InviteTier.solo)
    r = client.post(
        "/api/i/s/rsvp",
        json={"attending": True, "answers": [{"question_id": str(hidden.id), "value": {"text": "hi"}}]},
    )
    assert r.status_code == 422


def test_required_question_must_be_answered_when_attending(client, db_session, wedding):
    q = Question(
        wedding_id=wedding.id, prompt="Meal choice", qtype=QuestionType.choice,
        options=["Fish", "Veg"], required=True, visibility=QuestionVisibility.all, sort_order=1,
    )
    db_session.add(q)
    db_session.commit()
    _add_guest(db_session, wedding, slug="s", name="Solo", tier=InviteTier.solo)
    missing = client.post("/api/i/s/rsvp", json={"attending": True})
    assert missing.status_code == 422
    ok = client.post(
        "/api/i/s/rsvp",
        json={"attending": True, "answers": [{"question_id": str(q.id), "value": {"choice": "Veg"}}]},
    )
    assert ok.status_code == 200
    # Not attending → required question is not enforced.
    decline = client.post("/api/i/s/rsvp", json={"attending": False})
    assert decline.status_code == 200
