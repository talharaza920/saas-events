# LEARNINGS

Locked decisions and hard-won gotchas for **saas-events**. Newest first.
Entries below the "Carried over" line were curated from the predecessor
single-wedding build (full history lives in that private repo); everything
above it is new to the platform.

## 2026-07-08 — Phase 0 fork: scrub before the first push
**Context:** This repo was forked from a private single-wedding build whose
seed data, tests, docs, and assets were full of personal facts.
**Lesson:** The scrub happened BEFORE anything was pushed, and history was
squashed so no personal data exists in any commit. Keep it that way: no
personal names/venues/dates/guest data in fixtures, seeds, docs, or comments.
The case-insensitive sweep list lives in the predecessor repo's SAAS_PLAN
(don't copy the list here — it is itself personal data).

---

_Carried over from the predecessor build (condensed):_

## Vercel functions default to US East; pin `regions` next to Supabase
Both `vercel.json`s set `"regions": ["hnd1"]` because Supabase is in
ap-northeast-1 (Tokyo) and `NullPool` opens a fresh Postgres connection per
request — an un-pinned iad1 function paid ~5 US↔Tokyo round trips per request
(~2.7s warm admin calls; ~0.55s after pinning). Verify with
`curl -sD - <url> | grep -i x-vercel-id` → expect `…::hnd1::…`. Remaining
first-hit slowness is Python cold start, inherent to Python-on-Vercel.

## A new migration MUST be applied to Supabase as part of deploy
Pushing backend code does NOT migrate Supabase; a DB one revision behind 500s
every DB-backed route (and the 500 strips CORS headers, masquerading as a CORS
bug). Also: `backend/.env.local` overrides `.env`, so a bare `alembic upgrade
head` migrates local `dev.db` — rename `.env.local` aside to target Supabase,
verify with `alembic current`. Additive nullable columns need no redeploy.

## N+1 lazy-loads are invisible on SQLite and brutal on Supabase
Aggregate/admin endpoints that walk relationships in Python loops must
eager-load (`selectinload`). Local SQLite makes each lazy query sub-ms;
in prod each is a network hop from the serverless function to the pooler
(seconds, or a function timeout). Also: a refetch-on-deps React effect needs
its own loading reset + `.catch`, or a slow backend reads as a frozen UI.

## Supabase pooler URL gotchas (region, driver, RLS owner-bypass)
The pooler template leaves a literal `<region>` placeholder (wrong region →
`Tenant or user not found`; right region + bad password → `password
authentication failed`). `DATABASE_URL` must use `postgresql+psycopg://`
(plain `postgresql://` loads psycopg2, which isn't installed). RLS stance:
`ENABLE ROW LEVEL SECURITY` on every table with no policies — the backend
connects as the `postgres` owner (bypasses RLS), `anon` is denied everything;
never `FORCE` (locks the owner out too). The Supabase advisor's
`rls_disabled_in_public` usually flags `alembic_version` — enable RLS on it or
unexpose `public` from PostgREST.

## Guest slugs are credentials: 128-bit, enumeration-proof
The guest slug is the ONLY thing gating a guest's PII + RSVP. Mint with
`secrets.token_urlsafe(16)` (128 bits) — an early `token_hex(5)` (40 bits) was
brute-forceable. `scripts/reslug_guests.py` re-mints existing guests (dry-run
by default; re-slugging invalidates already-shared links — it reports the
`invite_sent` blast radius).

## Exported spreadsheets need formula-injection escaping
Guest-supplied text flows into `export.xlsx`; values starting `= + - @` (or
tab/CR) execute as formulas in Excel. `export_import.escape_formula()`
prefixes `'`; every data cell goes through it. React's default escaping covers
the web render — and keep `RichText.tsx` away from `dangerouslySetInnerHTML`.

## Config-driven theme + content-as-data
All colors/typography/spacing live in `frontend/theme/defaultThemeConfig.ts`;
per-wedding `theme_tokens` deep-merge over it. All copy lives on the wedding
row (seeded from `backend/app/seed_data.py`). Components never hard-code a
hex/px/font or a line of guest-facing copy — that's what makes multi-tenant
theming possible at all.

## Invite tiers must be invisible in the UI
Tier (`solo`/`plus_one`/`plus_family`) is encoded server-side against the
unguessable slug. The RSVP renders identical chrome and simply omits +1/kids
fields — never label or hint at the tier client-side.

## Windows dev box gotchas
- Use **npm**, not pnpm (`corepack prepare pnpm` needs admin and fails EPERM).
- Never run two npm installs in the same `node_modules` at once.
- Stray `package.json`/`package-lock.json` files in the user-profile directory
  break Next's monorepo-root detection (`next.config.ts` pins
  `outputFileTracingRoot` for this).
- Bare `pip` isn't on PATH — `python -m pip`. Set `PYTHONIOENCODING=utf-8`
  when scripts print non-ASCII (cp1252 crashes).

## Circular wordmark centring is a cross-browser SVG trap
`<textPath startOffset="50%" text-anchor="middle">` on a full-circle path is
the only combination that centres reliably; measuring/offsetting glyphs
manually drifts per browser. See `components/invite/brand/Wordmark.tsx`.
