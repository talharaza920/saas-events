"""Per-wedding phone region (review backlog #6).

A national-format phone number (no leading +) is interpreted in the wedding's
`settings["phone_region"]`, falling back to the platform default (SG). The
setting is owner-editable via PATCH /settings and validated to a supported
ISO 3166-1 alpha-2 code. International (+...) input is region-independent.
"""
from __future__ import annotations

from app.validation import DEFAULT_REGION, wedding_phone_region
from tests.helpers import add_guest, make_member, make_wedding, user_auth

ALICE_EMAIL = "alice@example.com"

US_NATIONAL = "212 555 0123"          # valid US number, national format
US_E164 = "+12125550123"
SG_NATIONAL = "8123 4567"             # valid SG mobile, national format
SG_E164 = "+6581234567"


def _wedding_with_owner(db, slug="wed-region", region: str | None = None):
    w = make_wedding(db, slug)
    if region is not None:
        w.settings = {"phone_region": region}
        db.commit()
    make_member(db, w, ALICE_EMAIL, role="owner")
    return w


def test_wedding_phone_region_helper_defaults_and_validates(db_session):
    w = make_wedding(db_session, "wed-helper")
    assert wedding_phone_region(w) == DEFAULT_REGION          # unset → default
    w.settings = {"phone_region": "us"}
    assert wedding_phone_region(w) == "US"                    # case-normalized
    w.settings = {"phone_region": "ZZ"}
    assert wedding_phone_region(w) == DEFAULT_REGION          # junk → default


def test_settings_accepts_and_normalizes_region(client, db_session):
    _wedding_with_owner(db_session)
    r = client.patch(
        "/api/w/wed-region/admin/settings", headers=user_auth(ALICE_EMAIL),
        json={"phone_region": "us"},
    )
    assert r.status_code == 200
    assert r.json()["phone_region"] == "US"


def test_settings_rejects_unknown_region(client, db_session):
    _wedding_with_owner(db_session)
    r = client.patch(
        "/api/w/wed-region/admin/settings", headers=user_auth(ALICE_EMAIL),
        json={"phone_region": "ZZ"},
    )
    assert r.status_code == 422


def test_guest_rsvp_phone_uses_wedding_region(client, db_session):
    w = _wedding_with_owner(db_session, region="US")
    guest = add_guest(db_session, w, "guest-us")
    r = client.post(
        f"/api/i/{guest.slug}/rsvp",
        json={"attending": True, "phone": US_NATIONAL, "companions": [], "answers": []},
    )
    assert r.status_code == 200
    db_session.refresh(guest)
    assert guest.phone == US_E164


def test_guest_rsvp_phone_defaults_to_sg_when_unset(client, db_session):
    w = _wedding_with_owner(db_session, slug="wed-sg")
    guest = add_guest(db_session, w, "guest-sg")
    r = client.post(
        f"/api/i/{guest.slug}/rsvp",
        json={"attending": True, "phone": SG_NATIONAL, "companions": [], "answers": []},
    )
    assert r.status_code == 200
    db_session.refresh(guest)
    assert guest.phone == SG_E164


def test_admin_guest_create_uses_wedding_region(client, db_session):
    _wedding_with_owner(db_session, region="US")
    r = client.post(
        "/api/w/wed-region/admin/guests", headers=user_auth(ALICE_EMAIL),
        json={"greeting_name": "Pat", "invite_tier": "solo", "phone": US_NATIONAL},
    )
    assert r.status_code == 201
    assert r.json()["phone"] == US_E164


def test_international_input_ignores_region(client, db_session):
    # A +... number parses the same regardless of the wedding's region setting.
    w = _wedding_with_owner(db_session, slug="wed-intl", region="US")
    guest = add_guest(db_session, w, "guest-intl")
    r = client.post(
        f"/api/i/{guest.slug}/rsvp",
        json={"attending": True, "phone": SG_E164, "companions": [], "answers": []},
    )
    assert r.status_code == 200
    db_session.refresh(guest)
    assert guest.phone == SG_E164
