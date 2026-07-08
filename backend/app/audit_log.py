"""Platform audit trail (SAAS_PLAN 1.2 `audit_log`) — one small helper.

Called from mutating admin/platform endpoints just before their commit; rides
the caller's transaction (no separate commit) so the audit row lands atomically
with the change it describes. Cheap to write now, impossible to retrofit later.

Distinct from app/audit.py, which stamps provenance ON the RSVP row itself.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.auth import AuthedUser
from app.models import AuditLog, Wedding


def record(
    db: Session,
    action: str,
    *,
    user: AuthedUser | None = None,
    wedding: Wedding | None = None,
    target_type: str | None = None,
    target_id: object = None,
    detail: dict | None = None,
) -> None:
    """Append an audit row (uncommitted — the caller's commit persists it).

    `action` is dotted lowercase, subject.verb: "wedding.approve",
    "member.invite", "guest.import", "plan.assign", …
    """
    db.add(
        AuditLog(
            wedding_id=wedding.id if wedding is not None else None,
            actor_user_id=user.sub if user is not None else None,
            actor_email=user.email if user is not None else None,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            detail=detail or {},
        )
    )
