"""Theme presets (AI_WIZARD_PLAN 8.5e).

What these pin down, in one line each: the catalogue is data a platform admin
curates and a couple only reads; a broken blob degrades instead of bricking the
Theme tab; and applying a preset COPIES it — so the couple owns those tokens
afterwards and a console edit can never reach back into their wedding.
"""
from __future__ import annotations

import copy

import pytest

from app.models import PlatformSetting, Wedding
from app.theme_presets import (
    DEFAULT_THEME_PRESETS,
    FONT_BODY,
    PresetError,
    THEME_PRESETS_KEY,
    get_theme_presets,
    validate_presets,
)
from tests.helpers import make_member, make_wedding, platform_auth, user_auth


@pytest.fixture
def wedding(db_session) -> Wedding:
    w = make_wedding(db_session, "alex-and-sam")
    make_member(db_session, w, "owner@example.com", role="owner")
    return w


def _preset(**over) -> dict:
    base = {
        "id": "test-look",
        "name": "Test look",
        "description": "",
        "swatches": [],
        "enabled": True,
        "tokens": {"colors": {"primary": "#112233"}},
    }
    base.update(over)
    return base


def _put(client, presets: list[dict]):
    return client.put(
        "/api/platform/theme-presets", json={"presets": presets}, headers=platform_auth()
    )


# --- The catalogue that ships ------------------------------------------------
def test_ten_presets_ship_in_code_and_all_validate():
    presets = validate_presets(DEFAULT_THEME_PRESETS)
    assert len(presets) == 10
    assert presets[0]["id"] == "ever-after"  # the template is a starting point too
    assert len({p["id"] for p in presets}) == 10


def test_a_preset_only_names_fonts_the_app_actually_loads():
    """A font is not really data — adding a face means registering it with
    next/font. A preset naming an unloaded family would silently render the
    fallback stack, so the console can't set one."""
    with pytest.raises(PresetError, match="fonts the app loads"):
        validate_presets([_preset(tokens={"typography": {"body": "Comic Sans MS"}})])


# --- Never brick the Theme tab ----------------------------------------------
def test_defaults_when_nothing_is_stored(db_session):
    assert [p["id"] for p in get_theme_presets(db_session)] == [
        p["id"] for p in DEFAULT_THEME_PRESETS
    ]


def test_a_structurally_broken_blob_falls_back_to_the_code_defaults(db_session):
    db_session.add(PlatformSetting(key=THEME_PRESETS_KEY, value={"presets": "not-a-list"}))
    db_session.commit()
    assert len(get_theme_presets(db_session)) == len(DEFAULT_THEME_PRESETS)


def test_one_rotten_preset_is_skipped_and_the_rest_still_serve(db_session):
    db_session.add(
        PlatformSetting(
            key=THEME_PRESETS_KEY,
            value={"presets": [_preset(), {"id": "no-tokens", "name": "Broken"}, _preset(id="bb")]},
        )
    )
    db_session.commit()
    assert [p["id"] for p in get_theme_presets(db_session)] == ["test-look", "bb"]


def test_an_emptied_catalogue_is_a_choice_not_a_fault(db_session, client):
    """An admin who deletes every preset gets none offered — that is a stored
    empty list, not a broken blob, so it must NOT resurrect the defaults."""
    assert _put(client, []).status_code == 200
    assert get_theme_presets(db_session) == []


# --- The console editor ------------------------------------------------------
def test_the_console_sees_disabled_presets_and_the_couple_does_not(client, wedding):
    assert _put(client, [_preset(enabled=False), _preset(id="live", name="Live")]).status_code == 200

    console = client.get("/api/platform/theme-presets", headers=platform_auth()).json()
    assert [p["id"] for p in console["presets"]] == ["test-look", "live"]

    tab = client.get(
        "/api/w/alex-and-sam/admin/theme/presets", headers=user_auth("owner@example.com")
    ).json()
    assert [p["id"] for p in tab] == ["live"]


