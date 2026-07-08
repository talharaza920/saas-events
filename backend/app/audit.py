"""RSVP audit stamping — records, on every RSVP write, WHEN it last changed, from
WHICH surface, and (for owner-side changes) WHO.

`Rsvp.responded_at` stays the FIRST-reply time (set once on insert by the DB
default). `updated_at` is bumped on every change; `last_source`/`last_actor`
record the latest write; `first_source` is stamped once and never overwritten, so
you can tell whether a response originated with the guest or was entered by the
couple. The actor email is only meaningful for owner/import writes — a guest's own
submission has no admin identity, so `last_actor` stays NULL there.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.models import Rsvp

# Where an RSVP write originated. Stored as a short string (not a DB enum) so adding
# a future source needs no migration.
SOURCE_GUEST = "guest"  # the guest's own signed invite link
SOURCE_ADMIN = "admin"  # the owner, via /admin
SOURCE_IMPORT = "import"  # spreadsheet import
SOURCES = {SOURCE_GUEST, SOURCE_ADMIN, SOURCE_IMPORT}


def stamp_rsvp(rsvp: Rsvp, source: str, *, actor: str | None = None) -> None:
    """Record provenance of the current write on `rsvp`. Call just before commit.

    `source` is one of SOURCES; `actor` is the admin email for owner/import writes
    (leave None for a guest's self-serve submission). Sets `first_source` only the
    first time the row is stamped (when it's still NULL), so it preserves where the
    very first reply came from across later edits.
    """
    rsvp.updated_at = datetime.now(timezone.utc)
    rsvp.last_source = source
    rsvp.last_actor = actor
    if rsvp.first_source is None:
        rsvp.first_source = source
