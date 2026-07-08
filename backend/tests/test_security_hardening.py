"""Phase-0 security hardening (SAAS_PLAN 0.3) regression tests.

Covers the fork-specific protections:
  • dev-token bypass is refused whenever the VERCEL env var is present,
    regardless of ENVIRONMENT (belt-and-braces against a prod misconfig);
  • guests receive an ALLOWLISTED wedding payload (owner-only keys like
    `event_details.capacity` never cross the wire);
  • RSVP answer values are bounded to the known shapes.
Contact masking is covered in test_invite_api.py.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_owner
from app.config import Settings
from app.db import Base, get_db
from app.main import app
from app.models import Guest, InviteTier, Wedding

DEV_TOKEN = "dev-secret-token"


def _settings(**overrides) -> Settings:
    base = dict(
        environment="development",
        dev_admin_token=DEV_TOKEN,
        supabase_url="",
        supabase_publishable_key="",
        admin_emails="owner@example.com",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


# --- P1-1: dev token refused on Vercel --------------------------------------
def test_dev_token_refused_when_vercel_env_present(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        get_current_owner(authorization=f"Bearer {DEV_TOKEN}", settings=_settings())
    assert exc.value.status_code == 401


def test_dev_token_accepted_locally(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    owner = get_current_owner(authorization=f"Bearer {DEV_TOKEN}", settings=_settings())
    assert owner.via == "dev"


# --- Fixtures for the endpoint-level checks ---------------------------------
@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def guest_slug(db_session):
    wedding = Wedding(
        slug="w",
        couple_names="Alex & Sam",
        status="active", published=True,
        owner_id=None,
        event_details={
            "venue": "The Garden Hall",
            # Owner-only planning data that must never reach a guest:
            "capacity": {"total": 120, "by_side": {"Alex": 60, "Sam": 60}},
        },
        content={"rsvp": {}, "internal_notes": "owner eyes only"},
    )
    db_session.add(wedding)
    db_session.flush()
    guest = Guest(
        wedding_id=wedding.id,
        slug="g",
        name="Guest",
        greeting_name="Guest",
        invite_tier=InviteTier.solo,
    )
    db_session.add(guest)
    db_session.commit()
    return "g"


# --- P1-3: allowlisted guest payload ----------------------------------------
def test_invite_payload_omits_owner_only_keys(client, guest_slug):
    body = client.get(f"/api/i/{guest_slug}").json()
    assert body["wedding"]["event_details"]["venue"] == "The Garden Hall"
    assert "capacity" not in body["wedding"]["event_details"]
    assert "internal_notes" not in body["wedding"]["content"]


# --- P1-4: bounded answer payloads ------------------------------------------
def _rsvp(client, slug, answers):
    return client.post(f"/api/i/{slug}/rsvp", json={"attending": True, "answers": answers})


def test_answer_value_unknown_shape_rejected(client, guest_slug):
    r = _rsvp(client, guest_slug, [{"question_id": str(uuid4()), "value": {"evil": "x"}}])
    assert r.status_code == 422


def test_answer_value_two_keys_rejected(client, guest_slug):
    r = _rsvp(
        client, guest_slug, [{"question_id": str(uuid4()), "value": {"text": "a", "yesno": True}}]
    )
    assert r.status_code == 422


def test_answer_text_over_cap_rejected(client, guest_slug):
    r = _rsvp(client, guest_slug, [{"question_id": str(uuid4()), "value": {"text": "x" * 2001}}])
    assert r.status_code == 422


def test_duplicate_question_ids_rejected(client, guest_slug):
    qid = str(uuid4())
    r = _rsvp(
        client,
        guest_slug,
        [
            {"question_id": qid, "value": {"text": "a"}},
            {"question_id": qid, "value": {"text": "b"}},
        ],
    )
    assert r.status_code == 422
