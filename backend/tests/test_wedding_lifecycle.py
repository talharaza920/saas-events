"""Phase 2 — self-serve creation, approval workflow, publication, suspension
semantics on the guest surface, and soft delete."""
from __future__ import annotations

from app.models import AuditLog, Wedding

from tests.helpers import add_guest, make_member, make_wedding, platform_auth, user_auth

ALICE = "alice@example.com"
BOB = "bob@example.com"


def _create(client, email=ALICE, slug="riley-and-sam", names="Riley & Sam"):
    return client.post(
        "/api/weddings",
        headers=user_auth(email),
        json={"couple_names": names, "slug": slug},
    )


# --- Creation wizard -------------------------------------------------------------
def test_create_wedding_from_template(client, db_session):
    r = _create(client)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "draft"
    assert body["admin_path"] == "/riley-and-sam/admin"

    # The creator owns it and the dashboard works immediately.
    me = client.get("/api/w/riley-and-sam/admin/me", headers=user_auth(ALICE))
    assert me.status_code == 200
    assert me.json()["role"] == "owner"
    # Template content was seeded and personalised.
    content = client.get("/api/w/riley-and-sam/admin/content", headers=user_auth(ALICE)).json()
    assert content["couple_names"] == "Riley & Sam"
    assert content["content"]["nav"]["brand"] == "Riley & Sam"
    # Default questions + the starter story arc came along.
    assert len(client.get("/api/w/riley-and-sam/admin/questions", headers=user_auth(ALICE)).json()) > 0
    assert len(client.get("/api/w/riley-and-sam/admin/story-arcs", headers=user_auth(ALICE)).json()) > 0
    # Audit row written.
    assert db_session.query(AuditLog).filter_by(action="wedding.create").count() == 1


def test_create_validates_slug(client):
    bad = client.post(
        "/api/weddings", headers=user_auth(ALICE),
        json={"couple_names": "A & B", "slug": "Bad Slug!"},
    )
    assert bad.status_code == 422
    reserved = client.post(
        "/api/weddings", headers=user_auth(ALICE),
        json={"couple_names": "A & B", "slug": "admin"},
    )
    assert reserved.status_code == 422
    assert "reserved" in reserved.json()["detail"].lower()
    assert _create(client).status_code == 201
    dupe = _create(client, email=BOB)
    assert dupe.status_code == 409


def test_slug_check_endpoint(client, db_session):
    make_wedding(db_session, "taken-slug")
    ok = client.get("/api/weddings/slug-check?slug=free-slug", headers=user_auth(ALICE)).json()
    assert ok["available"] is True
    taken = client.get("/api/weddings/slug-check?slug=taken-slug", headers=user_auth(ALICE)).json()
    assert taken["available"] is False and taken["suggestion"]
    reserved = client.get("/api/weddings/slug-check?slug=platform", headers=user_auth(ALICE)).json()
    assert reserved["available"] is False


def test_wedding_per_account_cap(client):
    for i in range(3):
        assert _create(client, slug=f"wed-{i}-of-alice").status_code == 201
    r = _create(client, slug="wed-too-many")
    assert r.status_code == 403


# --- Approval workflow -------------------------------------------------------------
def test_submit_queues_for_manual_review_by_default(client, db_session):
    _create(client)
    r = client.post("/api/w/riley-and-sam/admin/submit-approval", headers=user_auth(ALICE))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending_approval"
    assert body["auto_approved"] is False
    assert any(t["rule"] == "banned_words" for t in body["rule_trace"])


def test_auto_approval_when_rules_pass(client, db_session):
    # Platform admin switches auto-approval on.
    rules = client.get("/api/platform/settings/approval", headers=platform_auth()).json()
    rules["auto_approve"] = True
    assert client.put(
        "/api/platform/settings/approval", headers=platform_auth(), json=rules
    ).status_code == 200

    _create(client)
    r = client.post("/api/w/riley-and-sam/admin/submit-approval", headers=user_auth(ALICE))
    assert r.status_code == 200
    assert r.json()["auto_approved"] is True
    assert r.json()["status"] == "active"


def test_banned_word_blocks_auto_approval(client):
    rules = client.get("/api/platform/settings/approval", headers=platform_auth()).json()
    rules["auto_approve"] = True
    rules["banned_words"] = ["casino"]
    client.put("/api/platform/settings/approval", headers=platform_auth(), json=rules)

    _create(client, slug="casino-royale", names="Casino & Royale")
    r = client.post("/api/w/casino-royale/admin/submit-approval", headers=user_auth(ALICE))
    assert r.json()["status"] == "pending_approval"
    trace = {t["rule"]: t for t in r.json()["rule_trace"]}
    assert trace["banned_words"]["ok"] is False


