"""Approval workflow rules (SAAS_PLAN 2.2) — auto-approval evaluation.

The platform admin edits one `platform_settings` blob (key "approval") from the
console. When an owner submits a wedding for approval we evaluate the rules and
either activate instantly (all pass, auto_approve on) or queue it for manual
review — returning the per-rule trace either way, so the console can show WHY
something was queued.
"""
from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Guest, PlatformSetting, Profile, Wedding, WeddingMember
from app.timeutil import as_utc, utcnow

APPROVAL_KEY = "approval"

# Defaults: auto-approval OFF (everything queues for manual review) with sane
# thresholds pre-filled for when it's switched on.
DEFAULT_APPROVAL_RULES = {
    "auto_approve": False,
    "require_verified_email": True,
    "min_account_age_hours": 0,
    "max_weddings_per_account": 3,
    "max_guests_at_submission": 500,
    "banned_words": [],
}


def get_approval_rules(db: Session) -> dict:
    row = db.get(PlatformSetting, APPROVAL_KEY)
    rules = dict(DEFAULT_APPROVAL_RULES)
    if row is not None and isinstance(row.value, dict):
        rules.update(row.value)
    return rules


def set_approval_rules(db: Session, rules: dict) -> dict:
    """Replace the approval blob (uncommitted — caller commits)."""
    row = db.get(PlatformSetting, APPROVAL_KEY)
    if row is None:
        row = PlatformSetting(key=APPROVAL_KEY, value=rules)
        db.add(row)
    else:
        row.value = rules
    return rules


def _banned_hits(wedding: Wedding, banned: list[str]) -> list[str]:
    """Banned words found in the slug / names / content (case-insensitive).
    Content is scanned as one JSON dump — crude but effective for review flags."""
    if not banned:
        return []
    hay = " ".join(
        [
            wedding.slug,
            wedding.couple_names,
            json.dumps(wedding.content or {}, ensure_ascii=False),
            json.dumps(wedding.event_details or {}, ensure_ascii=False),
        ]
    ).lower()
    return [w for w in banned if w and w.lower() in hay]


def evaluate_auto_approval(
    db: Session, wedding: Wedding, rules: dict | None = None
) -> tuple[bool, list[dict]]:
    """(would_auto_approve, trace). The trace lists every rule with ok/detail —
    stored in the audit log and shown in the console's approval queue.

    Conditions (all must pass, and auto_approve must be on):
    email verified, account age ≥ N hours, ≤ N weddings per account,
    guest count at submission ≤ N, no banned-word hits.

    Callers evaluating a whole page (the approvals queue) pass `rules` so the
    settings blob is read once, not per wedding.
    """
    if rules is None:
        rules = get_approval_rules(db)
    trace: list[dict] = []

    creator: Profile | None = db.get(Profile, wedding.owner_id) if wedding.owner_id else None

    # Email verified: auth refuses unverified Supabase sessions outright, and the
    # local dev principals count as verified — so this passes when a profile
    # exists (kept as an explicit rule so the console shows it evaluated).
    if rules.get("require_verified_email", True):
        ok = creator is not None and not creator.disabled
        trace.append(
            {"rule": "verified_email", "ok": ok, "detail": None if ok else "creator account missing or disabled"}
        )

    min_age = int(rules.get("min_account_age_hours", 0) or 0)
    if min_age > 0:
        ok = False
        detail = "creator account unknown"
        if creator is not None and creator.created_at is not None:
            age_h = (utcnow() - as_utc(creator.created_at)).total_seconds() / 3600
            ok = age_h >= min_age
            detail = None if ok else f"account is {age_h:.1f}h old (< {min_age}h)"
        trace.append({"rule": "account_age", "ok": ok, "detail": detail})

    max_w = int(rules.get("max_weddings_per_account", 0) or 0)
    if max_w > 0 and wedding.owner_id:
        count = db.execute(
            select(func.count())
            .select_from(WeddingMember)
            .where(WeddingMember.user_id == wedding.owner_id)
        ).scalar_one()
        ok = count <= max_w
        trace.append(
            {"rule": "weddings_per_account", "ok": ok,
             "detail": None if ok else f"{count} weddings (max {max_w})"}
        )

    max_g = int(rules.get("max_guests_at_submission", 0) or 0)
    if max_g > 0:
        count = db.execute(
            select(func.count()).select_from(Guest).where(Guest.wedding_id == wedding.id)
        ).scalar_one()
        ok = count <= max_g
        trace.append(
            {"rule": "guest_count", "ok": ok, "detail": None if ok else f"{count} guests (max {max_g})"}
        )

    hits = _banned_hits(wedding, rules.get("banned_words") or [])
    trace.append(
        {"rule": "banned_words", "ok": not hits, "detail": None if not hits else f"hits: {', '.join(hits)}"}
    )

    all_ok = all(t["ok"] for t in trace)
    return bool(rules.get("auto_approve")) and all_ok, trace
