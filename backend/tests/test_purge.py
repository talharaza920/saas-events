"""Archived-wedding purge (REVIEW_BACKLOG P1-9).

Archive is a soft delete with a 30-day undo; past the window the purge job
hard-deletes the tenant (guests/PII gone), keeps the audit trail with
`wedding_id` nulled, and never touches recent archives, NULL-timestamp rows,
or live weddings. Triggered from the console (platform admin) or the cron
endpoint (shared secret; 404 when unconfigured).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import AuditLog, Guest, Wedding
from tests.helpers import add_guest, make_member, make_wedding, platform_auth, user_auth

OWNER = "owner@example.com"


def _archive(db, wedding, days_ago: int | None):
    wedding.status = "archived"
    wedding.published = False
    wedding.archived_at = (
        None if days_ago is None else datetime.now(timezone.utc) - timedelta(days=days_ago)
    )
    db.commit()


def test_purge_hard_deletes_past_window_and_keeps_audit(client, db_session):
    w = make_wedding(db_session, "wed-old")
    make_member(db_session, w, OWNER)
    add_guest(db_session, w, "old-guest")
    db_session.add(AuditLog(wedding_id=w.id, action="wedding.archive", detail={}))
    _archive(db_session, w, days_ago=31)
    wid = w.id

    r = client.post("/api/platform/purge-archived", headers=platform_auth())
    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert r.json()["purged"][0]["slug"] == "wed-old"

    assert db_session.get(Wedding, wid) is None
    assert db_session.execute(select(Guest).where(Guest.slug == "old-guest")).first() is None
    # Trail kept, pointer nulled; plus the purge record itself.
    trail = db_session.execute(select(AuditLog)).scalars().all()
    assert all(a.wedding_id is None for a in trail)
    assert any(a.action == "wedding.purge" and a.target_id == str(wid) for a in trail)


def test_purge_skips_recent_null_timestamp_and_live(client, db_session):
    recent = make_wedding(db_session, "wed-recent")
    _archive(db_session, recent, days_ago=5)
    legacy = make_wedding(db_session, "wed-legacy")
    _archive(db_session, legacy, days_ago=None)  # archived pre-migration: never purged
    live = make_wedding(db_session, "wed-live")

    r = client.post("/api/platform/purge-archived", headers=platform_auth())
    assert r.status_code == 200 and r.json()["count"] == 0
    for w in (recent, legacy, live):
        assert db_session.get(Wedding, w.id) is not None


def test_archive_sets_clock_and_reinstate_clears_it(client, db_session):
    w = make_wedding(db_session, "wed-undo")
    make_member(db_session, w, OWNER)

    assert client.delete("/api/w/wed-undo/admin", headers=user_auth(OWNER)).status_code == 200
    db_session.refresh(w)
    assert w.status == "archived" and w.archived_at is not None

    r = client.post(f"/api/platform/weddings/{w.id}/reinstate", headers=platform_auth())
    assert r.status_code == 200
    db_session.refresh(w)
    assert w.status == "draft" and w.archived_at is None


def test_cron_endpoint_is_404_without_secret(client):
    assert client.post("/api/internal/cron/purge-archived").status_code == 404
    assert client.get("/api/internal/cron/purge-archived").status_code == 404


def test_cron_endpoint_auth_and_purge(make_client, db_session):
    client = make_client(cron_secret="s3cret-cron")
    w = make_wedding(db_session, "wed-cron")
    _archive(db_session, w, days_ago=40)

    assert client.post("/api/internal/cron/purge-archived").status_code == 401
    assert (
        client.post(
            "/api/internal/cron/purge-archived",
            headers={"Authorization": "Bearer wrong"},
        ).status_code
        == 401
    )
    r = client.get(
        "/api/internal/cron/purge-archived",
        headers={"Authorization": "Bearer s3cret-cron"},
    )
    assert r.status_code == 200 and r.json()["count"] == 1
    assert db_session.get(Wedding, w.id) is None