def test_platform_approve_deny_flow(client, db_session):
    _create(client)
    client.post("/api/w/riley-and-sam/admin/submit-approval", headers=user_auth(ALICE))
    queue = client.get("/api/platform/approvals", headers=platform_auth()).json()
    assert len(queue) == 1
    wid = queue[0]["wedding"]["id"]

    # Deny → back to draft.
    r = client.post(
        f"/api/platform/weddings/{wid}/deny", headers=platform_auth(),
        json={"reason": "Please finish your details"},
    )
    assert r.json()["status"] == "draft"
    # Owner resubmits; platform approves.
    client.post("/api/w/riley-and-sam/admin/submit-approval", headers=user_auth(ALICE))
    r = client.post(f"/api/platform/weddings/{wid}/approve", headers=platform_auth(), json={})
    assert r.json()["status"] == "active"


# --- Publication + guest surface ---------------------------------------------------
def test_publish_requires_active_and_gates_guests(client, db_session):
    _create(client)
    wedding = db_session.query(Wedding).filter_by(slug="riley-and-sam").one()
    guest = add_guest(db_session, wedding, "guest-1")

    # Draft: publish refused; guest link dark.
    assert client.post(
        "/api/w/riley-and-sam/admin/publish", headers=user_auth(ALICE), json={"published": True}
    ).status_code == 409
    assert client.get(f"/api/i/{guest.slug}").status_code == 404

    # Approve, then publish → the guest link lights up.
    client.post(f"/api/platform/weddings/{wedding.id}/approve", headers=platform_auth(), json={})
    r = client.post(
        "/api/w/riley-and-sam/admin/publish", headers=user_auth(ALICE), json={"published": True}
    )
    assert r.status_code == 200 and r.json()["published"] is True
    assert client.get(f"/api/i/{guest.slug}").status_code == 200
    # Public per-wedding landing works too.
    assert client.get("/api/w/riley-and-sam/landing").status_code == 200

    # Unpublish → dark again (same neutral 404).
    client.post(
        "/api/w/riley-and-sam/admin/publish", headers=user_auth(ALICE), json={"published": False}
    )
    assert client.get(f"/api/i/{guest.slug}").status_code == 404
    assert client.get("/api/w/riley-and-sam/landing").status_code == 404


def test_admins_cannot_publish_unless_granted(client, db_session):
    w = make_wedding(db_session, "wed-a", status="active", published=False)
    make_member(db_session, w, ALICE, role="owner")
    make_member(db_session, w, BOB, role="admin")
    # Co-admin refused by default…
    assert client.post(
        "/api/w/wed-a/admin/publish", headers=user_auth(BOB), json={"published": True}
    ).status_code == 403
    # …owner grants publish rights…
    assert client.patch(
        "/api/w/wed-a/admin/settings", headers=user_auth(ALICE), json={"admins_can_publish": True}
    ).status_code == 200
    # …now the co-admin can publish.
    assert client.post(
        "/api/w/wed-a/admin/publish", headers=user_auth(BOB), json={"published": True}
    ).status_code == 200


def test_suspension_hides_guests_without_explanation(client, db_session):
    w = make_wedding(db_session, "wed-a", status="active", published=True)
    make_member(db_session, w, ALICE, role="owner")
    guest = add_guest(db_session, w, "guest-1")
    assert client.get(f"/api/i/{guest.slug}").status_code == 200

    client.post(f"/api/platform/weddings/{w.id}/suspend", headers=platform_auth(), json={})
    r = client.get(f"/api/i/{guest.slug}")
    assert r.status_code == 404
    # Identical body to a truly unknown slug — nothing hints at suspension.
    assert r.json() == client.get("/api/i/never-existed").json()

    # Reinstate → live again (published flag survived).
    client.post(f"/api/platform/weddings/{w.id}/reinstate", headers=platform_auth())
    assert client.get(f"/api/i/{guest.slug}").status_code == 200


# --- Soft delete ---------------------------------------------------------------------
def test_owner_archive_is_soft_and_reinstatable(client, db_session):
    w = make_wedding(db_session, "wed-a", status="active", published=True)
    make_member(db_session, w, ALICE, role="owner")
    guest = add_guest(db_session, w, "guest-1")

    r = client.delete("/api/w/wed-a/admin", headers=user_auth(ALICE))
    assert r.status_code == 200
    assert r.json()["status"] == "archived" and r.json()["published"] is False
    # Gone for guests and for the (now former) dashboard…
    assert client.get(f"/api/i/{guest.slug}").status_code == 404
    assert client.get("/api/w/wed-a/admin/me", headers=user_auth(ALICE)).status_code == 404
    # …data still exists; platform admin can reinstate within the undo window.
    client.post(f"/api/platform/weddings/{w.id}/reinstate", headers=platform_auth())
    assert client.get("/api/w/wed-a/admin/me", headers=user_auth(ALICE)).status_code == 200
    assert client.get("/api/w/wed-a/admin/me", headers=user_auth(ALICE)).json()["wedding_status"] == "draft"
