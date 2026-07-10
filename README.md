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
Phases 0–5 of `docs/SAAS_PLAN.md` (identity/tenancy, self-serve creation +
approval, co-admins, platform console, plans & entitlements) are built and
tested locally; Phase 8 (AI creation wizard, `docs/AI_WIZARD_PLAN.md`) is in
progress. Cloud infra (Supabase/Vercel/Resend/Sentry) is not provisioned yet —
everything below runs fully offline. `docs/PROGRESS.md` is the source of truth.

## Run locally (Windows / PowerShell)

Two dev servers: FastAPI backend on :8000, Next.js frontend on :3000. Local
runs use SQLite — no Supabase account needed.

**One-time setup:**

```powershell
# Backend deps (creates backend/.venv)
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt

# Point the backend at local SQLite (gitignored; delete it later to hit Supabase)
copy .env.local.example .env.local

# Create the schema + seed the template wedding and demo guests
# (solo-demo / plusone-demo / family-demo). Reset any time: delete dev.db.
.venv\Scripts\python.exe -m scripts.dev_setup

# Frontend deps (npm — pnpm is broken on this box)
cd ..\frontend
npm install
```

Then set the same dev token in both env files so the dashboard logs you in
without Supabase: `DEV_ADMIN_TOKEN=<anything>` in `backend/.env.local` and
`NEXT_PUBLIC_DEV_ADMIN_TOKEN=<the same>` in `frontend/.env.local`. The bare
token = platform admin; `<token>:<email>` simulates an ordinary user.

**Every session (two terminals):**

```powershell
# Terminal 1 — backend (from backend/)
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# Terminal 2 — frontend (from frontend/)
npx next dev
```

Open http://localhost:3000/dashboard (admin), or a demo invite at
http://localhost:3000/i/solo-demo. API health: http://localhost:8000/health
(reports `"db": "sqlite"` locally).

**Verify:**

```powershell
# Backend tests (offline, in-memory SQLite) — from backend/
.venv\Scripts\python.exe -m pytest -q

# Frontend checks — from frontend/
npx tsc --noEmit; npx eslint .

# E2E smoke (needs both dev servers + a dev_setup-seeded DB) — from frontend/
node scripts/smoke-e2e.mjs
```

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
