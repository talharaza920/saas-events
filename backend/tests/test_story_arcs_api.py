"""Story-arc admin CRUD + content editing + image upload + invite exposure.

Runs on in-memory SQLite with the dev-token auth path (same harness style as
test_admin_api.py). Verifies tenant scoping, that the invite surfaces visible
arcs, and that the upload endpoint stores a file via the local backend.
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
def client(db_session, tmp_path, monkeypatch):
    # Point local uploads at a temp dir so the upload test doesn't touch the repo.
    import app.storage as storage

    monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path)
    s = _settings(media_base_url="http://testserver")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_settings] = lambda: s
    yield TestClient(app)
    app.dependency_overrides.clear()


def auth() -> dict:
    return {"Authorization": f"Bearer {DEV_TOKEN}"}


@pytest.fixture
def wedding(db_session):
    w = Wedding(
        slug="alex-and-sam",
        couple_names="Alex & Sam",
        status="active",
        owner_id="dev",  # the dev-token principal's sub; claims this wedding
        event_details={"venue": "The Garden Hall"},
        content={"cover": {"greeting": "Dear {name},"}},
        theme_tokens=None,
    )
    db_session.add(w)
    db_session.commit()
    return w


def _arc(db, wedding, *, title="Chapter Two", visible=True, sort_order=0, content=None):
    a = StoryArc(
        wedding_id=wedding.id,
        title=title,
        visible=visible,
        sort_order=sort_order,
        content=content or {"heading": "Our story", "beats": []},
    )
    db.add(a)
    db.commit()
    return a


# --- Story-arc CRUD --------------------------------------------------------
def test_arc_crud(client, wedding):
    created = client.post(
        "/api/admin/story-arcs",
        headers=auth(),
        json={"title": "Draft", "content": {"heading": "Hi", "beats": []}},
    )
    assert created.status_code == 201
    arc_id = created.json()["id"]
    assert created.json()["visible"] is True

    listed = client.get("/api/admin/story-arcs", headers=auth()).json()
    assert [a["title"] for a in listed] == ["Draft"]

    patched = client.patch(
        f"/api/admin/story-arcs/{arc_id}",
        headers=auth(),
        json={"visible": False, "content": {"heading": "Edited", "beats": [{"text": "x"}]}},
    )
    assert patched.status_code == 200
    assert patched.json()["visible"] is False
    assert patched.json()["content"]["heading"] == "Edited"

    assert client.delete(f"/api/admin/story-arcs/{arc_id}", headers=auth()).status_code == 204
    assert client.get("/api/admin/story-arcs", headers=auth()).json() == []


def test_arc_tenant_scoped(client, db_session, wedding):
    other = Wedding(slug="other", couple_names="O", status="active", owner_id="someone",
                    event_details={}, content={})
    db_session.add(other)
    db_session.commit()
    foreign = _arc(db_session, other, title="Foreign")
    # The dev owner (claimed onto alex-and-sam) can't touch the other wedding's arc.
    assert client.patch(
        f"/api/admin/story-arcs/{foreign.id}", headers=auth(), json={"title": "Hijack"}
    ).status_code == 404
    assert client.delete(f"/api/admin/story-arcs/{foreign.id}", headers=auth()).status_code == 404
    assert client.get("/api/admin/story-arcs", headers=auth()).json() == []


# --- Content editing -------------------------------------------------------
def test_content_partial_merge(client, wedding):
    r = client.patch(
        "/api/admin/content",
        headers=auth(),
        json={"content": {"cover": {"invite_line": "join us!"}}, "couple_names": "T & S"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["couple_names"] == "T & S"
    # Deep-merge keeps the untouched sibling key.
    assert body["content"]["cover"]["greeting"] == "Dear {name},"
    assert body["content"]["cover"]["invite_line"] == "join us!"


def test_content_theme_tokens_merge(client, wedding):
    r = client.patch(
        "/api/admin/content",
        headers=auth(),
        json={"theme_tokens": {"colors": {"primary": "#123456"}}},
    )
    assert r.status_code == 200
    assert r.json()["theme_tokens"]["colors"]["primary"] == "#123456"


# --- Upload ----------------------------------------------------------------
def test_upload_local_returns_url(client, wedding):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100  # minimal non-empty payload
    r = client.post(
        "/api/admin/upload",
        headers=auth(),
        files={"file": ("mascot.png", png, "image/png")},
    )
    assert r.status_code == 200
    url = r.json()["url"]
    assert url.startswith("http://testserver/media/alex-and-sam/")
    assert url.endswith(".png")


def test_upload_compresses_large_image(client, wedding, tmp_path):
    # A 3000x3000 photo-ish PNG, well over MAX_DIM. It should be accepted (under
    # the 15 MB cap) and stored downscaled (<=1600px) and smaller.
    from io import BytesIO

    from PIL import Image

    im = Image.new("RGB", (3000, 3000))
    for x in range(0, 3000, 5):  # some variation so it isn't trivially compressible
        for y in range(0, 3000, 200):
            im.putpixel((x, y), (x % 256, y % 256, (x + y) % 256))
    buf = BytesIO()
    im.save(buf, format="PNG")
    original = buf.getvalue()

    r = client.post(
        "/api/admin/upload",
        headers=auth(),
        files={"file": ("big.png", original, "image/png")},
    )
    assert r.status_code == 200
    url = r.json()["url"]
    stored = tmp_path / "alex-and-sam" / url.rsplit("/", 1)[1]
    assert stored.exists()
    with Image.open(stored) as out:
        assert max(out.size) <= 1600  # downscaled
    assert stored.stat().st_size < len(original)  # and shrunk


def test_upload_rejects_non_image(client, wedding):
    r = client.post(
        "/api/admin/upload",
        headers=auth(),
        files={"file": ("evil.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 422


def test_upload_requires_auth(client, wedding):
    r = client.post(
        "/api/admin/upload", files={"file": ("x.png", b"123", "image/png")}
    )
    assert r.status_code == 401


# --- Invite exposes visible arcs (no tier leak) ----------------------------
def test_invite_returns_visible_arcs_only(client, db_session, wedding):
    _arc(db_session, wedding, title="Shown", visible=True, sort_order=0,
         content={"heading": "Visible arc", "beats": []})
    _arc(db_session, wedding, title="Hidden", visible=False, sort_order=1,
         content={"heading": "Hidden arc", "beats": []})
    g = Guest(wedding_id=wedding.id, slug="solo-x", name="Solo X", greeting_name="Solo",
              invite_tier=InviteTier.solo, invited=True)
    db_session.add(g)
    db_session.commit()

    r = client.get("/api/i/solo-x")
    assert r.status_code == 200
    body = r.json()
    arcs = body["story_arcs"]
    assert len(arcs) == 1
    assert arcs[0]["content"]["heading"] == "Visible arc"
    # Tier never crosses the wire (arc payload is content + id only).
    assert "tier" not in r.text
    assert "title" not in arcs[0]
