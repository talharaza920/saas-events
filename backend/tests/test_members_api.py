"""Phase 3 — co-admin invites, acceptance, revocation, ownership transfer.
Every mutation is owner-only; cross-tenant negatives included."""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.emailer import OUTBOX

from tests.helpers import make_member, make_wedding, platform_auth, user_auth

OWNER = "owner@example.com"
COADMIN = "coadmin@example.com"
STRANGER = "stranger@example.com"


def _invite(client, *, email=COADMIN, role="admin", slug="wed-a", auth_email=OWNER):
    return client.post(
        f"/api/w/{slug}/admin/members",
        headers=user_auth(auth_email),
        json={"email": email, "role": role},
    )


def _token_from(accept_path: str) -> str:
    return parse_qs(urlparse(accept_path).query)["token"][0]


def _accept(client, token: str, *, email=COADMIN):
    return client.post("/api/invites/accept", headers=user_auth(email), json={"token": token})


def _setup(db):
    w = make_wedding(db, "wed-a")
    make_member(db, w, OWNER, role="owner")
    return w


# --- Invite + accept ---------------------------------------------------------------
def test_invite_and_accept_flow(client, db_session):
    _setup(db_session)
    OUTBOX.clear()
    r = _invite(client)
    assert r.status_code == 201
    body = r.json()
    assert body["member"]["status"] == "invited"
    assert body["member"]["role"] == "admin"
    token = _token_from(body["accept_path"])
    # The invite email went to the co-admin.
    assert any(e.to == COADMIN for e in OUTBOX)

    # Before accepting: no access.
    assert client.get("/api/w/wed-a/admin/guests", headers=user_auth(COADMIN)).status_code == 404
    # Accept (signed in with the SAME email) → immediate access.
    r = _accept(client, token)
    assert r.status_code == 200
    assert r.json()["wedding_slug"] == "wed-a"
    assert client.get("/api/w/wed-a/admin/guests", headers=user_auth(COADMIN)).status_code == 200
    # The dashboard list shows it with the invited role.
    rows = client.get("/api/me/weddings", headers=user_auth(COADMIN)).json()
    assert [(r["slug"], r["role"]) for r in rows] == [("wed-a", "admin")]


def test_accept_requires_matching_email(client, db_session):
    _setup(db_session)
    token = _token_from(_invite(client).json()["accept_path"])
    # A different signed-in account gets the same "invalid" 404 (no oracle).
    assert _accept(client, token, email=STRANGER).status_code == 404
    # The right account still works afterwards.
    assert _accept(client, token).status_code == 200


def test_invite_token_is_single_use(client, db_session):
    _setup(db_session)
    token = _token_from(_invite(client).json()["accept_path"])
    assert _accept(client, token).status_code == 200
    assert _accept(client, token).status_code == 404


def test_expired_invite_is_refused(client, db_session):
    from datetime import datetime, timedelta, timezone

    from app.models import WeddingMember

    _setup(db_session)
    token = _token_from(_invite(client).json()["accept_path"])
    m = db_session.query(WeddingMember).filter_by(invited_email=COADMIN).one()
    m.invite_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()
    assert _accept(client, token).status_code == 404


def test_invite_is_owner_only_and_tenant_scoped(client, db_session):
    w = _setup(db_session)
    make_member(db_session, w, COADMIN, role="admin")
    # A co-admin cannot invite (403 — member but under-role).
    assert _invite(client, email="x@example.com", auth_email=COADMIN).status_code == 403
    # A stranger gets 404 (existence hidden).
    assert _invite(client, email="x@example.com", auth_email=STRANGER).status_code == 404
    # Owner of another wedding can't reach this one.
    b = make_wedding(db_session, "wed-b")
    make_member(db_session, b, "other-owner@example.com", role="owner")
    assert _invite(client, auth_email="other-owner@example.com").status_code == 404


def test_duplicate_active_member_is_409(client, db_session):
    _setup(db_session)
    token = _token_from(_invite(client).json()["accept_path"])
    _accept(client, token)
    assert _invite(client).status_code == 409


