"""Guestbook / wishes — public submit + wall, and owner moderation.

In-memory SQLite, no Supabase. Covers the public contract (a wish is tied to the
resolving guest, the wall only shows approved messages, the slug gates access and
scopes to the tenant) and the owner side (sees hidden messages, can hide/restore
and delete, behind auth and scoped to their wedding).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.db import Base, get_db
from app.main import app
from app.models import Guest, InviteTier, Wedding, Wish

DEV_TOKEN = "dev-secret-token"
ADMIN_EMAIL = "owner@example.com"


def _settings(**overrides) -> Settings:
    base = dict(
        environment="development",
        dev_admin_token=DEV_TOKEN,
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="sb_publishable_test",
        admin_emails=ADMIN_EMAIL,
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture
def db_session():
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
    app.dependency_overrides[get_settings] = lambda: _settings()
    yield TestClient(app)
    app.dependency_overrides.clear()


def dev_auth() -> dict:
    return {"Authorization": f"Bearer {DEV_TOKEN}"}


@pytest.fixture
def wedding(db_session):
    w = Wedding(
        slug="alex-and-sam",
        couple_names="Alex & Sam",
        status="active",
        event_details={"venue": "The Garden Hall"},
        content={},
        theme_tokens=None,
    )
    db_session.add(w)
    db_session.commit()
    return w


def _add_guest(db, wedding, *, slug, name, tier=InviteTier.solo, invited=True):
    g = Guest(
        wedding_id=wedding.id, slug=slug, name=name, invite_tier=tier, invited=invited,
        greeting_name=name.split(" ")[0] if name else "Guest",
    )
    db.add(g)
    db.commit()
    return g


# --- Guest side: submit + wall ---------------------------------------------
def test_submit_wish_is_pending_approval(client, db_session, wedding):
    _add_guest(db_session, wedding, slug="g1", name="Riley Khan")
    r = client.post("/api/i/g1/wishes", json={"name": "Riley", "message": "So happy for you both!"})
    assert r.status_code == 201
    # Held for the couple to approve — not auto-published.
    assert r.json() == {"ok": True, "approved": False}
    # ...so it does NOT show on the public wall yet.
    assert client.get("/api/i/g1/wishes").json() == []


def test_wall_shows_approved_messages_newest_first(client, db_session, wedding):
    g = _add_guest(db_session, wedding, slug="g1", name="Riley Khan")
    # Explicit timestamps — two API submits can land in the same second on SQLite,
    # which would make created_at-desc ordering ambiguous in the test.
    from datetime import datetime, timedelta, timezone

    base = datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)
    db_session.add_all(
        [
            Wish(wedding_id=wedding.id, guest_id=g.id, name="Riley", message="first", created_at=base),
            Wish(
                wedding_id=wedding.id,
                guest_id=g.id,
                name="Riley",
                message="second",
                created_at=base + timedelta(minutes=1),
            ),
        ]
    )
    db_session.commit()
    r = client.get("/api/i/g1/wishes")
    assert r.status_code == 200
    msgs = [w["message"] for w in r.json()]
    assert msgs == ["second", "first"]
    # Public shape never leaks moderation state or the guest id.
    assert set(r.json()[0].keys()) == {"name", "message", "created_at"}


def test_wall_hides_unapproved_messages(client, db_session, wedding):
    g = _add_guest(db_session, wedding, slug="g1", name="Riley Khan")
    db_session.add_all(
        [
            Wish(wedding_id=wedding.id, guest_id=g.id, name="Spam", message="hidden", approved=False),
            Wish(wedding_id=wedding.id, guest_id=g.id, name="Riley", message="shown", approved=True),
        ]
    )
    db_session.commit()
    r = client.get("/api/i/g1/wishes")
    assert [w["message"] for w in r.json()] == ["shown"]


def test_wishes_scoped_to_tenant(client, db_session, wedding):
    """A wish on another wedding never appears on this wedding's wall."""
    other = Wedding(slug="other", couple_names="A & B", status="active", event_details={}, content={})
    db_session.add(other)
    db_session.commit()
    og = _add_guest(db_session, other, slug="other-g", name="Outsider")
    db_session.add(Wish(wedding_id=other.id, guest_id=og.id, name="Outsider", message="elsewhere"))
    g = _add_guest(db_session, wedding, slug="g1", name="Riley Khan")
    db_session.add(Wish(wedding_id=wedding.id, guest_id=g.id, name="Riley", message="ours", approved=True))
    db_session.commit()
    r = client.get("/api/i/g1/wishes")
    assert [w["message"] for w in r.json()] == ["ours"]


