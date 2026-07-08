# saas-events — multi-tenant wedding RSVP platform

A self-serve platform where couples create a personalized wedding-invitation
site with per-guest RSVP links, a story-driven single-page invite, and an
admin dashboard. Working name **saas-events**; forked from a private
single-wedding build and being generalized into a product.

## What a wedding gets
- A personalized, single-page invitation greeting each guest by name at an
  unguessable link (`/i/{guest-slug}`).
- **RSVP** with name-gating, custom questions, dietary capture, and per-guest
  **+1 / +1 & kids** allowances driven invisibly by the invite link — a `solo`
  guest never learns a +1 was an option.
- An **admin dashboard** to edit all content/theme as data, manage the guest
  list, generate links, build custom questions, and track responses (dietary
  summary, import/export).
- An optional **mascot/story theme**: scrolling comic-style story beats with
  owner-uploaded art, themeable tokens, and a default **"Ever after"** template
  seeded as placeholder content ("Alex & Sam").

## Status
**Phase 0** of `docs/SAAS_PLAN.md` — fork scrubbed of personal data and being
hardened; identity/tenancy (Phase 1) and self-serve signup (Phase 2) follow.

## Start here
- `docs/SAAS_PLAN.md` — the governing plan (phases, roles, entitlements).
- `docs/PROGRESS.md` — phase status; the resumable source of truth.
- `docs/PLAN.md` — architecture, data model, API surface (inherited design).
- `docs/DESIGN.md` — the default theme template & token system.
- `LEARNINGS.md` — gotchas carried over from the predecessor build.
- `CLAUDE.md` — guidance for AI agents working in this repo.

## Stack
Next.js (App Router) + TypeScript + MUI · FastAPI (Python) · Supabase
(Postgres + Auth + Storage) · Vercel. See `CLAUDE.md` for commands.