# --- Revoke + roles ------------------------------------------------------------------
def test_revoke_kills_access_immediately(client, db_session):
    _setup(db_session)
    token = _token_from(_invite(client).json()["accept_path"])
    _accept(client, token)
    members = client.get("/api/w/wed-a/admin/members", headers=user_auth(OWNER)).json()
    target = next(m for m in members if m["email"] == COADMIN)

    r = client.delete(f"/api/w/wed-a/admin/members/{target['id']}", headers=user_auth(OWNER))
    assert r.status_code == 200 and r.json()["status"] == "revoked"
    assert client.get("/api/w/wed-a/admin/guests", headers=user_auth(COADMIN)).status_code == 404


def test_cannot_remove_last_owner(client, db_session):
    _setup(db_session)
    members = client.get("/api/w/wed-a/admin/members", headers=user_auth(OWNER)).json()
    owner_row = members[0]
    assert client.delete(
        f"/api/w/wed-a/admin/members/{owner_row['id']}", headers=user_auth(OWNER)
    ).status_code == 409
    assert client.patch(
        f"/api/w/wed-a/admin/members/{owner_row['id']}",
        headers=user_auth(OWNER), json={"role": "admin"},
    ).status_code == 409


def test_transfer_ownership(client, db_session):
    _setup(db_session)
    token = _token_from(_invite(client).json()["accept_path"])
    _accept(client, token)
    members = client.get("/api/w/wed-a/admin/members", headers=user_auth(OWNER)).json()
    target = next(m for m in members if m["email"] == COADMIN)

    r = client.post(
        f"/api/w/wed-a/admin/members/{target['id']}/transfer-ownership",
        headers=user_auth(OWNER),
    )
    assert r.status_code == 200 and r.json()["role"] == "owner"
    # The old owner is now an admin: content yes, member management no.
    assert client.get("/api/w/wed-a/admin/guests", headers=user_auth(OWNER)).status_code == 200
    assert _invite(client, email="y@example.com", auth_email=OWNER).status_code == 403
    # The new owner can manage members.
    assert _invite(client, email="y@example.com", auth_email=COADMIN).status_code == 201


def test_transfer_requires_accepted_member(client, db_session):
    _setup(db_session)
    invited = _invite(client).json()["member"]
    assert client.post(
        f"/api/w/wed-a/admin/members/{invited['id']}/transfer-ownership",
        headers=user_auth(OWNER),
    ).status_code == 409


def test_member_ids_are_tenant_scoped(client, db_session):
    _setup(db_session)
    b = make_wedding(db_session, "wed-b")
    other = make_member(db_session, b, "other@example.com", role="admin")
    # B's member id through A's path → 404 (owner of A, but foreign row).
    assert client.delete(
        f"/api/w/wed-a/admin/members/{other.id}", headers=user_auth(OWNER)
    ).status_code == 404
    assert client.patch(
        f"/api/w/wed-a/admin/members/{other.id}", headers=user_auth(OWNER), json={"role": "owner"}
    ).status_code == 404


def test_reinvite_after_revoke_reuses_row(client, db_session):
    _setup(db_session)
    token = _token_from(_invite(client).json()["accept_path"])
    _accept(client, token)
    members = client.get("/api/w/wed-a/admin/members", headers=user_auth(OWNER)).json()
    target = next(m for m in members if m["email"] == COADMIN)
    client.delete(f"/api/w/wed-a/admin/members/{target['id']}", headers=user_auth(OWNER))

    r = _invite(client)  # same email again
    assert r.status_code == 201
    token2 = _token_from(r.json()["accept_path"])
    assert _accept(client, token2).status_code == 200
    # Still one row for this email (reused, not duplicated).
    rows = client.get("/api/w/wed-a/admin/members", headers=user_auth(OWNER)).json()
    assert sum(1 for m in rows if m["email"] == COADMIN) == 1


def test_platform_admin_bypasses_owner_gate(client, db_session):
    _setup(db_session)
    assert client.get("/api/w/wed-a/admin/members", headers=platform_auth()).status_code == 200
