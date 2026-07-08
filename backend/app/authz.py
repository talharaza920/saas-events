"""Authorization seams (SAAS_PLAN 1.3) — membership + platform-admin checks.

Every wedding-scoped admin endpoint resolves its tenant FROM THE PATH
(`/api/w/{wedding_slug}/admin/…`) through `require_wedding(...)`, which grants
access to platform admins or holders of an `active` membership row. The
guarantees the tests pin down:

  • Unauthenticated                        → 401 (from app/auth.py)
  • Authenticated, but not a member        → 404 — existence is never revealed
  • Member, but below the required role    → 403
  • Suspended wedding, mutating endpoint   → 403 (read stays available)
  • Archived wedding                       → 404 for members (platform admin still sees it)
  • Disabled account                       → 403 everywhere

`require_platform_admin` gates `/api/platform/*`: a `platform_admins` row, the
`ADMIN_EMAILS` bootstrap fallback, or the local bare dev-token principal.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import AuthedUser, get_current_user
from app.config import Settings, get_settings
from app.db import get_db
from app.models import (
    MemberRole,
    MemberStatus,
    PlatformAdmin,
    Profile,
    Wedding,
    WeddingMember,
    WeddingStatus,
)

# Role precedence for `role_at_least` checks. "platform" outranks owner — a
# platform admin passes every wedding-scoped gate (view-as / support).
ROLE_RANK = {"admin": 1, "owner": 2, "platform": 3}


@dataclass
class WeddingCtx:
    """What a wedding-scoped endpoint gets: the tenant, the caller, and the
    caller's effective role on this wedding."""

    wedding: Wedding
    user: AuthedUser
    role: str  # "admin" | "owner" | "platform"

    @property
    def is_platform(self) -> bool:
        return self.role == "platform"


def ensure_profile(db: Session, user: AuthedUser) -> Profile:
    """Upsert the caller's profile row (lazy — replaces a signup trigger, so it
    works the same on SQLite and Supabase). Refuses disabled accounts."""
    profile = db.get(Profile, user.sub)
    if profile is None:
        profile = Profile(user_id=user.sub, email=user.email)
        db.add(profile)
        db.commit()
    elif profile.email != user.email:
        profile.email = user.email  # keep in sync with the auth provider
        db.commit()
    if profile.disabled:
        raise HTTPException(status_code=403, detail="This account is disabled")
    return profile


def is_platform_admin(db: Session, settings: Settings, user: AuthedUser) -> bool:
    if user.sub == "dev":  # local bare dev token = the bootstrap platform admin
        return True
    if user.email in settings.admin_email_list:  # env bootstrap fallback
        return True
    return db.get(PlatformAdmin, user.sub) is not None


def require_platform_admin(
    user: AuthedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthedUser:
    """Dependency for /api/platform/*."""
    ensure_profile(db, user)
    if not is_platform_admin(db, settings, user):
        raise HTTPException(status_code=403, detail="Platform admin access required")
    return user


def active_membership(db: Session, wedding_id, user_sub: str) -> WeddingMember | None:
    return db.execute(
        select(WeddingMember).where(
            WeddingMember.wedding_id == wedding_id,
            WeddingMember.user_id == user_sub,
            WeddingMember.status == MemberStatus.active,
        )
    ).scalar_one_or_none()


def require_wedding(role_at_least: str = "admin", *, edit: bool = False):
    """Dependency factory: resolve `{wedding_slug}` from the path and authorize.

    `role_at_least` is "admin" (any active member) or "owner" (owner-only
    endpoints: member management, delete/transfer, publish by default).
    `edit=True` marks a mutating endpoint — refused with 403 on a suspended
    wedding (the dashboard goes read-only; platform admins are exempt so they
    can operate on suspended tenants).
    """

    def dependency(
        wedding_slug: str = Path(),
        user: AuthedUser = Depends(get_current_user),
        db: Session = Depends(get_db),
        settings: Settings = Depends(get_settings),
    ) -> WeddingCtx:
        ensure_profile(db, user)
        wedding = db.execute(
            select(Wedding).where(Wedding.slug == wedding_slug)
        ).scalar_one_or_none()

        not_found = HTTPException(status_code=404, detail="Wedding not found")
        if wedding is None:
            raise not_found

        member = active_membership(db, wedding.id, user.sub)
        platform = is_platform_admin(db, settings, user)
        if member is None and not platform:
            # Non-members get the same 404 as a nonexistent slug — never confirm
            # a wedding exists to someone with no membership.
            raise not_found

        if member is not None:
            role = member.role.value if isinstance(member.role, MemberRole) else str(member.role)
            if platform:
                role = "platform"
        else:
            role = "platform"

        # Archived (soft-deleted) weddings are gone for members; platform admins
        # keep access for the undo window.
        if wedding.status == WeddingStatus.ARCHIVED and role != "platform":
            raise not_found

        if ROLE_RANK[role] < ROLE_RANK[role_at_least]:
            raise HTTPException(status_code=403, detail="Owner access required")

        if edit and wedding.status == WeddingStatus.SUSPENDED and role != "platform":
            raise HTTPException(
                status_code=403, detail="This wedding is suspended — the dashboard is read-only"
            )

        return WeddingCtx(wedding=wedding, user=user, role=role)

    return dependency
