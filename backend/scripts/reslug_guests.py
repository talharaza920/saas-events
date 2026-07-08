"""Re-mint every guest's invite slug with the hardened (128-bit) token.

Why this exists
---------------
The guest slug IS the only credential gating a guest's PII + RSVP. Slugs minted
before the hardening were 40-bit (`token_hex(5)`); this rewrites every existing
guest to a fresh 128-bit `secrets.token_urlsafe(16)` slug so the whole list is
enumeration-proof. Only the `guests.slug` column changes — names, RSVPs,
companions, answers and wishes are untouched (they're keyed by id, not slug).

IMPORTANT: re-slugging INVALIDATES every previously-shared link. Any guest whose
invite was already sent (`invite_sent = true`) must be re-sent their new link.
The script reports that count so you know the blast radius before committing.

Usage (against the same DATABASE_URL the app uses):
    python -m scripts.reslug_guests              # dry-run: report only
    python -m scripts.reslug_guests --commit      # apply
    python -m scripts.reslug_guests --commit --only-unsent   # skip already-sent
"""
from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db import SessionLocal
from app.guest_import import make_guest_slug
from app.models import Guest, Wedding
from app.seed_data import WEDDING_SLUG


def _unique_slug(existing: set[str]) -> str:
    """A fresh slug not colliding with any slug seen this run (or in the DB)."""
    for _ in range(10):
        slug = make_guest_slug()
        if slug not in existing:
            return slug
    raise SystemExit("Could not generate a unique slug — retry.")


def reslug(*, commit: bool, only_unsent: bool, wedding_slug: str) -> None:
    db = SessionLocal()
    try:
        wedding = db.query(Wedding).filter_by(slug=wedding_slug).one_or_none()
        if wedding is None:
            raise SystemExit(f"No wedding '{wedding_slug}' found.")

        guests = list(
            db.execute(select(Guest).where(Guest.wedding_id == wedding.id)).scalars()
        )
        # Reserve every current slug so a new one never collides with one we haven't
        # rewritten yet (the unique index would reject it mid-loop otherwise).
        taken: set[str] = {g.slug for g in guests}

        targets = [g for g in guests if not (only_unsent and g.invite_sent)]
        already_sent = sum(1 for g in targets if g.invite_sent)

        for g in targets:
            new = _unique_slug(taken)
            taken.discard(g.slug)
            taken.add(new)
            if commit:
                g.slug = new

        if commit:
            db.commit()

        verb = "Re-slugged" if commit else "Would re-slug (dry-run)"
        print(
            f"{verb} {len(targets)} of {len(guests)} guest(s) for '{wedding.slug}'."
            f" {already_sent} of them already had an invite sent — RE-SEND those links."
        )
        if not commit:
            print("Dry-run only. Re-run with --commit to apply.")
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Re-mint guest invite slugs (128-bit).")
    ap.add_argument("--commit", action="store_true", help="apply (default is dry-run)")
    ap.add_argument(
        "--only-unsent",
        action="store_true",
        help="skip guests whose invite was already sent (preserve their live links)",
    )
    ap.add_argument("--wedding-slug", default=WEDDING_SLUG)
    args = ap.parse_args()
    reslug(commit=args.commit, only_unsent=args.only_unsent, wedding_slug=args.wedding_slug)
