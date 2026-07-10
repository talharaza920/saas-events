"""Per-invitee story-arc targeting (Phase 3) + per-guest story hiding.

Verifies `tenancy.visible_arcs` + the admin guest override (tri-state):
  - no override (NULL) → the guest sees every *visible* arc (ordered);
  - an override → exactly the assigned arcs (even ones otherwise hidden);
  - [] → the story is hidden for this guest (`show_story: false` on the invite);
  - a cross-tenant / unknown arc id is rejected and never resolves;
  - the tier is never the selector and never crosses the wire.

In-memory SQLite, dev-token auth — same harness as test_story_arcs_api.py.
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
from app.models import Guest, InviteTier, StoryArc, Wedding
from app.tenancy import visible_arcs

DEV_TOKEN = "dev-secret-token"


def _settings(**overrides) -> Settings:
    base = dict(environment="development", dev_admin_token=DEV_TOKEN)
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


def auth() -> dict:
    return {"Authorization": f"Bearer {DEV_TOKEN}"}


@pytest.fixture
def wedding(db_session):
    w = Wedding(
        slug="alex-and-sam",
        couple_names="Alex & Sam",
        status="active", published=True,
        owner_id="dev",
        event_details={},
        content={},
    )
    db_session.add(w)
    db_session.commit()
    return w


def _arc(db, wedding, *, title, visible=True, sort_order=0):
    a = StoryArc(
        wedding_id=wedding.id,
        title=title,
        visible=visible,
        sort_order=sort_order,
        content={"heading": title, "beats": []},
    )
    db.add(a)
    db.commit()
    return a


def _guest(db, wedding, *, slug, story_arc_ids=None, tier=InviteTier.solo):
    g = Guest(
        wedding_id=wedding.id,
        slug=slug,
        name="Guest " + slug,
        greeting_name="Guest",
        invite_tier=tier,
        invited=True,
        story_arc_ids=story_arc_ids,
    )
    db.add(g)
    db.commit()
    return g


# --- visible_arcs core ------------------------------------------------------
def test_default_sees_all_visible_ordered(db_session, wedding):
    a2 = _arc(db_session, wedding, title="Second", sort_order=1)
    a1 = _arc(db_session, wedding, title="First", sort_order=0)
    _arc(db_session, wedding, title="Hidden", visible=False, sort_order=2)
    g = _guest(db_session, wedding, slug="default-g")

    arcs = visible_arcs(db_session, wedding, g)
    assert [a.id for a in arcs] == [a1.id, a2.id]  # hidden absent, ordered


def test_override_sees_only_assigned_even_if_hidden(db_session, wedding):
    shown = _arc(db_session, wedding, title="Shown", sort_order=0)
    hidden = _arc(db_session, wedding, title="Hidden", visible=False, sort_order=1)
    # Override points at the hidden arc only — a deliberate per-invitee pick.
    g = _guest(db_session, wedding, slug="override-g", story_arc_ids=[str(hidden.id)])

    arcs = visible_arcs(db_session, wedding, g)
    assert [a.id for a in arcs] == [hidden.id]
    assert shown.id not in {a.id for a in arcs}


def test_cross_tenant_arc_never_resolves(db_session, wedding):
    other = Wedding(slug="other", couple_names="O", status="active", published=True, owner_id="x",
                    event_details={}, content={})
    db_session.add(other)
    db_session.commit()
    foreign = _arc(db_session, other, title="Foreign")
    mine = _arc(db_session, wedding, title="Mine")
    # Even if a stale/foreign id ends up on the guest, it filters out by wedding.
    g = _guest(db_session, wedding, slug="x-g", story_arc_ids=[str(foreign.id), str(mine.id)])

    arcs = visible_arcs(db_session, wedding, g)
    assert [a.id for a in arcs] == [mine.id]


# --- admin override endpoint + invite payload -------------------------------
def test_admin_override_round_trip_and_no_tier_leak(client, db_session, wedding):
    a1 = _arc(db_session, wedding, title="Arc one", sort_order=0)
    _arc(db_session, wedding, title="Arc two", sort_order=1)
    g = _guest(db_session, wedding, slug="solo-x", tier=InviteTier.plus_family)

    # Assign only arc one via the admin API.
    r = client.patch(
        f"/api/w/alex-and-sam/admin/guests/{g.id}", headers=auth(),
        json={"story_arc_ids": [str(a1.id)]},
    )
    assert r.status_code == 200
    assert r.json()["story_arc_ids"] == [str(a1.id)]

    # The invite now surfaces only that arc — and never the tier.
    inv = client.get("/api/i/solo-x")
    assert inv.status_code == 200
    body = inv.json()
    assert [a["content"]["heading"] for a in body["story_arcs"]] == ["Arc one"]
    assert body["show_story"] is True
    assert "tier" not in inv.text
    assert "story_arc_ids" not in inv.text  # the override itself never leaks either

    # Clearing it (explicit null) restores the default (both arcs).
    r = client.patch(
        f"/api/w/alex-and-sam/admin/guests/{g.id}", headers=auth(), json={"story_arc_ids": None}
    )
    assert r.json()["story_arc_ids"] is None
    inv = client.get("/api/i/solo-x").json()
    assert len(inv["story_arcs"]) == 2 and inv["show_story"] is True


def test_empty_override_hides_story_entirely(client, db_session, wedding):
    _arc(db_session, wedding, title="Arc one")
    g = _guest(db_session, wedding, slug="hide-g")

    # [] = "no story for this guest" (distinct from null = default).
    r = client.patch(
        f"/api/w/alex-and-sam/admin/guests/{g.id}", headers=auth(), json={"story_arc_ids": []}
    )
    assert r.status_code == 200
    assert r.json()["story_arc_ids"] == []

    inv = client.get("/api/i/hide-g").json()
    assert inv["story_arcs"] == []
    assert inv["show_story"] is False

    # Omitting the field on a later PATCH leaves the hide in place.
    r = client.patch(
        f"/api/w/alex-and-sam/admin/guests/{g.id}", headers=auth(), json={"side": "Alex"}
    )
    assert r.json()["story_arc_ids"] == []


def test_visible_arcs_hidden_override(db_session, wedding):
    _arc(db_session, wedding, title="Arc one")
    g = _guest(db_session, wedding, slug="hide-core", story_arc_ids=[])
    assert visible_arcs(db_session, wedding, g) == []


def test_arcless_wedding_keeps_legacy_story_fallback(client, db_session, wedding):
    # No arc rows at all + no override: show_story stays True so the frontend
    # can fall back to the legacy embedded content.story.
    g = _guest(db_session, wedding, slug="legacy-g")
    inv = client.get(f"/api/i/{g.slug}").json()
    assert inv["story_arcs"] == []
    assert inv["show_story"] is True


def test_override_of_deleted_arc_hides_story(client, db_session, wedding):
    # A targeted arc that was since deleted resolves to nothing — the page must
    # hide the section rather than fall back to placeholder story copy.
    arc = _arc(db_session, wedding, title="Doomed")
    g = _guest(db_session, wedding, slug="stale-g", story_arc_ids=[str(arc.id)])
    r = client.delete(f"/api/w/alex-and-sam/admin/story-arcs/{arc.id}", headers=auth())
    assert r.status_code == 204
    inv = client.get("/api/i/stale-g").json()
    assert inv["story_arcs"] == []
    assert inv["show_story"] is False


def test_admin_rejects_unknown_arc(client, db_session, wedding):
    g = _guest(db_session, wedding, slug="solo-y")
    import uuid

    r = client.patch(
        f"/api/w/alex-and-sam/admin/guests/{g.id}", headers=auth(),
        json={"story_arc_ids": [str(uuid.uuid4())]},
    )
    assert r.status_code == 422
