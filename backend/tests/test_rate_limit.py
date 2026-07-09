"""Guest-API rate limiting (REVIEW_BACKLOG P0-4): per-IP fixed window, writes
stricter than reads, off in dev unless opted in, on by default in production.
The conftest autouse fixture resets the buckets between tests."""
from __future__ import annotations

from tests.helpers import add_guest, make_wedding

DECLINE = {"attending": False}


def _guest(db, slug="rate-limit-guest"):
    w = make_wedding(db, f"rl-{slug}")
    return add_guest(db, w, slug)


def test_off_by_default_outside_production(make_client, db_session):
    g = _guest(db_session, "dev-default")
    client = make_client()  # environment="development", rate_limit_enabled unset
    codes = {client.post(f"/api/i/{g.slug}/rsvp", json=DECLINE).status_code for _ in range(10)}
    assert codes == {200}


def test_write_limit_enforced_when_enabled(make_client, db_session):
    g = _guest(db_session, "writes")
    client = make_client(rate_limit_enabled=True, rate_limit_guest_writes_per_minute=3)
    codes = [client.post(f"/api/i/{g.slug}/rsvp", json=DECLINE).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_wish_writes_share_the_write_budget(make_client, db_session):
    g = _guest(db_session, "wishes")
    client = make_client(rate_limit_enabled=True, rate_limit_guest_writes_per_minute=2)
    wish = {"name": "A guest", "message": "Congratulations!"}
    codes = [client.post(f"/api/i/{g.slug}/wishes", json=wish).status_code for _ in range(3)]
    assert codes == [201, 201, 429]


def test_read_limit_enforced_when_enabled(make_client, db_session):
    g = _guest(db_session, "reads")
    client = make_client(rate_limit_enabled=True, rate_limit_guest_reads_per_minute=2)
    codes = [client.get(f"/api/i/{g.slug}").status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_enabled_automatically_in_production(make_client, db_session):
    g = _guest(db_session, "prod")
    client = make_client(environment="production", rate_limit_guest_writes_per_minute=1)
    first = client.post(f"/api/i/{g.slug}/rsvp", json=DECLINE).status_code
    second = client.post(f"/api/i/{g.slug}/rsvp", json=DECLINE).status_code
    assert (first, second) == (200, 429)


def test_429_carries_retry_after(make_client, db_session):
    g = _guest(db_session, "retry-after")
    client = make_client(rate_limit_enabled=True, rate_limit_guest_reads_per_minute=1)
    assert client.get(f"/api/i/{g.slug}").status_code == 200
    resp = client.get(f"/api/i/{g.slug}")
    assert resp.status_code == 429
    assert resp.headers.get("retry-after") == "60"
