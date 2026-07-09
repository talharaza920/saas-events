# PROGRESS — saas-events platform

The resumable source of truth for platform work. Phases are defined in
`SAAS_PLAN.md`. The predecessor build's milestone history (M1–M14) lives in
that private repo, not here.

_Last updated: 2026-07-09 (Phases 1–5 built & tested locally; review P0 fixes
and P1 items 5/6/8/9/10 landed — see `REVIEW_BACKLOG.md`)._

## Where things stand (one paragraph)

Phases 1–5 are **code-complete and tested on local SQLite**: accounts +
memberships gate every admin endpoint (wedding-scoped
`/api/w/{slug}/admin/*`), self-serve creation/approval/publish works
end-to-end, co-admin invites/transfer/revoke work, the platform console
(`/platform`) runs the whole lifecycle, and plans/entitlements are enforced
server-side. **Nothing is provisioned in the cloud yet** — Supabase (auth +
Postgres + storage), Vercel, WAF rate limits, a real email provider, and
Sentry are the remaining infrastructure work, deliberately deferred until RT
creates those accounts. A full-codebase review (2026-07-09) found no
cross-tenant hole; its prioritised backlog lives in **`REVIEW_BACKLOG.md`**
and the four P0 items (N+1 eager loading, introspection cache, Resend email
seam, guest-API rate limiting) are done. Suite: **232 pytest** (offline) +
**20/20 E2E smoke** checks (`frontend/scripts/smoke-e2e.mjs` against local dev
servers); `tsc`/`eslint`/`next build` clean.

## Phase 0 — Fork, personal-data scrub, security hardening

**Status: code complete (2026-07-08). Remaining items = fresh infrastructure.**

- [x] Tree copied, scrubbed, squashed history, pushed (private GitHub).
- [x] P1/P2 security hardening merged (dev-token guards, guest payload
  allowlist, bounded RSVP answers, CSP/nosniff/referrer headers, pinned image
  host, contact masking). Tests green.
- [ ] New Supabase project + new Vercel projects + env vars (**blocked on RT
  creating the accounts** — everything below runs locally meanwhile).
- [ ] P1-2 rate limiting via Vercel WAF (dashboard work, when Vercel exists).
- [ ] P2-8 Next.js patch chore (recurring).
- [ ] P3 backlog: trim `/health`, Content-Length pre-check on uploads,
  admin-auth failure logging, drop `x-upsert` on Storage uploads.

## Phase 1 — Identity & tenancy core — DONE (local) 2026-07-09

- [x] Schema (`e0a1b2c3d4e5` migration, RLS-enabled): `profiles`,
  `wedding_members` (owner/admin × invited/active/revoked + hashed invite
  tokens), `platform_admins`, `audit_log`, `platform_settings`;
  `weddings.published` + `weddings.settings` (+ backfill for active rows).
- [x] Auth (`app/auth.py`): any **verified** user is a principal (membership
  does the gating); unverified email → 403. Local dev token grew a
  `<token>:<email>` multi-user form (see LEARNINGS).
- [x] Authz seams (`app/authz.py`): `require_wedding(role, edit)` resolves the
  tenant from the path — non-member **404**, under-role **403**, suspended =
  read-only, archived hidden; `require_platform_admin` (+ `ADMIN_EMAILS`
  bootstrap fallback); lazy profile upsert (no DB trigger needed).
- [x] Admin API moved to `/api/w/{wedding_slug}/admin/*`; `/api/me` +
  `/api/me/weddings`; audit-log helper (`app/audit_log.py`) wired through
  mutating endpoints.
- [x] Frontend: `/{weddingSlug}/admin` dashboard (module-level
  `setAdminWedding`), post-login `/dashboard` (weddings + role chips),
  `/admin` → redirect. Reserved-slug blocklist (`app/slugs.py`).
- [ ] Supabase Auth config itself (Google + email/password + verification
  emails) — needs the Supabase project. The backend already enforces
  verified-email and the frontend sign-in flow is unchanged from Phase 0.

