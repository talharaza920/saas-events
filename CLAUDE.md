# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## What this is

**saas-events** (working name) — a multi-tenant wedding-RSVP **platform**,
forked 2026-07-08 from a private single-wedding build. Couples will sign up,
create a wedding from a neutral template ("Alex & Sam" / the "Ever after"
theme), and manage guests/RSVPs from a dashboard. The fork is scrubbed: this
repo must contain **no** personal data from the original wedding, ever.

**`docs/SAAS_PLAN.md` is the governing plan.** Read it first, then
`docs/PROGRESS.md` for where work stands. `docs/PLAN.md` documents the
inherited architecture (data model, invite tiers, API); `docs/DESIGN.md` the
theme/token system; `LEARNINGS.md` the carried-over gotchas.

## Non-obvious project rules

- **Multi-tenant is the product.** A root `weddings` tenant table with
  `wedding_id` on every table; page content + theme stored as **data** on the
  wedding (seeded from `backend/app/seed_data.py` + theme defaults — never
  hardcode copy/colors in components); images in Supabase Storage per wedding;
  guest links `/i/{globally-unique slug}` already carry the tenant.
- **The invite-tier mechanism is sacred.** Each guest slug maps server-side to
  a tier (`solo` / `plus_one` / `plus_family`). The RSVP renders **identical
  chrome** for everyone and silently omits +1/kids fields for lower tiers — a
  `solo` guest must never be able to tell a +1 was an option. Never expose the
  tier client-side or make it editable via the URL.
- **Cross-tenant tests are the #1 SaaS failure mode.** Every new endpoint
  ships with "wrong-tenant 404" and "no-membership 401/403" tests.
- **No personal data.** The predecessor wedding's names, venue, dates, guest
  data, and artwork must never enter this repo (including via test fixtures or
  docs). Seed/demo content is "Alex & Sam" placeholders.
- Guests authenticate by **signed link only** — guests never log in. Admin
  auth is Supabase (Google) today, moving to accounts + memberships in
  SAAS_PLAN Phase 1.
- **Additive-only migrations**, applied to Supabase as part of every deploy.

## Conventions (from the `rt-code-preferences` skill — re-read it each session)

- **Stack:** Next.js (App Router) + TypeScript + **MUI**; **FastAPI** (Python)
  backend; **Supabase** (Postgres + auth); deploy on Vercel via the
  `rt-basic-app-deploy` skill (only when RT asks).
- **Config-driven theme is non-negotiable.** All colors/typography/spacing
  live in `frontend/theme/defaultThemeConfig.ts` (→ MUI theme via
  `buildTheme.ts`); per-wedding `theme_tokens` deep-merge over it. Components
  reference tokens (`sx={{ color: 'primary.main' }}`); never hard-code a
  hex/px/font.
- **Open-source components first, custom last.** Compose MUI before building
  anything bespoke; if you must go custom, note why in `LEARNINGS.md`.
- **Type contract:** generate TS types from FastAPI's `/openapi.json` into
  `frontend/types/api.ts` so frontend/backend stay in sync.
- **Definition of done per phase:** library/theme rules honored, tests written
  & passing, UI browser-verified, `PROGRESS.md` + `LEARNINGS.md` updated,
  committed & pushed, tagged release with notes once tests pass.
- Package manager **npm** (pnpm is broken on this box); ESLint + Prettier
  before "done"; `.env.local` gitignored with a names-only `.env.example`.

## Environment notes

- Windows / PowerShell. Use `python -m pip` (bare `pip` isn't on PATH). Set
  `PYTHONIOENCODING=utf-8` for scripts that print non-ASCII.

## Commands

Run from the repo root. The backend venv lives at `backend/.venv` (create with
`python -m venv .venv` + `python -m pip install -r requirements.txt
-r requirements-dev.txt` if missing); use that interpreter.

**Local vs production = `DATABASE_URL`.** `.env.local` (gitignored) overrides
`.env` when present: create it (`cp backend/.env.local.example backend/.env.local`)
for **local SQLite** (`sqlite:///./dev.db`); delete it to hit **Supabase**.
`/health` reports `"db": sqlite|postgres`.

**Backend (FastAPI, from `backend/`):**
- Test: `.venv/Scripts/python.exe -m pytest -q` (offline — in-memory SQLite).
- Local DB setup: `.venv/Scripts/python.exe -m scripts.dev_setup` (SQLite only —
  creates schema + seeds the template wedding + demo guests `solo-demo`/
  `plusone-demo`/`family-demo`; reset by deleting `dev.db`).
- Run: `.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000`.
- Migrate (Supabase): `.venv/Scripts/python.exe -m alembic upgrade head` (RLS is
  Postgres-only and auto-skipped on SQLite, so the migration runs on both).
- Seed / import (Supabase): `scripts/seed_wedding.py`, then
  `scripts/import_guests.py --file <xlsx> --wedding-slug alex-and-sam`.
- Regenerate OpenAPI: `python -c "import json; from app.main import app;
  open('openapi.json','w',encoding='utf-8').write(json.dumps(app.openapi()))"`.

**Frontend (Next.js, from `frontend/`, npm):**
- Dev: `npx next dev` · Build: `npx next build` · Serve build: `npx next start`.
- Typecheck: `npx tsc --noEmit` · Lint: `npx eslint .`.
- Regenerate API types (after backend schema changes):
  `npx openapi-typescript ../backend/openapi.json -o types/api.ts`.
- Guest invite route: `/i/[guestSlug]` — needs the backend running
  (`NEXT_PUBLIC_API_URL` / `API_BASE`, default `http://localhost:8000`).
- Admin route: `/admin` (owner-only). **Local:** set the same token in
  `backend/.env.local` (`DEV_ADMIN_TOKEN`) and `frontend/.env.local`
  (`NEXT_PUBLIC_DEV_ADMIN_TOKEN`) — the dashboard then skips Google sign-in.
  **Production:** Supabase auth restricted to `ADMIN_EMAILS`; the dev token is
  refused when `ENVIRONMENT=production`. API lives under `/api/admin/*`
  (auth header: `Authorization: Bearer <token>`).
