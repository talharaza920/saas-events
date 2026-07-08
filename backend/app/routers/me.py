"""Account-level endpoints — the signed-in user's home (no wedding in the path).

  GET  /api/me                → whoami + platform-admin flag
  GET  /api/me/weddings       → the dashboard list (my weddings + roles)
  POST /api/weddings          → create a wedding from the neutral template
  GET  /api/weddings/slug-check?slug=… → live availability for the wizard
  POST /api/invites/accept    → accept a co-admin invite token
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit_log import record
from app.auth import AuthedUser, get_current_user
from app.authz import ensure_profile, is_platform_admin
from app.config import Settings, get_settings
from app.db import get_db
from app.entitlements import DEFAULT_ENTITLEMENTS
from app.models import (
    Guest,
    MemberStatus,
    Wedding,
    WeddingMember,
    WeddingStatus,
)
from app.schemas import (
    InviteAccept,
    InviteAccepted,
    MeResponse,
    MyWedding,
    SlugCheck,
    WeddingCreate,
    WeddingCreated,
)
from app.slugs import slug_error, suggest_slug
from app.wedding_factory import create_wedding

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=MeResponse)
def me(
    user: AuthedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MeResponse:
    profile = ensure_profile(db, user)
    return MeResponse(
        user_id=user.sub,
        email=user.email,
        via=user.via,
        display_name=profile.display_name,
        is_platform_admin=is_platform_admin(db, settings, user),
    )


@router.get("/me/weddings", response_model=list[MyWedding])
def my_weddings(
    user: AuthedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MyWedding]:
    """Weddings this user belongs to (active memberships), for the post-login
    dashboard. Archived weddings stay listed (status chip shows it) so the owner
    understands where their wedding went during the undo window."""
    ensure_profile(db, user)
    rows = db.execute(
        select(WeddingMember, Wedding)
        .join(Wedding, Wedding.id == WeddingMember.wedding_id)
        .where(
            WeddingMember.user_id == user.sub,
            WeddingMember.status == MemberStatus.active,
        )
        .order_by(Wedding.created_at)
    ).all()
    out: list[MyWedding] = []
    for member, wedding in rows:
        guest_count = db.execute(
            select(func.count()).select_from(Guest).where(Guest.wedding_id == wedding.id)
        ).scalar_one()
        out.append(
            MyWedding(
                wedding_id=wedding.id,
                slug=wedding.slug,
                couple_names=wedding.couple_names,
                role=member.role.value,
                status=wedding.status,
                published=wedding.published,
                guest_count=guest_count,
                created_at=wedding.created_at,
            )
        )
    return out


def _slug_taken(db: Session, slug: str) -> bool:
    return (
        db.execute(select(Wedding.id).where(Wedding.slug == slug)).scalar_one_or_none()
        is not None
    )


@router.get("/weddings/slug-check", response_model=SlugCheck)
def slug_check(
    slug: str = Query(min_length=1, max_length=120),
    user: AuthedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SlugCheck:
    """Live slug validation for the creation wizard (format + reserved list +
    uniqueness). Authenticated so it can't be used to enumerate anonymously."""
    slug = slug.strip().lower()
    reason = slug_error(slug)
    if reason is None and _slug_taken(db, slug):
        reason = "That address is already taken"
    suggestion = None
    if reason is not None:
        base = suggest_slug(slug) or "our-wedding"
        candidate = base
        for i in range(2, 30):
            if slug_error(candidate) is None and not _slug_taken(db, candidate):
                suggestion = candidate
                break
            candidate = f"{base}-{i}"
    return SlugCheck(slug=slug, available=reason is None, reason=reason, suggestion=suggestion)


@router.post("/weddings", response_model=WeddingCreated, status_code=201)
def create_wedding_endpoint(
    payload: WeddingCreate,
    user: AuthedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeddingCreated:
    """Self-serve wedding creation (SAAS_PLAN 2.1): neutral template content +
    default questions/arc, creator gets the `owner` membership, status `draft`.
    Account-level cap (`max_weddings_per_account`) is enforced here."""
    ensure_profile(db, user)
    slug = payload.slug.strip().lower()
    reason = slug_error(slug)
    if reason is not None:
        raise HTTPException(status_code=422, detail=reason)
    if _slug_taken(db, slug):
        raise HTTPException(status_code=409, detail="That address is already taken")

    my_count = db.execute(
        select(func.count()).select_from(WeddingMember).where(
            WeddingMember.user_id == user.sub,
            WeddingMember.status == MemberStatus.active,
        )
    ).scalar_one()
    max_per_account = DEFAULT_ENTITLEMENTS["max_weddings_per_account"]
    if my_count >= max_per_account:
        raise HTTPException(
            status_code=403,
            detail="You've reached the number of weddings your account allows — contact us",
        )

    wedding = create_wedding(
        db,
        slug=slug,
        couple_names=payload.couple_names.strip(),
        creator=user,
        event_overrides={
            "venue": payload.venue,
            "date_iso": payload.date_iso,
            "date_display": payload.date_display,
        },
    )
    record(db, "wedding.create", user=user, wedding=wedding, detail={"slug": slug})
    db.commit()
    return WeddingCreated(
        wedding_id=wedding.id,
        slug=wedding.slug,
        couple_names=wedding.couple_names,
        status=wedding.status,
        admin_path=f"/{wedding.slug}/admin",
    )


@router.post("/invites/accept", response_model=InviteAccepted)
def accept_invite(
    payload: InviteAccept,
    user: AuthedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InviteAccepted:
    """Accept a co-admin invite (Phase 3). The token is single-use and expiring;
    the signed-in email must MATCH the invited email — a forwarded link is
    useless to anyone else."""
    ensure_profile(db, user)
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    member = db.execute(
        select(WeddingMember).where(
            WeddingMember.invite_token_hash == token_hash,
            WeddingMember.status == MemberStatus.invited,
        )
    ).scalar_one_or_none()
    invalid = HTTPException(status_code=404, detail="This invite link is invalid or has expired")
    if member is None:
        raise invalid
    if member.invite_expires_at is not None:
        expires = member.invite_expires_at
        now = datetime.now(timezone.utc)
        if expires.tzinfo is None:
            now = now.replace(tzinfo=None)
        if expires < now:
            raise invalid
    if (member.invited_email or "").lower() != user.email.lower():
        # Same shape as "not found" — don't confirm the invite exists to the
        # wrong account.
        raise invalid

    wedding = db.get(Wedding, member.wedding_id)
    if wedding is None or wedding.status == WeddingStatus.ARCHIVED:
        raise invalid

    member.user_id = user.sub
    member.status = MemberStatus.active
    member.invite_token_hash = None
    member.invite_expires_at = None
    record(
        db, "member.accept", user=user, wedding=wedding,
        target_type="member", target_id=member.id,
    )
    db.commit()
    return InviteAccepted(
        wedding_id=wedding.id,
        wedding_slug=wedding.slug,
        couple_names=wedding.couple_names,
        role=member.role.value,
    )
