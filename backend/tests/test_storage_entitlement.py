"""max_storage_mb enforcement + usage accounting (REVIEW_BACKLOG P1-7).

Uploads are gated by the plan's storage cap against the per-wedding
`storage_bytes_used` counter (incremented per upload, exact stored size);
the reconcile cron rewrites the counter from what's actually on disk / in the
bucket so drift can't silently grow.
"""
from __future__ import annotations

import pytest

import app.storage as storage
from app.models import Plan, Wedding, WeddingPlan
from tests.helpers import make_member, make_wedding, user_auth

OWNER = "owner@example.com"
PNG = ("pic.png", b"not-really-a-png-but-fine", "image/png")  # stored verbatim


@pytest.fixture(autouse=True)
def _tmp_uploads(tmp_path, monkeypatch):
    """Keep test uploads out of the repo's uploads/ dir."""
    monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path)


def _wedding(db, slug="wed-storage"):
    w = make_wedding(db, slug)
    make_member(db, w, OWNER)
    return w


def test_upload_increments_byte_counter(client, db_session):
    w = _wedding(db_session)
    r = client.post(
        "/api/w/wed-storage/admin/upload", headers=user_auth(OWNER), files={"file": PNG}
    )
    assert r.status_code == 200
    db_session.refresh(w)
    assert w.storage_bytes_used == len(PNG[1])
    # /me surfaces the counter for the dashboard's usage display.
    me = client.get("/api/w/wed-storage/admin/me", headers=user_auth(OWNER)).json()
    assert me["storage_bytes_used"] == len(PNG[1])

    client.post("/api/w/wed-storage/admin/upload", headers=user_auth(OWNER), files={"file": PNG})
    db_session.refresh(w)
    assert w.storage_bytes_used == 2 * len(PNG[1])


def test_upload_refused_past_the_cap(client, db_session):
    w = _wedding(db_session)
    w.storage_bytes_used = 500 * 1024 * 1024  # exactly at the default 500 MB cap
    db_session.commit()
    r = client.post(
        "/api/w/wed-storage/admin/upload", headers=user_auth(OWNER), files={"file": PNG}
    )
    assert r.status_code == 403
    assert "Storage limit" in r.json()["detail"]
    db_session.refresh(w)
    assert w.storage_bytes_used == 500 * 1024 * 1024  # nothing was stored or counted


def test_storage_zero_turns_uploads_off(client, db_session):
    w = _wedding(db_session)
    plan = Plan(name="NoStorage", entitlements={})
    db_session.add(plan)
    db_session.flush()
    db_session.add(
        WeddingPlan(wedding_id=w.id, plan_id=plan.id, overrides={"max_storage_mb": 0})
    )
    db_session.commit()
    r = client.post(
        "/api/w/wed-storage/admin/upload", headers=user_auth(OWNER), files={"file": PNG}
    )
    assert r.status_code == 403


def test_reconcile_cron_corrects_drift(make_client, db_session, tmp_path):
    client = make_client(cron_secret="s3cret-cron")
    w = _wedding(db_session)
    # Truth on disk: two files, 10 bytes. Counter: wrong on purpose.
    folder = tmp_path / "wed-storage"
    folder.mkdir()
    (folder / "a.png").write_bytes(b"1234")
    (folder / "b.png").write_bytes(b"123456")
    w.storage_bytes_used = 999_999
    db_session.commit()

    assert client.post("/api/internal/cron/reconcile-storage").status_code == 401
    r = client.post(
        "/api/internal/cron/reconcile-storage",
        headers={"Authorization": "Bearer s3cret-cron"},
    )
    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert r.json()["corrected"][0]["to_bytes"] == 10
    db_session.refresh(w)
    assert w.storage_bytes_used == 10


def test_reconcile_zeroes_missing_namespace(make_client, db_session):
    client = make_client(cron_secret="s3cret-cron")
    w = _wedding(db_session, slug="wed-empty")
    w.storage_bytes_used = 123
    db_session.commit()
    r = client.get(
        "/api/internal/cron/reconcile-storage",
        headers={"Authorization": "Bearer s3cret-cron"},
    )
    assert r.status_code == 200
    db_session.refresh(w)
    assert w.storage_bytes_used == 0  # no uploads dir → truly zero, not "unknown"
