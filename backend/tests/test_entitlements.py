"""Phase 5 — plans & entitlements: definition, assignment, and server-side
enforcement at every create seam. Limits are create-only (never destructive)."""
from __future__ import annotations

from tests.helpers import add_guest, make_member, make_wedding, platform_auth, user_auth

ALICE = "alice@example.com"


def _setup(db):
    w = make_wedding(db, "wed-a")
    make_member(db, w, ALICE, role="owner")
    return w


def _make_plan(client, name="Free", *, entitlements, is_default=False):
    r = client.post(
        "/api/platform/plans", headers=platform_auth(),
        json={"name": name, "entitlements": entitlements, "is_default": is_default},
    )
    assert r.status_code == 201
    return r.json()


def _assign(client, wedding_id, plan_id=None, overrides=None):
    return client.put(
        f"/api/platform/weddings/{wedding_id}/plan", headers=platform_auth(),
        json={"plan_id": plan_id, "overrides": overrides},
    )


# --- Plan CRUD -------------------------------------------------------------------
def test_plan_crud_and_default_flag(client):
    free = _make_plan(client, "Free", entitlements={"max_guests": 2}, is_default=True)
    plus = _make_plan(client, "Plus", entitlements={"max_guests": 300}, is_default=False)
    # Making Plus default clears Free's flag.
    r = client.patch(
        f"/api/platform/plans/{plus['id']}", headers=platform_auth(), json={"is_default": True}
    )
    assert r.json()["is_default"] is True
    plans = {p["name"]: p for p in client.get("/api/platform/plans", headers=platform_auth()).json()}
    assert plans["Free"]["is_default"] is False
    # Duplicate names refused.
    assert client.post(
        "/api/platform/plans", headers=platform_auth(),
        json={"name": "Free", "entitlements": {}},
    ).status_code == 409


def test_default_plan_applies_without_assignment(client, db_session):
    _setup(db_session)
    _make_plan(client, "Free", entitlements={"max_guests": 1}, is_default=True)
    auth = user_auth(ALICE)
    assert client.post(
        "/api/w/wed-a/admin/guests", headers=auth, json={"greeting_name": "One"}
    ).status_code == 201
    r = client.post("/api/w/wed-a/admin/guests", headers=auth, json={"greeting_name": "Two"})
    assert r.status_code == 403
    assert "limit" in r.json()["detail"].lower()
    assert "contact us" in r.json()["detail"].lower()  # dormant upgrade hint


# --- Enforcement seams ------------------------------------------------------------
def test_guest_cap_enforced_on_create_not_retroactively(client, db_session):
    w = _setup(db_session)
    add_guest(db_session, w, "g-1")
    add_guest(db_session, w, "g-2")
    plan = _make_plan(client, "Tiny", entitlements={"max_guests": 1})
    _assign(client, w.id, plan["id"])
    auth = user_auth(ALICE)
    # Existing guests above the cap are untouched (still listed, editable)…
    rows = client.get("/api/w/wed-a/admin/guests", headers=auth).json()
    assert len(rows) == 2
    # …but new adds are blocked.
    assert client.post(
        "/api/w/wed-a/admin/guests", headers=auth, json={"greeting_name": "Three"}
    ).status_code == 403


def test_question_cap_and_feature_toggles(client, db_session):
    w = _setup(db_session)
    plan = _make_plan(
        client, "Basic",
        entitlements={"max_custom_questions": 0, "export_enabled": False, "import_enabled": False},
    )
    _assign(client, w.id, plan["id"])
    auth = user_auth(ALICE)
    # Questions feature off (cap 0).
    assert client.post(
        "/api/w/wed-a/admin/questions", headers=auth,
        json={"prompt": "Song?", "qtype": "text"},
    ).status_code == 403
    # Export / import off.
    assert client.get("/api/w/wed-a/admin/export.xlsx", headers=auth).status_code == 403
    assert client.get("/api/w/wed-a/admin/template.xlsx", headers=auth).status_code == 403


def test_member_cap_enforced_on_invite(client, db_session):
    w = _setup(db_session)
    plan = _make_plan(client, "Solo", entitlements={"max_members": 1})
    _assign(client, w.id, plan["id"])
    r = client.post(
        "/api/w/wed-a/admin/members", headers=user_auth(ALICE),
        json={"email": "helper@example.com"},
    )
    assert r.status_code == 403


def test_overrides_beat_plan(client, db_session):
    w = _setup(db_session)
    plan = _make_plan(client, "Tiny", entitlements={"max_guests": 0})
    _assign(client, w.id, plan["id"])
    auth = user_auth(ALICE)
    assert client.post(
        "/api/w/wed-a/admin/guests", headers=auth, json={"greeting_name": "X"}
    ).status_code == 403
    # RT grants a per-wedding exception without changing the plan.
    r = _assign(client, w.id, plan["id"], overrides={"max_guests": 50})
    assert r.status_code == 200
    assert r.json()["effective"]["max_guests"] == 50
    assert client.post(
        "/api/w/wed-a/admin/guests", headers=auth, json={"greeting_name": "X"}
    ).status_code == 201


def test_entitlements_surface_in_admin_me(client, db_session):
    w = _setup(db_session)
    plan = _make_plan(client, "Plus", entitlements={"max_guests": 300, "wishes_enabled": False})
    _assign(client, w.id, plan["id"])
    me = client.get("/api/w/wed-a/admin/me", headers=user_auth(ALICE)).json()
    assert me["entitlements"]["max_guests"] == 300
    assert me["entitlements"]["wishes_enabled"] is False
    # Unspecified keys fall back to platform defaults.
    assert "max_members" in me["entitlements"]


def test_import_respects_guest_cap(client, db_session):
    import io

    import openpyxl

    w = _setup(db_session)
    plan = _make_plan(client, "Tiny", entitlements={"max_guests": 1})
    _assign(client, w.id, plan["id"])
    # A workbook that would create two new invitees.
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Id", "Person", "Greeting", "Name"])
    ws.append(["", "Primary", "Riley", "Riley"])
    ws.append(["", "Primary", "Sam", "Sam"])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post(
        "/api/w/wed-a/admin/import?commit=0",
        headers=user_auth(ALICE),
        files={"file": ("guests.xlsx", buf.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 403


def test_wishes_toggle_gates_guestbook(client, db_session):
    w = _setup(db_session)
    guest = add_guest(db_session, w, "g-1")
    plan = _make_plan(client, "NoWishes", entitlements={"wishes_enabled": False})
    _assign(client, w.id, plan["id"])
    # Guest guestbook surface goes dark (404 — the section simply doesn't exist).
    assert client.get(f"/api/i/{guest.slug}/wishes").status_code == 404
    assert client.post(
        f"/api/i/{guest.slug}/wishes", json={"name": "R", "message": "hi"}
    ).status_code == 404


def test_clearing_assignment_returns_to_default(client, db_session):
    w = _setup(db_session)
    _make_plan(client, "Free", entitlements={"max_guests": 5}, is_default=True)
    plan = _make_plan(client, "Tiny", entitlements={"max_guests": 0})
    _assign(client, w.id, plan["id"])
    r = _assign(client, w.id, None)  # clear → default plan
    assert r.status_code == 200
    assert r.json()["effective"]["max_guests"] == 5
