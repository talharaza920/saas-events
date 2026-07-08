"""Platform (super admin) console API — `/api/platform/*`, gated by
`require_platform_admin` (SAAS_PLAN Phase 4; approve/deny/suspend arrive with
Phase 2, plans & entitlements with Phase 5).

  GET  /weddings                     → all weddings + status/owner/counts/plan
  POST /weddings/{id}/approve|deny|suspend|reinstate → lifecycle actions
  GET  /approvals                    → pending queue with the auto-rule trace
  GET/PUT /settings/approval         → the auto-approval rules editor
  GET  /users                        → all accounts; POST /users/{id}/disable
  GET  /admins, POST /admins/{id}, DELETE /admins/{id} → platform admins
  GET  /stats                        → ops widgets
  GET  /audit                        → recent audit tail
  GET/POST/PATCH /plans              → entitlement tiers
  PUT  /weddings/{id}/plan           → assign a plan / per-wedding overrides
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.approval import (
    evaluate_auto_approval,
    get_approval_rules,
    set_approval_rules,
)
from app.audit_log import record
from app.auth import AuthedUser
from app.authz import require_platform_admin
from app.config import Settings, get_settings
from app.db import get_db
from app.emailer import send_email
from app.entitlements import effective_entitlements
from app.models import (
    AuditLog,
    Guest,
    MemberRole,
    MemberStatus,
    Plan,
    PlatformAdmin,
    Profile,
    Rsvp,
    Wedding,
    WeddingMember,
    WeddingPlan,
    WeddingStatus,
)
from app.schemas import (
    ApprovalDecision,
    ApprovalItem,
    AuditEntry,
    PlanAdmin,
    PlanAssign,
    PlanCreate,
    PlanUpdate,
    PlatformSettingsPayload,
    PlatformStats,
    PlatformUser,
    PlatformWedding,
    RuleTraceEntry,
    UserDisableUpdate,
    WeddingPlanAdmin,
)

router = APIRouter(
    prefix="/api/platform",
    tags=["platform"],
    dependencies=[Depends(require_platform_admin)],
)


# --- Weddings view -----------------------------------------------------------
def _owner_email(db: Session, wedding: Wedding) -> str | None:
    row = db.execute(
        select(WeddingMember).where(
            WeddingMember.wedding_id == wedding.id,
            WeddingMember.role == MemberRole.owner,
            WeddingMember.status == MemberStatus.active,
        ).order_by(WeddingMember.created_at)
    ).scalars().first()
    if row is None:
        return None
    if row.user_id:
        profile = db.get(Profile, row.user_id)
        if profile is not None:
            return profile.email
    return row.invited_email


def _platform_wedding(db: Session, wedding: Wedding) -> PlatformWedding:
    member_count = db.execute(
        select(func.count()).select_from(WeddingMember).where(
            WeddingMember.wedding_id == wedding.id,
            WeddingMember.status == MemberStatus.active,
        )
    ).scalar_one()
    guest_count = db.execute(
        select(func.count()).select_from(Guest).where(Guest.wedding_id == wedding.id)
    ).scalar_one()
    wp = db.get(WeddingPlan, wedding.id)
    plan_name = wp.plan.name if wp is not None and wp.plan is not None else None
    return PlatformWedding(
        id=wedding.id,
        slug=wedding.slug,
        couple_names=wedding.couple_names,
        status=wedding.status,
        published=wedding.published,
        owner_email=_owner_email(db, wedding),
        member_count=member_count,
        guest_count=guest_count,
        plan_name=plan_name,
        created_at=wedding.created_at,
    )


@router.get("/weddings", response_model=list[PlatformWedding])
def list_weddings(
    status: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[PlatformWedding]:
    stmt = select(Wedding).order_by(Wedding.created_at.desc())
    if status:
        stmt = stmt.where(Wedding.status == status)
    return [_platform_wedding(db, w) for w in db.execute(stmt).scalars()]


def _get_wedding(db: Session, wedding_id: UUID) -> Wedding:
    wedding = db.get(Wedding, wedding_id)
    if wedding is None:
        raise HTTPException(status_code=404, detail="Wedding not found")
    return wedding


def _notify_owner(db: Session, settings: Settings, wedding: Wedding, subject: str, body: str) -> None:
    email = _owner_email(db, wedding)
    if email:
        send_email(settings, email, subject, body)


@router.post("/weddings/{wedding_id}/approve", response_model=PlatformWedding)
def approve_wedding(
    wedding_id: UUID,
    payload: ApprovalDecision | None = None,
    user: AuthedUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PlatformWedding:
    wedding = _get_wedding(db, wedding_id)
    if wedding.status not in (WeddingStatus.PENDING_APPROVAL, WeddingStatus.DRAFT):
        raise HTTPException(status_code=409, detail="Only a pending wedding can be approved")
    wedding.status = WeddingStatus.ACTIVE
    record(db, "wedding.approve", user=user, wedding=wedding,
           detail={"reason": payload.reason if payload else None})
    db.commit()
    _notify_owner(db, settings, wedding, f"{wedding.couple_names}: approved!",
                  "Your wedding was approved — you can publish it from the dashboard.")
    return _platform_wedding(db, wedding)


@router.post("/weddings/{wedding_id}/deny", response_model=PlatformWedding)
def deny_wedding(
    wedding_id: UUID,
    payload: ApprovalDecision,
    user: AuthedUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PlatformWedding:
    """Deny with a reason — back to `draft` so the owner can fix and resubmit."""
    wedding = _get_wedding(db, wedding_id)
    if wedding.status != WeddingStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=409, detail="Only a pending wedding can be denied")
    wedding.status = WeddingStatus.DRAFT
    record(db, "wedding.deny", user=user, wedding=wedding, detail={"reason": payload.reason})
    db.commit()
    _notify_owner(db, settings, wedding, f"{wedding.couple_names}: changes needed",
                  payload.reason or "Your submission needs changes before approval.")
    return _platform_wedding(db, wedding)


@router.post("/weddings/{wedding_id}/suspend", response_model=PlatformWedding)
def suspend_wedding(
    wedding_id: UUID,
    payload: ApprovalDecision | None = None,
    user: AuthedUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PlatformWedding:
    """Suspend: guest/public pages 404 (guests never see why); wedding admins get
    a read-only dashboard with a suspension banner."""
    wedding = _get_wedding(db, wedding_id)
    wedding.status = WeddingStatus.SUSPENDED
    record(db, "wedding.suspend", user=user, wedding=wedding,
           detail={"reason": payload.reason if payload else None})
    db.commit()
    _notify_owner(db, settings, wedding, f"{wedding.couple_names}: suspended",
                  "Your wedding was suspended by the platform. Reply to this email for help.")
    return _platform_wedding(db, wedding)


@router.post("/weddings/{wedding_id}/reinstate", response_model=PlatformWedding)
def reinstate_wedding(
    wedding_id: UUID,
    user: AuthedUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PlatformWedding:
    """Reinstate a suspended (→ active) or archived (→ draft, undo window)
    wedding."""
    wedding = _get_wedding(db, wedding_id)
    if wedding.status == WeddingStatus.SUSPENDED:
        wedding.status = WeddingStatus.ACTIVE
    elif wedding.status == WeddingStatus.ARCHIVED:
        wedding.status = WeddingStatus.DRAFT
    else:
        raise HTTPException(status_code=409, detail="Nothing to reinstate")
    record(db, "wedding.reinstate", user=user, wedding=wedding)
    db.commit()
    _notify_owner(db, settings, wedding, f"{wedding.couple_names}: reinstated",
                  "Your wedding was reinstated.")
    return _platform_wedding(db, wedding)


# --- Approval queue ----------------------------------------------------------
@router.get("/approvals", response_model=list[ApprovalItem])
def approval_queue(db: Session = Depends(get_db)) -> list[ApprovalItem]:
    """Pending weddings with each auto-rule's verdict, so the reviewer sees WHY
    something queued instead of auto-approving."""
    pending = db.execute(
        select(Wedding)
        .where(Wedding.status == WeddingStatus.PENDING_APPROVAL)
        .order_by(Wedding.created_at)
    ).scalars().all()
    out: list[ApprovalItem] = []
    for w in pending:
        would, trace = evaluate_auto_approval(db, w)
        out.append(
            ApprovalItem(
                wedding=_platform_wedding(db, w),
                rule_trace=[RuleTraceEntry(**t) for t in trace],
                would_auto_approve=would,
            )
        )
    return out


# --- Rules editor --------------------------------------------------------------
@router.get("/settings/approval", response_model=PlatformSettingsPayload)
def get_settings_approval(db: Session = Depends(get_db)) -> PlatformSettingsPayload:
    return PlatformSettingsPayload(**get_approval_rules(db))


@router.put("/settings/approval", response_model=PlatformSettingsPayload)
def put_settings_approval(
    payload: PlatformSettingsPayload,
    user: AuthedUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformSettingsPayload:
    rules = set_approval_rules(db, payload.model_dump())
    record(db, "platform.settings", user=user, detail=rules)
    db.commit()
    return PlatformSettingsPayload(**rules)


# --- Users view ----------------------------------------------------------------
@router.get("/users", response_model=list[PlatformUser])
def list_users(db: Session = Depends(get_db)) -> list[PlatformUser]:
    profiles = db.execute(select(Profile).order_by(Profile.created_at.desc())).scalars().all()
    admin_ids = {a.user_id for a in db.execute(select(PlatformAdmin)).scalars()}
    out: list[PlatformUser] = []
    for p in profiles:
        wedding_count = db.execute(
            select(func.count()).select_from(WeddingMember).where(
                WeddingMember.user_id == p.user_id,
                WeddingMember.status == MemberStatus.active,
            )
        ).scalar_one()
        out.append(
            PlatformUser(
                user_id=p.user_id,
                email=p.email,
                display_name=p.display_name,
                disabled=p.disabled,
                is_platform_admin=p.user_id in admin_ids,
                wedding_count=wedding_count,
                created_at=p.created_at,
            )
        )
    return out


@router.post("/users/{user_id}/disable", response_model=PlatformUser)
def set_user_disabled(
    user_id: str,
    payload: UserDisableUpdate,
    user: AuthedUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformUser:
    """Disable/re-enable an account. A disabled account still authenticates with
    Supabase but every API check refuses it (and once real infra exists this is
    where the Supabase ban call goes too)."""
    profile = db.get(Profile, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user_id == user.sub and payload.disabled:
        raise HTTPException(status_code=409, detail="You can't disable your own account")
    profile.disabled = payload.disabled
    record(db, "user.disable" if payload.disabled else "user.enable",
           user=user, target_type="user", target_id=user_id)
    db.commit()
    return PlatformUser(
        user_id=profile.user_id, email=profile.email, display_name=profile.display_name,
        disabled=profile.disabled, created_at=profile.created_at,
    )


# --- Platform admins -------------------------------------------------------------
@router.get("/admins", response_model=list[str])
def list_platform_admins(db: Session = Depends(get_db)) -> list[str]:
    return [a.user_id for a in db.execute(select(PlatformAdmin)).scalars()]


@router.post("/admins/{user_id}", response_model=list[str], status_code=201)
def grant_platform_admin(
    user_id: str,
    user: AuthedUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[str]:
    if db.get(Profile, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    if db.get(PlatformAdmin, user_id) is None:
        db.add(PlatformAdmin(user_id=user_id, granted_by=user.sub))
        record(db, "platform.admin_grant", user=user, target_type="user", target_id=user_id)
        db.commit()
    return [a.user_id for a in db.execute(select(PlatformAdmin)).scalars()]


@router.delete("/admins/{user_id}", response_model=list[str])
def revoke_platform_admin(
    user_id: str,
    user: AuthedUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[str]:
    if user_id == user.sub:
        raise HTTPException(status_code=409, detail="You can't revoke your own admin access")
    row = db.get(PlatformAdmin, user_id)
    if row is not None:
        db.delete(row)
        record(db, "platform.admin_revoke", user=user, target_type="user", target_id=user_id)
        db.commit()
    return [a.user_id for a in db.execute(select(PlatformAdmin)).scalars()]


# --- Ops widgets + audit tail ------------------------------------------------------
@router.get("/stats", response_model=PlatformStats)
def stats(db: Session = Depends(get_db)) -> PlatformStats:
    by_status: dict[str, int] = {}
    for status_value, count in db.execute(
        select(Wedding.status, func.count()).group_by(Wedding.status)
    ):
        by_status[status_value] = count
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    week_ago_naive = week_ago.replace(tzinfo=None)

    def _count_since(model, column):
        # SQLite stores naive datetimes; Postgres tz-aware — try aware, fall back.
        try:
            return db.execute(
                select(func.count()).select_from(model).where(column >= week_ago)
            ).scalar_one()
        except Exception:
            return db.execute(
                select(func.count()).select_from(model).where(column >= week_ago_naive)
            ).scalar_one()

    return PlatformStats(
        weddings_by_status=by_status,
        total_users=db.execute(select(func.count()).select_from(Profile)).scalar_one(),
        total_guests=db.execute(select(func.count()).select_from(Guest)).scalar_one(),
        rsvps_last_7_days=_count_since(Rsvp, Rsvp.responded_at),
        signups_last_7_days=_count_since(Profile, Profile.created_at),
    )


@router.get("/audit", response_model=list[AuditEntry])
def audit_tail(
    limit: int = Query(50, ge=1, le=500),
    wedding_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
) -> list[AuditEntry]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if wedding_id is not None:
        stmt = stmt.where(AuditLog.wedding_id == wedding_id)
    return [
        AuditEntry(
            id=a.id, wedding_id=a.wedding_id, actor_email=a.actor_email, action=a.action,
            target_type=a.target_type, target_id=a.target_id, detail=a.detail or {},
            created_at=a.created_at,
        )
        for a in db.execute(stmt).scalars()
    ]


# --- Plans & entitlements (Phase 5) -------------------------------------------------
def _plan_admin(p: Plan) -> PlanAdmin:
    return PlanAdmin(
        id=p.id, name=p.name, description=p.description, is_default=p.is_default,
        entitlements=p.entitlements or {}, archived=p.archived, created_at=p.created_at,
    )


def _clear_default(db: Session, except_id=None) -> None:
    for p in db.execute(select(Plan).where(Plan.is_default.is_(True))).scalars():
        if p.id != except_id:
            p.is_default = False


@router.get("/plans", response_model=list[PlanAdmin])
def list_plans(db: Session = Depends(get_db)) -> list[PlanAdmin]:
    return [
        _plan_admin(p)
        for p in db.execute(select(Plan).order_by(Plan.created_at)).scalars()
    ]


@router.post("/plans", response_model=PlanAdmin, status_code=201)
def create_plan(
    payload: PlanCreate,
    user: AuthedUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlanAdmin:
    if db.execute(select(Plan).where(Plan.name == payload.name)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A plan with that name already exists")
    plan = Plan(
        name=payload.name, description=payload.description,
        is_default=payload.is_default, entitlements=payload.entitlements,
    )
    db.add(plan)
    db.flush()
    if plan.is_default:
        _clear_default(db, except_id=plan.id)
    record(db, "plan.create", user=user, target_type="plan", target_id=plan.id,
           detail={"name": plan.name})
    db.commit()
    return _plan_admin(plan)


@router.patch("/plans/{plan_id}", response_model=PlanAdmin)
def update_plan(
    plan_id: UUID,
    payload: PlanUpdate,
    user: AuthedUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlanAdmin:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None or field in ("description",):
            setattr(plan, field, value)
    if data.get("is_default"):
        _clear_default(db, except_id=plan.id)
    record(db, "plan.update", user=user, target_type="plan", target_id=plan.id, detail=data)
    db.commit()
    return _plan_admin(plan)


@router.put("/weddings/{wedding_id}/plan", response_model=WeddingPlanAdmin)
def assign_plan(
    wedding_id: UUID,
    payload: PlanAssign,
    user: AuthedUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> WeddingPlanAdmin:
    """Assign a plan and/or per-wedding overrides. `plan_id: null` clears the
    assignment (back to the default plan); overrides merge-replace wholesale."""
    wedding = _get_wedding(db, wedding_id)
    wp = db.get(WeddingPlan, wedding.id)

    if payload.plan_id is None and payload.overrides is None:
        if wp is not None:
            db.delete(wp)
            db.flush()
            wp = None
    else:
        plan = None
        if payload.plan_id is not None:
            plan = db.get(Plan, payload.plan_id)
            if plan is None or plan.archived:
                raise HTTPException(status_code=404, detail="Plan not found")
        if wp is None:
            if plan is None:
                raise HTTPException(status_code=422, detail="A plan_id is required first")
            wp = WeddingPlan(wedding_id=wedding.id, plan_id=plan.id, assigned_by=user.sub)
            db.add(wp)
        if plan is not None:
            wp.plan_id = plan.id
        if payload.overrides is not None:
            wp.overrides = payload.overrides
        wp.valid_until = payload.valid_until
        wp.assigned_by = user.sub
        db.flush()

    record(db, "plan.assign", user=user, wedding=wedding, target_type="wedding",
           target_id=wedding.id,
           detail={"plan_id": str(payload.plan_id) if payload.plan_id else None,
                   "overrides": payload.overrides})
    db.commit()
    db.refresh(wedding)
    wp = db.get(WeddingPlan, wedding.id)
    return WeddingPlanAdmin(
        wedding_id=wedding.id,
        plan=_plan_admin(wp.plan) if wp is not None and wp.plan is not None else None,
        overrides=wp.overrides if wp is not None else {},
        effective=effective_entitlements(db, wedding),
        valid_until=wp.valid_until if wp is not None else None,
    )
