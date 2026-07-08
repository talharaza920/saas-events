"""Shared helpers for the platform-era tests (identity, lifecycle, members,
platform console, entitlements). The pre-platform test files keep their own
in-file fixtures; new tests use these + the fixtures in conftest.py.

Local principals (no Supabase needed):
  • bare dev token       → sub "dev", ALWAYS a platform admin (bootstrap)
  • "<token>:<email>"    → sub "dev:<email>", an ordinary user
"""
from __future__ import annotations

from app.models import Guest, InviteTier, MemberRole, MemberStatus, Wedding, WeddingMember

DEV_TOKEN = "dev-secret-token"


def platform_auth() -> dict:
    """The bootstrap platform admin (bare dev token)."""
    return {"Authorization": f"Bearer {DEV_TOKEN}"}


def user_auth(email: str) -> dict:
    """An ordinary signed-in user (no platform powers, no memberships unless
    granted via make_member)."""
    return {"Authorization": f"Bearer {DEV_TOKEN}:{email}"}


def user_sub(email: str) -> str:
    return f"dev:{email}"


def make_wedding(db, slug: str, *, status: str = "active", published: bool = True) -> Wedding:
    w = Wedding(
        slug=slug,
        couple_names=slug.replace("-", " ").title(),
        status=status,
        published=published,
        event_details={},
        content={},
    )
    db.add(w)
    db.commit()
    return w


def make_member(db, wedding: Wedding, email: str, role: str = "owner") -> WeddingMember:
    m = WeddingMember(
        wedding_id=wedding.id,
        user_id=user_sub(email),
        invited_email=email,
        role=MemberRole(role),
        status=MemberStatus.active,
    )
    db.add(m)
    db.commit()
    return m


def add_guest(db, wedding: Wedding, slug: str, name: str = "Guest", tier=InviteTier.solo) -> Guest:
    g = Guest(
        wedding_id=wedding.id,
        slug=slug,
        name=name,
        greeting_name=name,
        invite_tier=tier,
        invited=True,
    )
    db.add(g)
    db.commit()
    return g
