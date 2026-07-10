"""Hard-delete of archived weddings past the undo window (REVIEW_BACKLOG P1-9).

Archiving (owner "delete") is a soft delete with a 30-day undo; this module is
the promised purge. Selection rule: `status == archived` AND `archived_at` older
than the window. A NULL `archived_at` (pre-migration row) is deliberately never
purged — when in doubt, keep.

What a purge removes: the wedding row and, through ORM/DB cascades, its guests,
RSVPs, companions, answers, questions, story arcs, wishes and memberships — the
tenant's PII. The plan assignment is deleted explicitly and the audit trail is
KEPT with `wedding_id` nulled (mirrors the Postgres `ON DELETE SET NULL` on
SQLite, where dev runs don't enforce FKs), so "this tenant existed and was
purged" stays provable. Uploaded media is removed best-effort.

Triggered by POST /api/platform/purge-archived (console) or the cron endpoint
(Vercel cron → /api/internal/cron/purge-archived). This is also the seam for
GDPR-style deletion requests: archive, then purge.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit_log import record
from app.config import Settings
from app.models import AuditLog, Wedding, WeddingPlan, WeddingStatus
from app.storage import delete_wedding_media
from app.timeutil import as_utc, utcnow

PURGE_AFTER_DAYS = 30


def purge_archived_weddings(
    db: Session, settings: Settings, *, now: datetime | None = None
) -> list[dict]:
    """Hard-delete every wedding archived more than PURGE_AFTER_DAYS ago.
    Returns a summary entry per purged wedding (also written to the audit log).
    Commits once at the end."""
    now = now or utcnow()
    cutoff = now - timedelta(days=PURGE_AFTER_DAYS)

    # Cheap status filter in SQL; the timestamp compare happens in Python so the
    # naive-vs-aware storage difference between SQLite and Postgres can't skew it.
    archived = (
        db.execute(select(Wedding).where(Wedding.status == WeddingStatus.ARCHIVED))
        .scalars()
        .all()
    )
    due = [w for w in archived if w.archived_at is not None and as_utc(w.archived_at) <= cutoff]

    purged: list[dict] = []
    for wedding in due:
        summary = {
            "wedding_id": str(wedding.id),
            "slug": wedding.slug,
            "archived_at": as_utc(wedding.archived_at).isoformat(),
        }
        delete_wedding_media(settings, wedding.slug)
        # Keep the trail, lose the pointer (Postgres does this via SET NULL; done
        # explicitly so SQLite behaves identically).
        db.execute(
            update(AuditLog).where(AuditLog.wedding_id == wedding.id).values(wedding_id=None)
        )
        wp = db.get(WeddingPlan, wedding.id)
        if wp is not None:
            db.delete(wp)
        db.delete(wedding)  # ORM cascades take guests → rsvps → companions/answers etc.
        # The purge record itself carries no wedding_id (the row is gone) — the
        # identifying facts live in `detail`.
        record(db, "wedding.purge", target_type="wedding", target_id=wedding.id, detail=summary)
        purged.append(summary)

    if purged:
        db.commit()
    return purged
