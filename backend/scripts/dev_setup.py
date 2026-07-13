"""One-command LOCAL dev database setup (SQLite only).

  python -m scripts.dev_setup

Creates the schema from the ORM models, seeds the Alex & Sam wedding (incl.
the default RSVP questions, via seed_wedding), and adds three demo guests (one per
invite tier), then prints invite URLs you can open immediately. Idempotent — safe
to re-run. To start fresh, delete the SQLite file (default `backend/dev.db`).

SAFETY: refuses to run unless `DATABASE_URL` is SQLite, so it can never seed demo
data into the production Supabase database.
"""
from __future__ import annotations

import sys

from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.entitlements import default_plan
from app.models import Guest, InviteTier, Plan, PlatformAdmin, Profile
from app.wedding_factory import ensure_owner_membership
from scripts.seed_wedding import seed

# Stable, friendly demo slugs (one per tier) so you can bookmark them.
# (slug, name, tier, greeting, party_members) — greeting is mandatory now, and the
# +1/family rows carry a pre-filled party so the RSVP opens with names ready.
DEMO_GUESTS = [
    ("solo-demo", "Demo Solo Guest", InviteTier.solo, "Demo", None),
    ("plusone-demo", "Demo Plus-One Guest", InviteTier.plus_one, "Sam & Alex",
     [{"kind": "adult", "name": "Alex"}]),
    ("family-demo", "Demo Family Guest", InviteTier.plus_family, "The Demos",
     [{"kind": "adult", "name": "Robin"}, {"kind": "child", "name": "Junior"}]),
]

FRONTEND_ORIGIN = "http://localhost:3000"


def main() -> None:
    settings = get_settings()
    if not settings.is_sqlite:
        sys.exit(
            "Refusing to run: DATABASE_URL is not SQLite "
            f"(db_backend={settings.db_backend}). dev_setup is for LOCAL dev only.\n"
            "Create backend/.env.local from .env.local.example to switch to SQLite."
        )

    print(f"Using {settings.database_url}")
    Base.metadata.create_all(engine)
    wedding = seed()

    db = SessionLocal()
    try:
        for slug, name, tier, greeting, party in DEMO_GUESTS:
            if db.query(Guest).filter_by(slug=slug).one_or_none() is None:
                db.add(Guest(wedding_id=wedding.id, slug=slug, name=name,
                             greeting_name=greeting, party_members=party,
                             invite_tier=tier, invited=True, seed_meta={"demo": True}))

        # Local identity plumbing: the bare dev token authenticates as sub "dev".
        # Give it a profile, platform-admin powers, and owner membership on the
        # template wedding so /dashboard and /{slug}/admin work out of the box.
        dev_email = (settings.admin_email_list[0] if settings.admin_email_list else "dev@local")
        if db.get(Profile, "dev") is None:
            db.add(Profile(user_id="dev", email=dev_email, display_name="Local dev"))
        if db.get(PlatformAdmin, "dev") is None:
            db.add(PlatformAdmin(user_id="dev", granted_by="bootstrap"))
        ensure_owner_membership(db, wedding, "dev", dev_email)

        # Local default plan with the AI wizard ON (production default is off —
        # AI_WIZARD_PLAN metering) so /create and the admin AI tab are testable
        # offline against the fake provider. Applies to every local wedding via
        # the default-plan fallback; existing default plans are left alone.
        if default_plan(db) is None:
            db.add(Plan(
                name="Local dev",
                description="Seeded by dev_setup — AI wizard enabled for offline dev",
                is_default=True,
                entitlements={
                    "ai_enabled": True,
                    "ai_credits_included": 50,
                    # 8.5d likeness: on locally so the consent + reference flow is
                    # exercisable offline (with AI_FAKE_IMAGES the painter draws a
                    # placeholder and no photo leaves the process). Production
                    # default stays FALSE — it ships ahead of its legal framing.
                    "ai_likeness_enabled": True,
                },
            ))
        db.commit()
    finally:
        db.close()

    print("\nLocal dev DB ready. Open these invite links (frontend on :3000):")
    for slug, name, tier, _greeting, _party in DEMO_GUESTS:
        print(f"  {tier.value:<12} {FRONTEND_ORIGIN}/i/{slug}   ({name})")
    print("\nReset anytime by deleting the SQLite file and re-running this.")


if __name__ == "__main__":
    main()