## Phase 2 — Self-serve creation & approval — DONE (local) 2026-07-09

- [x] `POST /api/weddings` from the neutral template (`app/wedding_factory.py`
  — personalises names, seeds questions/arc, grants owner membership, status
  `draft`); live `GET /api/weddings/slug-check`; `/create` wizard page.
- [x] Approval workflow (`app/approval.py`): submit → rules evaluate →
  auto-approve (when on) or manual queue; rule trace stored in audit + shown
  in the console. Rules blob in `platform_settings` (editable from
  `/platform` → Rules): auto_approve, account age, weddings/account, guest
  count, banned words.
- [x] Approve / deny(+reason) / suspend / reinstate endpoints + emails (dev
  outbox). Suspension: guests get the same neutral 404 as "never existed";
  dashboard goes read-only with a banner.
- [x] **Publish** independent of approval (owner-only by default; owner can
  grant to admins via `settings.admins_can_publish`). Guests resolve only
  active AND published weddings.
- [x] Cold-start demo verified live: new (dev) user → create → submit →
  approve → publish → guest opens invite and RSVPs.
- [ ] Terms/privacy placeholder pages (owed before public launch, per plan).

## Phase 3 — Co-admins & team management — DONE (local) 2026-07-09

- [x] Members tab (dashboard "Team") + API: invite by email (single-use,
  sha256-hashed, 7-day token; accept path returned + emailed), accept requires
  the matching signed-in email, role change, revoke (immediate — checked
  per-request), two-step ownership transfer, last-owner protection.
- [x] Owner soft-delete → `archived` (unpublished, hidden); platform admin
  reinstates within the undo window. (Hard purge after 30 days = an ops job
  once real infra exists.)
- [x] Two-account flows covered in `tests/test_members_api.py`.

## Phase 4 — Platform console — DONE (local) 2026-07-09

- [x] `/platform` (platform-admin only) with tabs: **Weddings** (status,
  owner, member/guest counts, plan selector, approve/suspend/reinstate,
  view-as link), **Approvals** (rule-trace chips, approve / deny-with-reason),
  **Users** (weddings per account, disable/enable), **Plans**, **Rules**
  (auto-approval editor), **Ops** (status tiles + audit tail).
- [x] API `/api/platform/*`: weddings, approvals, settings, users (+disable),
  platform-admin grant/revoke, stats, audit.
- [ ] "View as" is currently just platform access to the wedding dashboard —
  a visual banner + per-view audit entry is still to add.

## Phase 5 — Plans & entitlements — DONE (local) 2026-07-09

- [x] `plans` + `wedding_plans` (overrides, `valid_until`) tables;
  `app/entitlements.py` merge: defaults ∪ default-plan ∪ assigned-plan ∪
  overrides.
- [x] Enforcement on **create only** (never retroactively destructive):
  guests (create + import), custom questions, story arcs, member invites;
  feature toggles: export / import / wishes (guest guestbook 404s neutrally);
  `max_weddings_per_account` at creation.
- [x] Entitlements block surfaced in `/api/w/{slug}/admin/me`; friendly 403
  detail with a dormant "contact us" upgrade hint. Plans editor + per-wedding
  assignment in the console.
- [ ] `max_storage_mb` is defined but not yet metered (needs Supabase Storage
  usage accounting — per-upload caps exist from Phase 0).

## Code review & hardening — P0 DONE 2026-07-09

Full-repo review (security / multi-tenancy / scaling / best practices);
findings + priorities in **`REVIEW_BACKLOG.md`** (work it top-down, tick items
there).

- [x] P0-1 N+1 eager loading on `/guests`, `/responses`, `/summary`, export,
  wishes list (`selectinload` chains + query-count guard tests).
- [x] P0-2 60s introspection cache in `app/auth.py` (token-hash keyed, success
  only; membership/disabled checks still per-request).
