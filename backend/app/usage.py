"""Storage-usage reconciliation (REVIEW_BACKLOG P1-7).

`weddings.storage_bytes_used` is incremented on every upload, but a counter
alone drifts: replaced images keep their bytes, manual bucket cleanups aren't
seen, failures can double-count. This job re-measures each wedding's namespace
in the actual storage backend and rewrites the counter to truth. A namespace
that can't be measured (provider error) is skipped — never zeroed.

Triggered by /api/internal/cron/reconcile-storage (Vercel cron, weekly is
plenty). Full-scan by design: fine for hundreds of tenants; shard by slug
prefix if the platform ever outgrows that.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Wedding
from app.storage import measure_wedding_media

logger = logging.getLogger("app.usage")


def reconcile_storage(db: Session, settings: Settings) -> list[dict]:
    """Re-measure every wedding's media and correct drifted counters. Returns a
    summary entry per corrected wedding. Commits once at the end."""
    weddings = db.execute(select(Wedding)).scalars().all()
    corrected: list[dict] = []
    for w in weddings:
        measured = measure_wedding_media(settings, w.slug)
        if measured is None:
            continue  # couldn't measure — leave the counter alone
        if measured != (w.storage_bytes_used or 0):
            corrected.append(
                {
                    "wedding_id": str(w.id),
                    "slug": w.slug,
                    "from_bytes": w.storage_bytes_used or 0,
                    "to_bytes": measured,
                }
            )
            w.storage_bytes_used = measured
    if corrected:
        db.commit()
        logger.info("storage reconcile corrected %d wedding(s)", len(corrected))
    return corrected
