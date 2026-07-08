"""Phase 1 — identity & the membership authz seam.

Pins the guarantees from app/authz.py:
  401 unauthenticated · 404 non-member (existence hidden) · 403 under-role ·
  suspended = read-only · archived = gone for members · disabled account = 403 ·
  platform admin passes everything. Plus /api/me and /api/me/weddings.
"""
from __future__ import annotations

from app.models import Profile

from tests.helpers import add_guest, make_member, make_wedding, platform_auth, user_auth, user_sub

ALICE = "alice@example.com"
BOB = "bob@example.com"


# --- /api/me ------------------------------------------------------------------
def test_me_creates_profile_lazily(client, db_session):
    r = client.get("/api/me", headers=user_auth(ALICE))
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == ALICE
    assert body["is_platform_admin"] is False
    assert db_session.get(Profile, user_sub(ALICE)) is not None


def test_me_platform_admin_flag(client):
    assert client.get("/api/me", headers=platform_auth()).json()["is_platform_admin"] is True


def test_me_requires_auth(client):
    assert client.get("/api/me").status_code == 401


def test_my_weddings_lists_only_memberships(client, db_session):
    a = make_wedding(db_session, "wed-a")
    b = make_wedding(db_session, "wed-b")
    make_member(db_session, a, ALICE, role="owner")
    make_member(db_session, b, BOB, role="owner")
    add_guest(db_session, a, "g-1")

    rows = client.get("/api/me/weddings", headers=user_auth(ALICE)).json()
    assert [(r["slug"], r["role"], r["guest_count"]) for r in rows] == [("wed-a", "owner", 1)]
    assert client.get("/api/me/weddings", headers=user_auth(BOB)).json()[0]["slug"] == "wed-b"


# --- Role gates -----------------------------------------------------------------
def test_admin_role_can_edit_but_not_manage(client, db_session):
    w = make_wedding(db_session, "wed-a")
    make_member(db_session, w, ALICE, role="admin")
    auth = user_auth(ALICE)
    # Content/guest editing works for a co-admin…
    assert client.get("/api/w/wed-a/admin/guests", headers=auth).status_code == 200
    assert client.post(
        "/api/w/wed-a/admin/guests", headers=auth, json={"greeting_name": "Riley"}
    ).status_code == 201
    # …but owner-only surfaces are 403 (role too low, not 404 — they ARE a member).
    assert client.post(
        "/api/w/wed-a/admin/members", headers=auth, json={"email": "x@example.com"}
    ).status_code == 403
    assert client.delete("/api/w/wed-a/admin", headers=auth).status_code == 403
    assert client.post("/api/w/wed-a/admin/submit-approval", headers=auth).status_code == 403


def test_non_member_gets_404_everywhere(client, db_session):
    w = make_wedding(db_session, "wed-a")
    make_member(db_session, w, ALICE, role="owner")
    stranger = user_auth(BOB)
    for path in ("me", "guests", "questions", "content", "summary", "members"):
        assert client.get(f"/api/w/wed-a/admin/{path}", headers=stranger).status_code == 404
    # Identical to a wedding that does not exist:
    assert client.get("/api/w/ghost/admin/me", headers=stranger).status_code == 404


def test_unauthenticated_is_401(client, db_session):
    make_wedding(db_session, "wed-a")
    assert client.get("/api/w/wed-a/admin/guests").status_code == 401


def test_platform_admin_passes_all_wedding_gates(client, db_session):
    w = make_wedding(db_session, "wed-a")
    r = client.get("/api/w/wed-a/admin/me", headers=platform_auth())
    assert r.status_code == 200
    assert r.json()["role"] == "platform"
    # Including owner-only surfaces:
    assert client.get("/api/w/wed-a/admin/members", headers=platform_auth()).status_code == 200


# --- Suspension / archive / disabled ------------------------------------------
def test_suspended_wedding_is_read_only_for_members(client, db_session):
    w = make_wedding(db_session, "wed-a", status="suspended")
    make_member(db_session, w, ALICE, role="owner")
    auth = user_auth(ALICE)
    # Reads still work (the dashboard shows a banner)…
    me = client.get("/api/w/wed-a/admin/me", headers=auth)
    assert me.status_code == 200
    assert me.json()["wedding_status"] == "suspended"
    assert client.get("/api/w/wed-a/admin/guests", headers=auth).status_code == 200
    # …every mutation is refused:
    r = client.post("/api/w/wed-a/admin/guests", headers=auth, json={"greeting_name": "X"})
    assert r.status_code == 403
    assert "suspended" in r.json()["detail"].lower()
    assert client.patch(
        "/api/w/wed-a/admin/content", headers=auth, json={"couple_names": "New"}
    ).status_code == 403
    # Platform admin can still operate on a suspended tenant.
    assert client.post(
        "/api/w/wed-a/admin/guests", headers=platform_auth(), json={"greeting_name": "Y"}
    ).status_code == 201


def test_archived_wedding_is_gone_for_members(client, db_session):
    w = make_wedding(db_session, "wed-a", status="archived")
    make_member(db_session, w, ALICE, role="owner")
    assert client.get("/api/w/wed-a/admin/me", headers=user_auth(ALICE)).status_code == 404
    # …but the platform admin keeps access (undo window).
    assert client.get("/api/w/wed-a/admin/me", headers=platform_auth()).status_code == 200
    # It still appears in the member's dashboard list, marked archived.
    rows = client.get("/api/me/weddings", headers=user_auth(ALICE)).json()
    assert rows[0]["status"] == "archived"


def test_disabled_account_is_refused(client, db_session):
    w = make_wedding(db_session, "wed-a")
    make_member(db_session, w, ALICE, role="owner")
    client.get("/api/me", headers=user_auth(ALICE))  # materialize the profile
    profile = db_session.get(Profile, user_sub(ALICE))
    profile.disabled = True
    db_session.commit()
    assert client.get("/api/me", headers=user_auth(ALICE)).status_code == 403
    assert client.get("/api/w/wed-a/admin/guests", headers=user_auth(ALICE)).status_code == 403


def test_revoked_membership_loses_access_immediately(client, db_session):
    from app.models import MemberStatus

    w = make_wedding(db_session, "wed-a")
    m = make_member(db_session, w, ALICE, role="admin")
    assert client.get("/api/w/wed-a/admin/guests", headers=user_auth(ALICE)).status_code == 200
    m.status = MemberStatus.revoked
    db_session.commit()
    assert client.get("/api/w/wed-a/admin/guests", headers=user_auth(ALICE)).status_code == 404
