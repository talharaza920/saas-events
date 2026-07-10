"""P2 hardening (REVIEW_BACKLOG items 11-18).

  11 — check-then-insert races surface as 409, never 500
  12 — accepting an invite while already a member merges cleanly
  13 — content JSON blobs are bounded (depth / node count / string size)
  14 — import upload caps (bytes + rows) before parsing bounds anything
  15 — ensure_profile commits only when the profile row actually changed
  17 — tz-aware UTC helpers behave on naive (SQLite) input
  18 — optional per-wedding RSVP deadline closes guest submits
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

import app.routers.me as me_router
from app.auth import AuthedUser
from app.authz import ensure_profile
from app.models import MemberRole, MemberStatus, WeddingMember
from app.timeutil import as_utc, db_bind_utc, utcnow
from tests.helpers import add_guest, make_member, make_wedding, user_auth, user_sub

ALICE = "alice@example.com"
BOB = "bob@example.com"


# --- 11: races → 409 ---------------------------------------------------------
def test_wedding_slug_race_is_409_not_500(client, db_session, monkeypatch):
    # Simulate the check-then-insert race: the availability pre-check never sees
    # the winner, so the second create must be caught at the unique constraint.
    monkeypatch.setattr(me_router, "_slug_taken", lambda db, slug: False)
    payload = {"couple_names": "Alex & Sam", "slug": "race-slug"}
    r1 = client.post("/api/weddings", headers=user_auth(ALICE), json=payload)
    assert r1.status_code == 201
    r2 = client.post("/api/weddings", headers=user_auth(BOB), json=payload)
    assert r2.status_code == 409
    assert "taken" in r2.json()["detail"]


# --- 12: invite-accept for an existing member --------------------------------
def test_accept_invite_when_already_member_merges(client, db_session):
    w = make_wedding(db_session, "merge-wed")
    make_member(db_session, w, ALICE, role="owner")
    # Bob is ALREADY an active owner, but his membership row carries an old
    # sign-in email — so the owner can re-invite his new address.
    db_session.add(
        WeddingMember(
            wedding_id=w.id,
            user_id=user_sub(BOB),
            invited_email="old-bob@example.com",
            role=MemberRole.owner,
            status=MemberStatus.active,
        )
    )
    db_session.commit()

    invited = client.post(
        "/api/w/merge-wed/admin/members", headers=user_auth(ALICE),
        json={"email": BOB, "role": "admin"},
    )
    assert invited.status_code == 201
    token = invited.json()["accept_path"].split("token=")[1]

    # Without the guard this violates uq_member_wedding_user → 500. With it,
    # the redundant invite is consumed and the EXISTING membership reported.
    r = client.post("/api/invites/accept", headers=user_auth(BOB), json={"token": token})
    assert r.status_code == 200
    assert r.json()["role"] == "owner"  # the existing role, not the invite's

    rows = db_session.query(WeddingMember).filter_by(
        wedding_id=w.id, invited_email=BOB
    ).all()
    assert len(rows) == 1 and rows[0].status is MemberStatus.revoked
    # And the original membership is untouched.
    kept = db_session.query(WeddingMember).filter_by(
        wedding_id=w.id, user_id=user_sub(BOB), status=MemberStatus.active
    ).one()
    assert kept.role is MemberRole.owner


# --- 13: bounded JSON on content endpoints ------------------------------------
def _owner_wedding(db, slug):
    w = make_wedding(db, slug)
    make_member(db, w, ALICE, role="owner")
    return w


def _nested(depth: int) -> dict:
    d: dict = {"x": 1}
    for _ in range(depth):
        d = {"a": d}
    return d


def test_content_rejects_deep_nesting(client, db_session):
    _owner_wedding(db_session, "deep-wed")
    r = client.patch(
        "/api/w/deep-wed/admin/content", headers=user_auth(ALICE),
        json={"content": _nested(30)},
    )
    assert r.status_code == 422


def test_content_rejects_huge_string_and_node_count(client, db_session):
    _owner_wedding(db_session, "big-wed")
    r = client.patch(
        "/api/w/big-wed/admin/content", headers=user_auth(ALICE),
        json={"content": {"note": "x" * 50_001}},
    )
    assert r.status_code == 422
    r = client.patch(
        "/api/w/big-wed/admin/content", headers=user_auth(ALICE),
        json={"content": {"items": list(range(25_001))}},
    )
    assert r.status_code == 422


def test_content_accepts_normal_payloads(client, db_session):
    _owner_wedding(db_session, "ok-wed")
    r = client.patch(
        "/api/w/ok-wed/admin/content", headers=user_auth(ALICE),
        json={"content": {"faq": {"items": [{"q": "Dress code?", "a": "Garden formal"}]}}},
    )
    assert r.status_code == 200


def test_story_arc_content_is_bounded(client, db_session):
    _owner_wedding(db_session, "arc-wed")
    r = client.post(
        "/api/w/arc-wed/admin/story-arcs", headers=user_auth(ALICE),
        json={"title": "Bomb", "content": _nested(30)},
    )
    assert r.status_code == 422


# --- 14: import caps -----------------------------------------------------------
def test_import_rejects_oversize_file(client, db_session):
    _owner_wedding(db_session, "imp-wed")
    blob = b"x" * (15 * 1024 * 1024 + 1)
    r = client.post(
        "/api/w/imp-wed/admin/import", headers=user_auth(ALICE),
        files={"file": ("guests.csv", blob, "text/csv")},
    )
    assert r.status_code == 413


def test_import_rejects_too_many_rows(client, db_session):
    _owner_wedding(db_session, "rows-wed")
    csv_text = "Row Type,Name\n" + "\n".join("Primary,G" for _ in range(5_001))
    r = client.post(
        "/api/w/rows-wed/admin/import", headers=user_auth(ALICE),
        files={"file": ("guests.csv", io.BytesIO(csv_text.encode()), "text/csv")},
    )
    assert r.status_code == 422
    assert "too many rows" in r.json()["detail"]


# --- 15: ensure_profile commit discipline ---------------------------------------
def test_ensure_profile_commits_only_on_change(db_session):
    commits = {"n": 0}
    real_commit = db_session.commit

    def counting_commit():
        commits["n"] += 1
        real_commit()

    db_session.commit = counting_commit
    user = AuthedUser(sub="dev:carol@example.com", email="carol@example.com", via="dev")
    ensure_profile(db_session, user)  # first request creates the profile
    assert commits["n"] == 1
    ensure_profile(db_session, user)  # pure read — must not commit
    ensure_profile(db_session, user)
    assert commits["n"] == 1
    changed = AuthedUser(sub="dev:carol@example.com", email="carol+new@example.com", via="dev")
    ensure_profile(db_session, changed)  # email drift — resync commits once
    assert commits["n"] == 2


# --- 17: tz helpers ---------------------------------------------------------------
def test_as_utc_normalizes_naive_and_aware():
    naive = datetime(2026, 7, 1, 12, 0, 0)
    aware = as_utc(naive)
    assert aware.tzinfo is timezone.utc and aware.hour == 12
    already = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert as_utc(already) == already
    assert as_utc(None) is None


def test_db_bind_utc_is_naive_on_sqlite(db_session):
    bound = db_bind_utc(db_session, utcnow())
    assert bound.tzinfo is None  # tests run on SQLite


# --- 18: RSVP deadline --------------------------------------------------------------
def _deadline_setup(db, slug, deadline: str | None):
    w = make_wedding(db, slug)
    make_member(db, w, ALICE, role="owner")
    if deadline is not None:
        w.settings = {"rsvp_deadline": deadline}
        db.commit()
    return add_guest(db, w, f"guest-{slug}")


def test_settings_validates_rsvp_deadline(client, db_session):
    make_member(db_session, make_wedding(db_session, "dl-wed"), ALICE, role="owner")
    r = client.patch(
        "/api/w/dl-wed/admin/settings", headers=user_auth(ALICE),
        json={"rsvp_deadline": "not-a-date"},
    )
    assert r.status_code == 422
    r = client.patch(
        "/api/w/dl-wed/admin/settings", headers=user_auth(ALICE),
        json={"rsvp_deadline": "2030-06-01"},
    )
    assert r.status_code == 200 and r.json()["rsvp_deadline"] == "2030-06-01"
    # Empty string clears the setting entirely.
    r = client.patch(
        "/api/w/dl-wed/admin/settings", headers=user_auth(ALICE),
        json={"rsvp_deadline": ""},
    )
    assert r.status_code == 200 and "rsvp_deadline" not in r.json()


def test_rsvp_closed_after_deadline(client, db_session):
    guest = _deadline_setup(db_session, "past-wed", "2020-01-01")
    r = client.get(f"/api/i/{guest.slug}")
    assert r.status_code == 200 and r.json()["rsvp_open"] is False  # invite still renders
    r = client.post(
        f"/api/i/{guest.slug}/rsvp",
        json={"attending": True, "companions": [], "answers": []},
    )
    assert r.status_code == 403
    assert "deadline" in r.json()["detail"].lower()


def test_rsvp_open_without_or_before_deadline(client, db_session):
    guest = _deadline_setup(db_session, "open-wed", None)
    assert client.get(f"/api/i/{guest.slug}").json()["rsvp_open"] is True
    future_guest = _deadline_setup(db_session, "future-wed", "2999-12-31")
    r = client.post(
        f"/api/i/{future_guest.slug}/rsvp",
        json={"attending": True, "companions": [], "answers": []},
    )
    assert r.status_code == 200


def test_garbage_deadline_never_locks_guests_out(client, db_session):
    guest = _deadline_setup(db_session, "junk-wed", "eventually")
    r = client.post(
        f"/api/i/{guest.slug}/rsvp",
        json={"attending": True, "companions": [], "answers": []},
    )
    assert r.status_code == 200