def test_wish_endpoints_404_on_bad_slug(client, wedding):
    assert client.get("/api/i/nope/wishes").status_code == 404
    assert client.post("/api/i/nope/wishes", json={"name": "x", "message": "y"}).status_code == 404


def test_wish_rejects_empty_and_overlong(client, db_session, wedding):
    _add_guest(db_session, wedding, slug="g1", name="Riley Khan")
    assert client.post("/api/i/g1/wishes", json={"name": "A", "message": ""}).status_code == 422
    long = "x" * 1001
    assert client.post("/api/i/g1/wishes", json={"name": "A", "message": long}).status_code == 422


# --- Owner side: moderation -------------------------------------------------
def test_admin_wishes_requires_auth(client, wedding):
    assert client.get("/api/admin/wishes").status_code == 401


def test_admin_sees_hidden_and_records_guest(client, db_session, wedding):
    _add_guest(db_session, wedding, slug="g1", name="Riley Khan")
    client.post("/api/i/g1/wishes", json={"name": "Riley", "message": "hi"})
    r = client.get("/api/admin/wishes", headers=dev_auth())
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    # Arrives unapproved — the owner sees it (pending) and decides.
    assert rows[0]["approved"] is False
    assert rows[0]["guest_name"] == "Riley Khan"


def test_admin_can_approve_then_hide_and_restore(client, db_session, wedding):
    _add_guest(db_session, wedding, slug="g1", name="Riley Khan")
    client.post("/api/i/g1/wishes", json={"name": "Riley", "message": "hi"})
    wid = client.get("/api/admin/wishes", headers=dev_auth()).json()[0]["id"]
    # Pending on arrival — not on the wall until the owner approves.
    assert client.get("/api/i/g1/wishes").json() == []

    approve = client.patch(f"/api/admin/wishes/{wid}", json={"approved": True}, headers=dev_auth())
    assert approve.status_code == 200 and approve.json()["approved"] is True
    assert len(client.get("/api/i/g1/wishes").json()) == 1

    # Hidden again removes it from the public wall without deleting...
    client.patch(f"/api/admin/wishes/{wid}", json={"approved": False}, headers=dev_auth())
    assert client.get("/api/i/g1/wishes").json() == []
    # ...and it's restorable.
    client.patch(f"/api/admin/wishes/{wid}", json={"approved": True}, headers=dev_auth())
    assert len(client.get("/api/i/g1/wishes").json()) == 1


def test_admin_can_delete_wish(client, db_session, wedding):
    _add_guest(db_session, wedding, slug="g1", name="Riley Khan")
    client.post("/api/i/g1/wishes", json={"name": "Riley", "message": "hi"})
    wid = client.get("/api/admin/wishes", headers=dev_auth()).json()[0]["id"]
    assert client.delete(f"/api/admin/wishes/{wid}", headers=dev_auth()).status_code == 204
    assert client.get("/api/admin/wishes", headers=dev_auth()).json() == []


def test_admin_moderate_unknown_wish_is_404(client, wedding):
    import uuid

    assert (
        client.patch(
            f"/api/admin/wishes/{uuid.uuid4()}", json={"approved": False}, headers=dev_auth()
        ).status_code
        == 404
    )
