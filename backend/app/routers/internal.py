"""Internal (machine-to-machine) endpoints — `/api/internal/*`.

Not user-facing: these are for schedulers (Vercel cron) that can't hold a
Supabase session. Auth is a shared secret — `Authorization: Bearer $CRON_SECRET`
— compared constant-time. With no CRON_SECRET configured every route here is a
neutral 404, so the surface simply doesn't exist until ops turns it on.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.ai.jobs import reap_expired_jobs
from app.config import Settings, get_settings
from app.db import get_db
from app.purge import purge_archived_weddings
from app.usage import reconcile_storage

router = APIRouter(prefix="/api/internal", tags=["internal"])


def require_cron_secret(
    authorization: str | None = Header(None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.cron_secret:
        # Feature not configured — indistinguishable from "no such route".
        raise HTTPException(status_code=404, detail="Not found")
    supplied = ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:]
    if not secrets.compare_digest(supplied, settings.cron_secret):
        raise HTTPException(status_code=401, detail="Invalid cron secret")


# GET as well as POST: Vercel cron only issues GETs.
@router.get("/cron/purge-archived", dependencies=[Depends(require_cron_secret)])
@router.post("/cron/purge-archived", dependencies=[Depends(require_cron_secret)])
def cron_purge_archived(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Scheduled hard-delete of weddings archived past the 30-day undo window."""
    purged = purge_archived_weddings(db, settings)
    return {"purged": purged, "count": len(purged)}


@router.get("/cron/reap-ai-jobs", dependencies=[Depends(require_cron_secret)])
@router.post("/cron/reap-ai-jobs", dependencies=[Depends(require_cron_secret)])
def cron_reap_ai_jobs(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Scheduled sweep of stuck AI jobs (expired + hold refunded) and orphaned
    raw inputs incl. their stored media (see app/ai/jobs.py::reap_expired_jobs)."""
    return reap_expired_jobs(db, settings)


@router.get("/cron/reconcile-storage", dependencies=[Depends(require_cron_secret)])
@router.post("/cron/reconcile-storage", dependencies=[Depends(require_cron_secret)])
def cron_reconcile_storage(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Scheduled correction of each wedding's `storage_bytes_used` counter
    against what's actually in the storage bucket (see app/usage.py)."""
    corrected = reconcile_storage(db, settings)
    return {"corrected": corrected, "count": len(corrected)}
