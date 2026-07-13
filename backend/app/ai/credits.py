"""Credit accounting for AI jobs (AI_WIZARD_PLAN "Metering" + guardrail 6).

Model (deliberately simple until Phase 6 billing lands):
- Each kind has a flat credit cost. The hold taken at job start IS the charge
  when the job succeeds (queued/running/awaiting_review/applied all count
  against the balance); failed/cancelled/expired jobs are refunded by zeroing
  `credits_held`. Actual-cost settlement against the dollar ledger is a
  Phase 6 refinement — the ledger already records true cost per call.
- The "1 free arc" is `ai_arc_generations_included`: wizard/story_arc jobs
  within the allowance hold 0 credits.
- Balance = `ai_credits_included` (entitlement; Stripe tops it up via
  overrides later) minus every non-refunded hold.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.entitlements import effective_entitlements
from app.models import AiJob, AiJobKind, AiJobStatus, Wedding

# Flat credit cost per job kind. Price credits with enough headroom that a
# retry is free to the platform, not just to the couple (plan: an arc costs
# roughly $0.30–$1.50 all-in).
CREDIT_COST: dict[str, int] = {
    AiJobKind.DETAILS: 1,  # two short text calls + a Places lookup — no images
    AiJobKind.STORY_ARC: 3,  # the TEXT run: draft + grounding pass, no art
    AiJobKind.GLYPH: 1,
    AiJobKind.GUESTS: 1,
}

# Images are the expensive call and, since 8.5b, an explicit click rather than
# part of a story run — so they're priced per image on top of the flat hold
# above (added to `credits_held`, hence refunded with it if the run is
# cancelled). See app/ai/images.py.
IMAGE_CREDIT_COST = 1

# Kinds that draw from the free-arc allowance.
_ARC_KINDS = (AiJobKind.STORY_ARC,)
# Statuses whose hold counts against the balance (everything not refunded).
_CHARGED_STATUSES = (
    AiJobStatus.QUEUED,
    AiJobStatus.RUNNING,
    AiJobStatus.AWAITING_REVIEW,
    AiJobStatus.APPLIED,
)


def arc_generations_used(db: Session, wedding: Wedding) -> int:
    return db.execute(
        select(func.count()).select_from(AiJob).where(
            AiJob.wedding_id == wedding.id,
            AiJob.kind.in_(_ARC_KINDS),
            AiJob.status.in_(_CHARGED_STATUSES),
        )
    ).scalar_one()


def credits_charged(db: Session, wedding: Wedding) -> int:
    return db.execute(
        select(func.coalesce(func.sum(AiJob.credits_held), 0)).where(
            AiJob.wedding_id == wedding.id,
            AiJob.status.in_(_CHARGED_STATUSES),
        )
    ).scalar_one()


def credits_remaining(db: Session, wedding: Wedding) -> int:
    ents = effective_entitlements(db, wedding)
    included = ents.get("ai_credits_included", 0)
    if not isinstance(included, int) or isinstance(included, bool):
        included = 0
    return included - credits_charged(db, wedding)


def compute_hold(db: Session, wedding: Wedding, kind: str) -> int:
    """The credits to hold for a new job of `kind`. Raises the friendly 403
    when the wedding can't cover it. 0 = this run rides the free allowance."""
    ents = effective_entitlements(db, wedding)
    if kind in _ARC_KINDS:
        free = ents.get("ai_arc_generations_included", 0)
        if isinstance(free, int) and not isinstance(free, bool):
            if arc_generations_used(db, wedding) < free:
                return 0
    cost = CREDIT_COST[kind]
    if credits_remaining(db, wedding) < cost:
        raise HTTPException(
            status_code=403,
            detail="You've used all this wedding's AI credits — contact us to upgrade",
        )
    return cost


def refund_hold(job: AiJob) -> None:
    """A failed/refused/cancelled/expired run never costs the couple."""
    job.credits_held = 0
