"""Unit tests for the pure guest-import logic (no DB)."""
from app.guest_import import (
    build_guests,
    classify_row,
    infer_tier,
    make_guest_slug,
    normalize_key,
    slugify,
)
from app.models import InviteTier


def test_slugify_strips_plus_and_parens():
    assert slugify("Riley +1") == "riley"
    assert slugify("Kid 2 (Casey)") == "kid-2"
    assert slugify("Au Mei Lin") == "au-mei-lin"


def test_make_guest_slug_is_non_descript_and_unique():
    a = make_guest_slug("Jordan")
    b = make_guest_slug("Jordan")
    # A bare random token — the name is never leaked into the link.
    assert "jordan" not in a.lower()
    # 16 random bytes, URL-safe base64 (~22 chars of [A-Za-z0-9_-]) = 128 bits of
    # entropy, so the link is infeasible to enumerate.
    assert len(a) >= 22
    assert all(c.isalnum() or c in "-_" for c in a)
    assert a != b  # random


def test_classify_primary_adult_child():
    assert classify_row("Jordan", "Friends").kind == "primary"
    adult = classify_row("Riley +1", "Friends")
    assert adult.kind == "adult" and adult.base_key == normalize_key("Riley")
    kid = classify_row("Kid 2 (Casey)", "Kid")
    assert kid.kind == "child" and kid.base_key == normalize_key("Casey")
    # Relationship 'Kid' without parenthetical → unresolved parent
    assert classify_row("Lucas", "Kid").kind == "child"


def test_infer_tier():
    assert infer_tier(0, 0) is InviteTier.solo
    assert infer_tier(1, 0) is InviteTier.plus_one
    assert infer_tier(2, 0) is InviteTier.plus_family
    assert infer_tier(0, 1) is InviteTier.plus_family


def test_build_guests_collapses_companions_into_tiers():
    rows = [
        {"name": "Jordan", "side": "Alex", "relationship": "Friends"},
        {"name": "Riley", "side": "Alex", "relationship": "Friends"},
        {"name": "Riley +1", "side": "Alex", "relationship": "Friends"},
        {"name": "Riley +2", "side": "Alex", "relationship": "Friends"},
        {"name": "Casey", "side": "Sam", "relationship": "Cousin"},
        {"name": "Kid 2 (Casey)", "side": "Sam", "relationship": "Kid"},
        {"name": "Orphan Kid", "side": "Sam", "relationship": "Kid"},
    ]
    guests, unresolved = build_guests(rows)
    by_name = {g.name: g for g in guests}

    # Companion placeholder rows do NOT become their own guests.
    assert set(by_name) == {"Jordan", "Riley", "Casey"}
    assert by_name["Jordan"].invite_tier is InviteTier.solo
    # Riley had +1 and +2 → 2 adult companions → plus_family
    assert by_name["Riley"].adult_companions == 2
    assert by_name["Riley"].invite_tier is InviteTier.plus_family
    # Casey got a resolvable kid → plus_family
    assert by_name["Casey"].child_companions == 1
    assert by_name["Casey"].invite_tier is InviteTier.plus_family
    # A kid with no resolvable parent is surfaced for admin review, not invented.
    assert any(u["name"] == "Orphan Kid" for u in unresolved)
