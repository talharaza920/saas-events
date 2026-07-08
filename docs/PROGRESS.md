# PROGRESS — saas-events platform

The resumable source of truth for platform work. Phases are defined in
`SAAS_PLAN.md`. The predecessor build's milestone history (M1–M14) lives in
that private repo, not here.

_Last updated: 2026-07-08 (Phase 0 fork + scrub + hardening)._

## Phase 0 — Fork, personal-data scrub, security hardening

**Status: nearly complete — remaining items need the fresh infrastructure.**

### 0.1 Fork & fresh infrastructure
- [x] Tree copied from the predecessor repo, excluding reference material,
  env/secret files, `dev.db`, and all personal images (2026-07-08).
- [x] Fresh squashed git history — no personal data in any commit; pushed to
  GitHub (private).
- [ ] New Supabase project (nothing provisioned yet).
- [ ] New Vercel projects (frontend + backend) + env vars; `hnd1` region
  pinning is already in both `vercel.json`s.

### 0.2 Personal-data & branding scrub — DONE 2026-07-08
- [x] `backend/app/seed_data.py` → neutral "Alex & Sam" starter template
  (slug `alex-and-sam`; text-only story beats — owners upload their own art).
- [x] Backend tests/fixtures/docstrings neutralized; `admin_emails` default
  now empty (fail-closed).
- [x] Frontend: mascot generalized (badge component renamed to `MascotBadge`; the built-in
  cat glyph stays as neutral default art, per RT's 2026-07-08 decision);
  render fallbacks, admin helper texts, and metadata neutralized; theme
  template renamed **"Ever after"**; dev-script paths de-personalized.
- [x] Docs: README/CLAUDE rewritten; fresh LEARNINGS (curated carry-overs) and
  PROGRESS; PLAN/DESIGN/SAAS_PLAN/REFERENCE_RESEARCH de-personalized.
- [x] `openapi.json` + `frontend/types/api.ts` regenerated post-scrub.
- [x] Final case-insensitive sweep: zero personal hits (term list deliberately
  lives only in the predecessor repo's SAAS_PLAN).

### 0.3 Security hardening (2026-07-08 review) — code items DONE
- [x] P1-1 dev-token bypass: refused whenever `VERCEL` is set; constant-time
  compare (`app/auth.py`).
- [x] P1-3 guest payload allowlist: `event_details`/`content` keys filtered in
  `routers/invite.py` — `capacity` and any owner-only key never reach guests.
- [x] P1-4 bounded RSVP answers: known shapes only, 2 000-char text cap,
  choices/list caps, duplicate `question_id` rejection (`app/schemas.py`).
- [x] P2-5 security headers (CSP, nosniff, Referrer-Policy, frame denial) in
  `next.config.ts`.
- [x] P2-6 `next/image` pinned to the exact Supabase host (derived from
  `NEXT_PUBLIC_SUPABASE_URL`; no more `*.supabase.co` wildcard).
- [x] P2-7 guest contacts masked on `GET /api/i/{slug}`; a posted masked value
  means "unchanged".
- [x] Tests: `tests/test_security_hardening.py` + masking coverage in
  `test_invite_api.py`. Suite: **157 passed**; `tsc`/`eslint`/`next build`
  clean.
- [ ] P1-2 rate limiting via Vercel WAF (dashboard work — when the Vercel
  projects exist).
- [ ] P2-8 keep Next.js on the latest patch (recurring chore).
- [ ] P3 backlog: trim `/health`, Content-Length check before reading uploads,
  admin-auth failure logging, drop `x-upsert` on Storage uploads.
- Note: the ⚠ cherry-picks back to the live predecessor deployment are tracked
  in THAT repo, not here.

### Exit criteria (SAAS_PLAN.md)
- [x] Grep sweep zero; P1+P2 code hardening merged; tests green.
- [ ] Boots against a fresh Supabase with the neutral seeded wedding (blocked
  on 0.1 infrastructure).

## Phase 1 — Identity & tenancy core
Not started.

## Phase 2+
Not started — see `SAAS_PLAN.md`.

## Decisions log
- **2026-07-08 (RT):** mascot generalized (not stripped) as an optional theme
  feature with the built-in cat glyph as neutral default art; working name
  **saas-events**; repo GitHub (private).
- **Open (owed by RT):** final platform name + domain; auth breadth beyond
  Google + email/password (Phase 1); publish-rights default (Phase 3);
  terms/privacy approach (before Phase 2 goes public).
