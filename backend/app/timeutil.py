"""Timezone-aware UTC helpers (REVIEW_BACKLOG P2-17).

The app stores UTC everywhere, but the two backends hand it back differently:
Postgres (timestamptz) returns tz-AWARE datetimes, SQLite returns NAIVE ones.
Every comparison between a stored timestamp and "now" must go through these
helpers so aware/naive never mix — the scattered per-module `_naive_utc` /
tzinfo-branching copies this replaces each solved it slightly differently.

Convention: application code works in tz-aware UTC (`utcnow()`); anything read
from the DB is normalized with `as_utc()` before arithmetic; anything BOUND
into a SQL comparison goes through `db_bind_utc()` (SQLite compares stored
naive strings, so an aware parameter would mis-compare there).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session


def utcnow() -> datetime:
    """The current moment, tz-aware UTC."""
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """Normalize a stored timestamp to tz-aware UTC. Naive input (SQLite) is
    UTC by construction — the app never writes local times."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def db_bind_utc(db: Session, dt: datetime) -> datetime:
    """The bind-parameter form of an aware-UTC datetime for this session's
    dialect: naive for SQLite (which stores and string-compares naive values),
    aware everywhere else (Postgres timestamptz)."""
    if db.get_bind().dialect.name == "sqlite":
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
