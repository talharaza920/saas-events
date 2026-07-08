"""Plans & entitlements engine (SAAS_PLAN Phase 5) — server-side enforcement.

Effective entitlements = DEFAULT_ENTITLEMENTS ∪ default-plan ∪ assigned-plan ∪
per-wedding overrides. Checked on CREATE only — lowering a plan below current
usage blocks new adds, never deletes data. The frontend reads the same block
from `/api/w/{slug}/admin/me` to gray out UI; the server is the source of truth.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Plan, Wedding, WeddingPlan

# Baseline when no plan exists at all (fresh platform, or plan deleted).
# Generous enough not to get in the way of a self-hosted/local install.
DEFAULT_ENTITLEMENTS: dict = {
    "max_guests": 200,
    "max_members": 5,
    "max_custom_questions": 20,  # 0 = feature off
    "max_story_arcs": 10,
    "max_storage_mb": 500,
    "wishes_enabled": True,
    "export_enabled": True,
    "import_enabled": True,
    "custom_domain": False,  # future (Phase 7)
    "remove_platform_badge": False,
    "max_weddings_per_account": 3,  # account-level, checked at creation
}

# Human labels for "not on your plan" messaging (kept server-side so the API's
# 403 detail is friendly without the frontend needing a lookup table).
_LIMIT_MESSAGES = {
    "max_guests": "Guest limit reached for this wedding's plan",
    "max_members": "Team-member limit reached for this wedding's plan",
    "max_custom_questions": "Custom-question limit reached for this wedding's plan",
    "max_story_arcs": "Story-chapter limit reached for this wedding's plan",
    "max_weddings_per_account": "You've reached the number of weddings your account allows",
}
_FEATURE_MESSAGES = {
    "wishes_enabled": "The guestbook isn't available on this wedding's plan",
    "export_enabled": "Exports aren't available on this wedding's plan",
    "import_enabled": "Spreadsheet import isn't available on this wedding's plan",
}
_UPGRADE_HINT = " — contact us to upgrade"


def default_plan(db: Session) -> Plan | None:
    return db.execute(
        select(Plan).where(Plan.is_default.is_(True), Plan.archived.is_(False))
    ).scalars().first()


def _plan_assignment(db: Session, wedding: Wedding) -> WeddingPlan | None:
    wp = db.get(WeddingPlan, wedding.id)
    if wp is None:
        return None
    if wp.valid_until is not None:
        until = wp.valid_until
        now = datetime.now(timezone.utc)
        if until.tzinfo is None:
            now = now.replace(tzinfo=None)
        if until < now:  # expired assignment → fall back to the default plan
            return None
    return wp


def effective_entitlements(db: Session, wedding: Wedding) -> dict:
    """The merged entitlement block for one wedding."""
    out = dict(DEFAULT_ENTITLEMENTS)
    wp = _plan_assignment(db, wedding)
    plan = wp.plan if wp is not None else default_plan(db)
    if plan is not None and isinstance(plan.entitlements, dict):
        out.update(plan.entitlements)
    if wp is not None and isinstance(wp.overrides, dict):
        out.update(wp.overrides)
    return out


def _denied(message: str) -> HTTPException:
    return HTTPException(status_code=403, detail=message + _UPGRADE_HINT)


def check_limit(db: Session, wedding: Wedding, key: str, current_count: int, adding: int = 1) -> None:
    """Raise 403 when `current_count + adding` would exceed the numeric
    entitlement `key`. A missing key falls back to the defaults; a value of 0
    means the feature is off entirely."""
    limit = effective_entitlements(db, wedding).get(key, DEFAULT_ENTITLEMENTS.get(key))
    if not isinstance(limit, (int, float)) or isinstance(limit, bool):
        return  # malformed entitlement — never lock a tenant out over bad config
    if current_count + adding > limit:
        raise _denied(_LIMIT_MESSAGES.get(key, "Plan limit reached"))


def require_feature(db: Session, wedding: Wedding, key: str) -> None:
    """Raise 403 when boolean entitlement `key` is off."""
    if not effective_entitlements(db, wedding).get(key, DEFAULT_ENTITLEMENTS.get(key)):
        raise _denied(_FEATURE_MESSAGES.get(key, "Not available on this wedding's plan"))


def feature_enabled(db: Session, wedding: Wedding, key: str) -> bool:
    return bool(effective_entitlements(db, wedding).get(key, DEFAULT_ENTITLEMENTS.get(key)))