- [x] P0-3 Resend behind `RESEND_API_KEY` + `EMAIL_FROM` in `app/emailer.py`
  (outbox stays the fallback; never raises). Provider account still owed (infra).
- [x] P0-4 per-IP guest-API rate limiting (`app/ratelimit.py`: reads 120/min,
  writes 30/min; prod-on by default, `RATE_LIMIT_ENABLED` overrides). Vercel
  WAF stays the durable outer layer (P1-2).
- [x] P1-5 platform root: `/api/landing` (earliest-wedding leak) removed;
  static platform landing at `/` (2026-07-09).
- [x] P1-6 per-wedding phone region (`settings.phone_region` → all
  `normalize_phone` call sites; SG fallback). Owner UI knob pending a settings
  panel.
- [x] P1-8 platform console: grouped-count queries (query-count guard tests) +
  `limit`/`offset` on weddings/users/approvals.
- [x] P1-9 archived-wedding purge: `archived_at` (migration `f1a2b3c4d5e6`),
  `app/purge.py` (30-day window), console button + `CRON_SECRET`-gated
  `/api/internal/cron/purge-archived` for Vercel cron.
- [x] P1-10 observability (backend): `app/obs.py` (logging, logfmt `log_event`,
  Sentry behind `SENTRY_DSN`); `/health` pings the DB (`db_ok`).
- [ ] Remaining P1 (7: storage metering) + P2/P3 items — see
  `REVIEW_BACKLOG.md`.

## Phase 6 (billing) / Phase 7 (growth) — not started (by design)

## Test & verification status (2026-07-09)

- `pytest`: **248 passed** (offline, in-memory SQLite) — includes the
  authz matrix, lifecycle, members, platform console, entitlements, and the
  pre-platform suites migrated to wedding-scoped paths. Cross-tenant
  negatives throughout (`test_identity_authz.py` is the status-code spec).
  Review-P0 additions: query-count guards (`test_query_efficiency.py`),
  introspection cache, rate limiting, emailer seam.
- Frontend: `tsc --noEmit`, `eslint .`, `next build` clean.
- E2E smoke (`node scripts/smoke-e2e.mjs`, needs both dev servers +
  `scripts.dev_setup`): **20/20** — three tier invites, solo tier-invisibility,
  full family RSVP persisted, landing, dashboard, wedding admin (lifecycle
  strip, Team tab), platform console.

## Infrastructure TODO (when RT provisions accounts)

1. Supabase project → run `alembic upgrade head`, configure Google OAuth +
   email/password with verification, storage bucket, env vars; seed RT's
   platform-admin row.
2. Vercel frontend + backend projects (hnd1), env vars, WAF rate rules (P1-2);
   cron entry hitting `/api/internal/cron/purge-archived` daily with
   `Authorization: Bearer $CRON_SECRET` (backend code path is in).
3. Email provider (Resend) → code path is in (`RESEND_API_KEY` + `EMAIL_FROM`
   env vars); create the account + verify the sending domain.
4. Sentry: create the project(s) and set `SENTRY_DSN` (backend init is in);
   add `@sentry/nextjs` to the frontend; uptime check on `/health` (now pings
   the DB — alert on `status: degraded`).
5. Staging Supabase + Vercel preview envs; PITR/backups on from first real user.

## Decisions log
- **2026-07-09:** all phases built & tested locally first (RT: provision
  Supabase/Vercel later); email = dev outbox until a provider exists; dev
  token composite form for local multi-user; authz status-code contract
  (404 non-member / 403 under-role) pinned in tests.
- **2026-07-08 (RT):** mascot generalized (not stripped) as an optional theme
  feature with the built-in cat glyph as neutral default art; working name
  **saas-events**; repo GitHub (private).
- **Open (owed by RT):** final platform name + domain; auth breadth beyond
  Google + email/password (Phase 1); publish-rights default is owner-only
  (confirm, Phase 3); terms/privacy approach (before Phase 2 goes public).
