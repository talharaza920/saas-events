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
  GET/PUT /settings/ai               → AI circuit breaker (kill switch, cost ceiling)
  GET/PUT /ai/prompts (+ /activate)  → prompt registry editor (versioned, rollback)
  GET  /ai/usage                     → AI spend widgets (Phase 8.4)
"""
from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.jobs import get_ai_settings, set_ai_settings
from app.ai.runtime import effective_settings
from app.ai.ledger import cost_usd_today
from app.ai.prompts import CODE_DEFAULTS, resolve_spec
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
from app.purge import purge_archived_weddings
from app.timeutil import as_utc, db_bind_utc, utcnow
from app.models import (
    AiJob,
    AiPrompt,
    AiUsageLedger,
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
    AiPromptActivate,
    AiPromptAdmin,
    AiPromptSave,
    AiSettingsPayload,
    AiSettingsView,
    AiUsageDay,
    AiUsageSummary,
    AiUsageTopWedding,
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


def _platform_wedding_cards(db: Session, weddings: list[Wedding]) -> list[PlatformWedding]:
    """Build the console's wedding cards with a FIXED number of queries (grouped
    counts + batched lookups), however many weddings are on the page — the
    per-wedding version was 4-5 queries each (review backlog #8)."""
    if not weddings:
        return []
    ids = [w.id for w in weddings]
    member_counts = dict(
        db.execute(
            select(WeddingMember.wedding_id, func.count())
            .where(
                WeddingMember.wedding_id.in_(ids),
                WeddingMember.status == MemberStatus.active,
            )
            .group_by(WeddingMember.wedding_id)
        ).all()
    )
    guest_counts = dict(
        db.execute(
            select(Guest.wedding_id, func.count())
            .where(Guest.wedding_id.in_(ids))
            .group_by(Guest.wedding_id)
        ).all()
    )
    plan_names = dict(
        db.execute(
            select(WeddingPlan.wedding_id, Plan.name)
            .join(Plan, WeddingPlan.plan_id == Plan.id)
            .where(WeddingPlan.wedding_id.in_(ids))
        ).all()
    )
    # Earliest active owner per wedding (rows come back ordered by created_at,
    # so the first seen per wedding wins — same pick as _owner_email).
    owner_rows = (
        db.execute(
            select(WeddingMember)
            .where(
                WeddingMember.wedding_id.in_(ids),
                WeddingMember.role == MemberRole.owner,
                WeddingMember.status == MemberStatus.active,
            )
            .order_by(WeddingMember.created_at)
        )
        .scalars()
        .all()
    )
    owner_by_wedding: dict = {}
    for m in owner_rows:
        owner_by_wedding.setdefault(m.wedding_id, m)
    owner_user_ids = [m.user_id for m in owner_by_wedding.values() if m.user_id]
    # user_id → profile email; a key that EXISTS mirrors "profile found" in
    # _owner_email (its email wins even when None, never the invited_email).
    profile_emails: dict = {}
    if owner_user_ids:
        profile_emails = dict(
            db.execute(
                select(Profile.user_id, Profile.email).where(Profile.user_id.in_(owner_user_ids))
            ).all()
        )

    def _email(m: WeddingMember | None) -> str | None:
        if m is None:
            return None
        if m.user_id and m.user_id in profile_emails:
            return profile_emails[m.user_id]
        return m.invited_email

    return [
        PlatformWedding(
            id=w.id,
            slug=w.slug,
            couple_names=w.couple_names,
            status=w.status,
            published=w.published,
            owner_email=_email(owner_by_wedding.get(w.id)),
            member_count=member_counts.get(w.id, 0),
            guest_count=guest_counts.get(w.id, 0),
            plan_name=plan_names.get(w.id),
            created_at=w.created_at,
        )
        for w in weddings
    ]


def _platform_wedding(db: Session, wedding: Wedding) -> PlatformWedding:
    return _platform_wedding_cards(db, [wedding])[0]


@router.get("/weddings", response_model=list[PlatformWedding])
def list_weddings(
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[PlatformWedding]:
    stmt = select(Wedding).order_by(Wedding.created_at.desc()).limit(limit).offset(offset)
    if status:
        stmt = stmt.where(Wedding.status == status)
    return _platform_wedding_cards(db, db.execute(stmt).scalars().all())


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
        wedding.archived_at = None  # undo used — stop the purge clock
    else:
        raise HTTPException(status_code=409, detail="Nothing to reinstate")
    record(db, "wedding.reinstate", user=user, wedding=wedding)
    db.commit()
    _notify_owner(db, settings, wedding, f"{wedding.couple_names}: reinstated",
                  "Your wedding was reinstated.")
    return _platform_wedding(db, wedding)


# --- Archived-wedding purge (REVIEW_BACKLOG P1-9) ------------------------------
@router.post("/purge-archived")
def purge_archived(
    user: AuthedUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Manually run the archived-wedding purge (hard-deletes weddings archived
    more than 30 days ago). The scheduled path is the cron endpoint in
    app/routers/internal.py; this button is for the console / GDPR requests."""
    purged = purge_archived_weddings(db, settings)
    return {"purged": purged, "count": len(purged)}


# --- Approval queue ----------------------------------------------------------
@router.get("/approvals", response_model=list[ApprovalItem])
def approval_queue(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[ApprovalItem]:
    """Pending weddings with each auto-rule's verdict, so the reviewer sees WHY
    something queued instead of auto-approving. Rules are loaded once for the
    page; the per-wedding trace queries (guest/wedding counts) stay per item."""
    pending = db.execute(
        select(Wedding)
        .where(Wedding.status == WeddingStatus.PENDING_APPROVAL)
        .order_by(Wedding.created_at)
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    cards = _platform_wedding_cards(db, pending)
    rules = get_approval_rules(db)
    out: list[ApprovalItem] = []
    for w, card in zip(pending, cards):
        would, trace = evaluate_auto_approval(db, w, rules=rules)
        out.append(
            ApprovalItem(
                wedding=card,
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
def list_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[PlatformUser]:
    profiles = (
        db.execute(
            select(Profile).order_by(Profile.created_at.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    admin_ids = {a.user_id for a in db.execute(select(PlatformAdmin)).scalars()}
    # One grouped count for the whole page (was one COUNT per profile).
    wedding_counts: dict = {}
    if profiles:
        wedding_counts = dict(
            db.execute(
                select(WeddingMember.user_id, func.count())
                .where(
                    WeddingMember.user_id.in_([p.user_id for p in profiles]),
                    WeddingMember.status == MemberStatus.active,
                )
                .group_by(WeddingMember.user_id)
            ).all()
        )
    return [
        PlatformUser(
            user_id=p.user_id,
            email=p.email,
            display_name=p.display_name,
            disabled=p.disabled,
            is_platform_admin=p.user_id in admin_ids,
            wedding_count=wedding_counts.get(p.user_id, 0),
            created_at=p.created_at,
        )
        for p in profiles
    ]


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
    # Bound in the dialect's own form (naive on SQLite, aware on Postgres) so the
    # comparison is exact on both — see app/timeutil.py.
    week_ago = db_bind_utc(db, utcnow() - timedelta(days=7))

    def _count_since(model, column):
        return db.execute(
            select(func.count()).select_from(model).where(column >= week_ago)
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


# --- AI console (Phase 8.4) ------------------------------------------------------
def _ai_settings_view(db: Session, settings: Settings, stored: dict) -> AiSettingsView:
    """The stored blob + what is actually in force. `effective_*` is resolved by
    the very same function the pipeline uses, so the console cannot drift from
    what the next run will do."""
    live = effective_settings(db, settings)
    return AiSettingsView(
        kill_switch=bool(stored.get("kill_switch")),
        daily_cost_ceiling_usd=stored.get("daily_cost_ceiling_usd") or 0,
        text_provider=stored.get("text_provider") or "",
        text_model=stored.get("text_model") or "",
        text_effort=stored.get("text_effort") or "",
        effective_provider=live.ai_text_provider,
        effective_model=live.text_model,
        effective_effort=live.ai_text_effort,
        from_env=not any(
            stored.get(k) for k in ("text_provider", "text_model", "text_effort")
        ),
        # Booleans only — an API key never crosses this wire.
        keys_configured={
            "anthropic": bool(settings.anthropic_api_key),
            "openai": bool(settings.openai_api_key),
        },
        live_calls=live.ai_text_live,
    )


@router.get("/settings/ai", response_model=AiSettingsView)
def get_settings_ai(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> AiSettingsView:
    return _ai_settings_view(db, settings, get_ai_settings(db))


@router.put("/settings/ai", response_model=AiSettingsView)
def put_settings_ai(
    payload: AiSettingsPayload,
    user: AuthedUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AiSettingsView:
    """The circuit breaker (guardrail 6) plus the platform-wide text model.

    Breaker: the kill switch stops new jobs and advances immediately; the
    ceiling makes in-flight runs queue, never fail. Model: overrides the env
    bootstrap platform-wide (ids churn faster than deploys) — blank a field to
    fall back to the deployed default. Audited, like every platform write.
    """
    merged = set_ai_settings(db, payload.model_dump())
    record(db, "platform.settings.ai", user=user, detail=merged)
    db.commit()
    return _ai_settings_view(db, settings, merged)


def _prompt_admin(row: AiPrompt, *, effective: bool) -> AiPromptAdmin:
    return AiPromptAdmin(
        key=row.key, provider=row.provider, version=row.version,
        template=row.template, model=row.model, effort=row.effort,
        max_tokens=row.max_tokens, active=row.active,
        updated_by=row.updated_by, updated_at=row.updated_at,
        is_effective=effective,
    )


@router.get("/ai/prompts", response_model=list[AiPromptAdmin])
def list_ai_prompts(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[AiPromptAdmin]:
    """Every key's code default (version 0) plus all DB override rows, with
    `is_effective` marking what resolve_spec actually picks under the
    configured text provider."""
    out: list[AiPromptAdmin] = []
    for key in sorted(CODE_DEFAULTS):
        spec = CODE_DEFAULTS[key]
        effective = resolve_spec(db, key, provider=settings.ai_text_provider)
        out.append(
            AiPromptAdmin(
                key=key, provider="", version=0, template=spec.template,
                model=spec.model, effort=spec.effort, max_tokens=spec.max_tokens,
                active=True, is_code_default=True,
                is_effective=effective.version == 0,
            )
        )
        rows = db.execute(
            select(AiPrompt).where(AiPrompt.key == key)
            .order_by(AiPrompt.provider, AiPrompt.version)
        ).scalars().all()
        for row in rows:
            out.append(
                _prompt_admin(
                    row,
                    effective=(
                        effective.version == row.version
                        and effective.provider == row.provider
                    ),
                )
            )
    return out


@router.put("/ai/prompts/{key}", response_model=AiPromptAdmin)
def save_ai_prompt(
    key: str,
    payload: AiPromptSave,
    user: AuthedUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AiPromptAdmin:
    """Save a NEW active version (rows are never edited in place — rollback =
    deactivate the bad one and resolution falls back). Only known keys: a row
    under a key the pipeline never renders would be dead config."""
    if key not in CODE_DEFAULTS:
        raise HTTPException(status_code=404, detail="Unknown prompt key")
    next_version = (
        db.execute(
            select(func.coalesce(func.max(AiPrompt.version), 0)).where(
                AiPrompt.key == key, AiPrompt.provider == payload.provider
            )
        ).scalar_one()
        + 1
    )
    row = AiPrompt(
        key=key, provider=payload.provider, version=next_version,
        template=payload.template, model=payload.model, effort=payload.effort,
        max_tokens=payload.max_tokens, active=True, updated_by=user.sub,
    )
    db.add(row)
    record(db, "ai.prompt.save", user=user,
           detail={"key": key, "provider": payload.provider, "version": next_version})
    db.commit()
    db.refresh(row)
    effective = resolve_spec(db, key, provider=settings.ai_text_provider)
    return _prompt_admin(
        row,
        effective=(effective.version == row.version and effective.provider == row.provider),
    )


@router.post("/ai/prompts/{key}/activate", response_model=AiPromptAdmin)
def set_ai_prompt_active(
    key: str,
    payload: AiPromptActivate,
    user: AuthedUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AiPromptAdmin:
    """Activate/deactivate one version — the rollback lever. Deactivating every
    row is safe: resolution falls back to the code default, never bricks."""
    row = db.get(AiPrompt, (key, payload.provider, payload.version))
    if row is None:
        raise HTTPException(status_code=404, detail="Prompt version not found")
    row.active = payload.active
    row.updated_by = user.sub
    record(db, "ai.prompt.activate", user=user,
           detail={"key": key, "provider": payload.provider,
                   "version": payload.version, "active": payload.active})
    db.commit()
    effective = resolve_spec(db, key, provider=settings.ai_text_provider)
    return _prompt_admin(
        row,
        effective=(effective.version == row.version and effective.provider == row.provider),
    )


@router.get("/ai/usage", response_model=AiUsageSummary)
def ai_usage(db: Session = Depends(get_db)) -> AiUsageSummary:
    """Spend widgets (guardrail 10): last 30 days aggregated in Python — the
    ledger at this scale is small, and it keeps the date math dialect-free."""
    ai_settings = get_ai_settings(db)
    since = utcnow() - timedelta(days=30)
    rows = db.execute(
        select(
            AiUsageLedger.wedding_id, AiUsageLedger.provider, AiUsageLedger.kind,
            AiUsageLedger.cost_usd_micros, AiUsageLedger.created_at,
        ).where(AiUsageLedger.created_at >= db_bind_utc(db, since))
    ).all()

    days: dict[str, dict] = {}
    by_kind: dict[str, float] = {}
    by_provider: dict[str, float] = {}
    per_wedding: dict = {}
    for wedding_id, provider, kind, micros, created_at in rows:
        usd = (micros or 0) / 1_000_000
        day = as_utc(created_at).date().isoformat()
        bucket = days.setdefault(day, {"usd": 0.0, "calls": 0})
        bucket["usd"] += usd
        bucket["calls"] += 1
        by_kind[kind] = by_kind.get(kind, 0.0) + usd
        by_provider[provider] = by_provider.get(provider, 0.0) + usd
        if wedding_id is not None:
            per_wedding[wedding_id] = per_wedding.get(wedding_id, 0.0) + usd

    top = sorted(per_wedding.items(), key=lambda kv: kv[1], reverse=True)[:10]
    top_weddings = []
    for wedding_id, usd in top:
        w = db.get(Wedding, wedding_id)
        top_weddings.append(
            AiUsageTopWedding(wedding_id=wedding_id, slug=w.slug if w else None, usd=round(usd, 6))
        )

    jobs_by_status = {
        status: count
        for status, count in db.execute(
            select(AiJob.status, func.count()).group_by(AiJob.status)
        ).all()
    }
    return AiUsageSummary(
        today_usd=cost_usd_today(db),
        ceiling_usd=ai_settings.get("daily_cost_ceiling_usd") or 0,
        kill_switch=bool(ai_settings.get("kill_switch")),
        days=[
            AiUsageDay(date=d, usd=round(v["usd"], 6), calls=v["calls"])
            for d, v in sorted(days.items())
        ],
        by_kind={k: round(v, 6) for k, v in by_kind.items()},
        by_provider={k: round(v, 6) for k, v in by_provider.items()},
        top_weddings=top_weddings,
        jobs_by_status=jobs_by_status,
    )