def test_one_save_is_reorder_disable_and_delete(client):
    _put(client, [_preset(id="aa", name="A"), _preset(id="bb", name="B"), _preset(id="cc", name="C")])
    assert _put(client, [_preset(id="cc", name="C"), _preset(id="aa", name="A", enabled=False)]).status_code == 200

    presets = client.get("/api/platform/theme-presets", headers=platform_auth()).json()["presets"]
    assert [(p["id"], p["enabled"]) for p in presets] == [("cc", True), ("aa", False)]


def test_bad_presets_are_refused_with_a_reason(client):
    cases = {
        "hex colour": _preset(tokens={"colors": {"primary": "rebeccapurple"}}),
        "unknown colour": _preset(tokens={"colors": {"blurple": "#112233"}}),
        "can't set": _preset(tokens={"shadows": {"soft": "0 0 0 red"}}),
        "slug": _preset(id="Not A Slug"),
        "between": _preset(tokens={"radius": 500}),
        "non-empty tokens": _preset(tokens={}),
    }
    for expected, preset in cases.items():
        res = _put(client, [preset])
        assert res.status_code == 422, expected
        assert expected in res.json()["detail"]


def test_two_presets_cannot_share_an_id(client):
    res = _put(client, [_preset(), _preset(name="Same id")])
    assert res.status_code == 422
    assert "share an id" in res.json()["detail"]


def test_every_catalogue_save_is_audited(client, db_session):
    from app.models import AuditLog

    _put(client, [_preset(), _preset(id="off", enabled=False)])
    row = db_session.query(AuditLog).filter(AuditLog.action == "platform.theme_presets").one()
    assert row.detail["enabled"] == ["test-look"]
    assert row.detail["disabled"] == ["off"]


# --- The couple's side -------------------------------------------------------
def test_swatches_are_derived_when_the_console_did_not_choose_them(client, wedding):
    presets = client.get(
        "/api/w/alex-and-sam/admin/theme/presets", headers=user_auth("owner@example.com")
    ).json()
    ever_after = next(p for p in presets if p["id"] == "ever-after")
    assert ever_after["swatches"][:2] == ["#D98C6A", "#8E9BB3"]  # primary, secondary


def test_applying_a_preset_replaces_the_theme_rather_than_merging_it(client, db_session, wedding):
    """Half of the old look surviving under the new one is the bug this rules
    out: pick Midnight, get Midnight."""
    wedding.theme_tokens = {"colors": {"primary": "#000000", "dream1": "#FF00FF"}}
    db_session.commit()

    res = client.post(
        "/api/w/alex-and-sam/admin/theme/preset",
        json={"preset_id": "midnight-gold"},
        headers=user_auth("owner@example.com"),
    )
    assert res.status_code == 200
    tokens = res.json()["theme_tokens"]
    assert tokens["colors"]["primary"] == "#D9B26A"
    assert tokens["colors"]["dream1"] == "#2A3358"  # not the leftover magenta
    assert tokens["typography"]["logo"] == tokens["typography"]["display"]


def test_a_preset_is_a_starting_point_the_couple_can_edit_on_top_of(client, wedding):
    client.post(
        "/api/w/alex-and-sam/admin/theme/preset",
        json={"preset_id": "forest-emerald"},
        headers=user_auth("owner@example.com"),
    )
    res = client.patch(
        "/api/w/alex-and-sam/admin/content",
        json={"theme_tokens": {"colors": {"primary": "#123456"}}},
        headers=user_auth("owner@example.com"),
    )
    tokens = res.json()["theme_tokens"]
    assert tokens["colors"]["primary"] == "#123456"  # the hand edit wins
    assert tokens["colors"]["paper"] == "#F2F1E7"  # the rest of the preset stays


def test_editing_the_preset_afterwards_never_touches_the_wedding(client, db_session, wedding):
    """Apply COPIES. This is why: a couple who chose a look in June must not find
    a different one on their invitation in July because the platform recoloured
    the catalogue."""
    _put(client, [_preset(id="chosen", name="Chosen", tokens={"colors": {"primary": "#AAAAAA"}})])
    client.post(
        "/api/w/alex-and-sam/admin/theme/preset",
        json={"preset_id": "chosen"},
        headers=user_auth("owner@example.com"),
    )
    _put(client, [_preset(id="chosen", name="Chosen", tokens={"colors": {"primary": "#BBBBBB"}})])

    db_session.refresh(wedding)
    assert wedding.theme_tokens["colors"]["primary"] == "#AAAAAA"


