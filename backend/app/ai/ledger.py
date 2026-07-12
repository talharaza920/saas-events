"""Append-only AiUsageLedger writer — one row per provider call.

Same discipline as audit_log: rows are inserted, never updated, and survive a
wedding purge with their pointers nulled. The caller owns the transaction
(the pipeline commits a step's job-state change and its ledger rows
together); this only stages the row.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.pricing import cost_usd_micros
from app.ai.types import Usage
from app.models import AiUsageLedger
from app.timeutil import db_bind_utc, utcnow


def record_usage(
    db: Session,
    *,
    wedding_id: uuid.UUID,
    job_id: uuid.UUID | None,
    kind: str,  # transcribe | extract | draft | ground | glyph | image
    usage: Usage,
    credits: int = 0,
    images: int | None = None,
) -> AiUsageLedger:
    row = AiUsageLedger(
        wedding_id=wedding_id,
        job_id=job_id,
        provider=usage.provider,
        model=usage.model,
        kind=kind,
        credits=credits,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        images=images,
        cost_usd_micros=cost_usd_micros(usage, images=images),
        provider_request_id=usage.request_id,
    )
    db.add(row)
    return row


def cost_usd_today(db: Session) -> float:
    """Platform-wide spend since UTC midnight — the input to the daily cost
    ceiling (guardrail 6). Micros are summed in SQL (the created_at index
    carries it); the bound goes through db_bind_utc so SQLite's naive
    storage compares correctly."""
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    micros = db.execute(
        select(func.coalesce(func.sum(AiUsageLedger.cost_usd_micros), 0)).where(
            AiUsageLedger.created_at >= db_bind_utc(db, start)
        )
    ).scalar_one()
    return micros / 1_000_000
