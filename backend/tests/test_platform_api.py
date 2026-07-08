"""Phase 4 — the platform (super admin) console API. The gate itself + the
weddings/users/settings/stats/audit surfaces."""
from __future__ import annotations

from tests.helpers import add_guest, make_member, make_wedding, platform_auth, user_auth, user_sub

ALICE = "alice@example.com"


# --- The gate ---------------------------------------------------------------------
def test_platform_endpoints_require_platform_admin(client, db_session):
    make_wedding(db_session, "wed-a")
    for path in ("/weddings", "/approvals", "/users", "/stats", "/audit",
                 "/settings/approval", "/plans", "/admins"):
        assert client.get(f"/api/platform{path}").status_code == 401
        assert client.get(f"/api/platform{path}", headers=user_auth(ALICE)).status_code == 403
        assert client.get(f"/api/platform{path}", headers=platform_auth()).status_code == 200


def test_admin_emails_env_is_bootstrap_platform_admin(make_client, db_session, monkeypatch):
    """The ADMIN_EMAILS fallback grants platform access to that Supabase account."""
    import app.auth as auth_module

    client = make_client(admin_emails="boss@example.com")

    def fake(settings, token):
        return {"id": "boss-1", "email": "boss@example.com",
                "email_confirmed_at": "2026-01-01T00:00:00Z"}

    monkeypatch.setattr(auth_module, "verify_supabase_token", fake)
    r = client.get("/api/platform/weddings", headers={"Authorization": "Bearer supabase-token"})
    assert r.status_code == 200


# --- Weddings view -------------------------------------------------------------------
def test_weddings_view_rolls_up(client, db_session):
    w = make_wedding(db_session, "wed-a")
    make_member(db_session, w, ALICE, role="owner")
    add_guest(db_session, w, "g-1")
    add_guest(db_session, w, "g-2")
    make_wedding(db_session, "wed-b", status="draft", published=False)

    rows = client.get("/api/platform/weddings", headers=platform_auth()).json()
    assert len(rows) == 2
    a = next(r for r in rows if r["slug"] == "wed-a")
    assert a["guest_count"] == 2
    assert a["member_count"] == 1
    assert a["owner_email"] == ALICE

    drafts = client.get("/api/platform/weddings?status=draft", headers=platform_auth()).json()
    assert [r["slug"] for r in drafts] == ["wed-b"]


# --- Users view ------------------------------------------------------------------------
def test_users_view_and_disable(client, db_session):
    w = make_wedding(db_session, "wed-a")
    make_member(db_session, w, ALICE, role="owner")
    client.get("/api/me", headers=user_auth(ALICE))  # materialize the profile

    users = client.get("/api/platform/users", headers=platform_auth()).json()
    alice = next(u for u in users if u["email"] == ALICE)
    assert alice["wedding_count"] == 1 and alice["disabled"] is False

    r = client.post(
        f"/api/platform/users/{user_sub(ALICE)}/disable",
        headers=platform_auth(), json={"disabled": True},
    )
    assert r.status_code == 200 and r.json()["disabled"] is True
    assert client.get("/api/me", headers=user_auth(ALICE)).status_code == 403
    # Re-enable restores access.
    client.post(
        f"/api/platform/users/{user_sub(ALICE)}/disable",
        headers=platform_auth(), json={"disabled": False},
    )
    assert client.get("/api/me", headers=user_auth(ALICE)).status_code == 200


def test_cannot_disable_own_account(client):
    client.get("/api/me", headers=platform_auth())
    r = client.post(
        "/api/platform/users/dev/disable", headers=platform_auth(), json={"disabled": True}
    )
    assert r.status_code == 409


# --- Platform admins management ----------------------------------------------------------
def test_grant_and_revoke_platform_admin(client, db_session):
    client.get("/api/me", headers=user_auth(ALICE))  # profile row required
    r = client.post(f"/api/platform/admins/{user_sub(ALICE)}", headers=platform_auth())
    assert r.status_code == 201
    # Alice can now use the console…
    assert client.get("/api/platform/stats", headers=user_auth(ALICE)).status_code == 200
    # …until revoked.
    client.delete(f"/api/platform/admins/{user_sub(ALICE)}", headers=platform_auth())
    assert client.get("/api/platform/stats", headers=user_auth(ALICE)).status_code == 403


# --- Settings / stats / audit --------------------------------------------------------------
def test_approval_settings_round_trip(client):
    rules = client.get("/api/platform/settings/approval", headers=platform_auth()).json()
    assert rules["auto_approve"] is False  # default: manual review
    rules.update({"auto_approve": True, "banned_words": ["spam"]})
    put = client.put("/api/platform/settings/approval", headers=platform_auth(), json=rules)
    assert put.status_code == 200
    again = client.get("/api/platform/settings/approval", headers=platform_auth()).json()
    assert again["auto_approve"] is True and again["banned_words"] == ["spam"]


def test_stats_and_audit_tail(client, db_session):
    w = make_wedding(db_session, "wed-a")
    make_member(db_session, w, ALICE, role="owner")
    add_guest(db_session, w, "g-1")
    client.get("/api/me", headers=user_auth(ALICE))
    # A mutating admin action writes audit rows.
    client.post(
        "/api/w/wed-a/admin/publish", headers=user_auth(ALICE), json={"published": False}
    )

    stats = client.get("/api/platform/stats", headers=platform_auth()).json()
    assert stats["weddings_by_status"].get("active") == 1
    assert stats["total_guests"] == 1
    assert stats["total_users"] >= 1

    tail = client.get("/api/platform/audit", headers=platform_auth()).json()
    assert any(e["action"] == "wedding.unpublish" for e in tail)
    # Scoped by wedding too.
    scoped = client.get(
        f"/api/platform/audit?wedding_id={w.id}", headers=platform_auth()
    ).json()
    assert all(e["wedding_id"] == str(w.id) for e in scoped)