def test_deleting_the_preset_afterwards_leaves_the_wedding_dressed(client, db_session, wedding):
    _put(client, [_preset(id="chosen", name="Chosen", tokens={"colors": {"primary": "#AAAAAA"}})])
    client.post(
        "/api/w/alex-and-sam/admin/theme/preset",
        json={"preset_id": "chosen"},
        headers=user_auth("owner@example.com"),
    )
    _put(client, [])

    db_session.refresh(wedding)
    assert wedding.theme_tokens["colors"]["primary"] == "#AAAAAA"


def test_a_disabled_or_unknown_preset_cannot_be_applied(client, wedding):
    _put(client, [_preset(id="retired", name="Retired", enabled=False)])
    for preset_id in ("retired", "no-such-preset"):
        res = client.post(
            "/api/w/alex-and-sam/admin/theme/preset",
            json={"preset_id": preset_id},
            headers=user_auth("owner@example.com"),
        )
        assert res.status_code == 404


def test_applying_a_preset_is_audited(client, db_session, wedding):
    from app.models import AuditLog

    client.post(
        "/api/w/alex-and-sam/admin/theme/preset",
        json={"preset_id": "coastal-blue"},
        headers=user_auth("owner@example.com"),
    )
    row = db_session.query(AuditLog).filter(AuditLog.action == "wedding.theme.preset").one()
    assert row.detail["preset_id"] == "coastal-blue"
    assert row.wedding_id == wedding.id


# --- Authz -------------------------------------------------------------------
def test_the_catalogue_is_platform_admins_only(client, db_session):
    make_wedding(db_session, "other")
    assert client.get("/api/platform/theme-presets").status_code == 401
    assert (
        client.get("/api/platform/theme-presets", headers=user_auth("nobody@example.com")).status_code
        == 403
    )
    assert _put_as_user(client, "nobody@example.com").status_code == 403


def _put_as_user(client, email: str):
    return client.put(
        "/api/platform/theme-presets", json={"presets": []}, headers=user_auth(email)
    )


def test_a_non_member_cannot_see_or_apply_this_weddings_themes(client, wedding):
    stranger = user_auth("stranger@example.com")
    assert client.get("/api/w/alex-and-sam/admin/theme/presets", headers=stranger).status_code == 404
    assert (
        client.post(
            "/api/w/alex-and-sam/admin/theme/preset",
            json={"preset_id": "ever-after"},
            headers=stranger,
        ).status_code
        == 404
    )
    assert client.get("/api/w/alex-and-sam/admin/theme/presets").status_code == 401


def test_a_suspended_wedding_can_read_the_catalogue_but_not_apply(client, db_session, wedding):
    wedding.status = "suspended"
    db_session.commit()
    auth = user_auth("owner@example.com")
    assert client.get("/api/w/alex-and-sam/admin/theme/presets", headers=auth).status_code == 200
    res = client.post(
        "/api/w/alex-and-sam/admin/theme/preset", json={"preset_id": "ever-after"}, headers=auth
    )
    assert res.status_code == 403  # read-only mode


def test_the_shipped_catalogue_is_not_mutated_by_a_read(db_session):
    before = copy.deepcopy(DEFAULT_THEME_PRESETS)
    presets = get_theme_presets(db_session)
    presets[0]["name"] = "Tampered"
    presets[0]["tokens"]["colors"]["primary"] = "#000000"
    assert DEFAULT_THEME_PRESETS == before


def test_a_preset_can_carry_the_numeric_knobs(client, wedding):
    _put(client, [_preset(id="round", name="Round", tokens={"radius": 30, "radiusLg": 40})])
    res = client.post(
        "/api/w/alex-and-sam/admin/theme/preset",
        json={"preset_id": "round"},
        headers=user_auth("owner@example.com"),
    )
    assert res.json()["theme_tokens"] == {"radius": 30, "radiusLg": 40}


def test_the_body_font_stack_is_the_one_the_frontend_uses():
    """If defaultThemeConfig.ts ever changes a stack, this is the tripwire — the
    Python copy is the only place the backend can know what the app loads."""
    assert FONT_BODY.startswith("var(--font-body)")
