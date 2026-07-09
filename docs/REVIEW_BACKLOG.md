# REVIEW_BACKLOG — full-codebase review findings (2026-07-09)

Prioritised backlog from the whole-repo review (security, multi-tenancy,
scaling, best practices) of the Phases 0–5 build. Work through it top-down,
ticking items as they land; move anything that grows real scope into
`SAAS_PLAN.md`. Effort: **S** < ½ day · **M** ½–2 days · **L** 3+ days.

**Verdict at review time:** tenancy/authz design is sound (path-scoped tenants,
404-for-non-member contract, server-side tiers, RLS backstop, hashed invite
tokens, allowlist rich-text rendering, formula-escaped exports; no cross-tenant
hole found). The gaps are production performance, operational readiness, and a
handful of correctness edges.

## P0 — before real users

- [x] **1. N+1 query storms on hot admin endpoints** — Perf — **S** —
  `GET /guests`, `GET /responses`, `export.xlsx` and the summary's answer walk
  lazy-loaded `rsvp → companions → answers` per row (~600–1000 queries for a
  200-guest wedding; brutal over serverless + NullPool). Fix: the same
  `selectinload` chains `/summary/pivot` already uses.
  _Done 2026-07-09: eager loads on `list_guests`, `list_responses`,
  `_guests_with_rsvp`, `_attending_rsvps`; bounded-query-count test._
- [x] **2. Supabase token introspection on every request** — Perf/Availability
  — **S–M** — `get_current_user` HTTP-round-trips to `/auth/v1/user` per admin
  call (+latency, auth outage = dashboard outage). Fix now: short-TTL
  in-process cache keyed by token hash (success only). Later (P1): local JWT
  verification via cached JWKS. Trade-off: revocation lag ≤ TTL — acceptable
  because membership/disabled checks still run per request.
  _Done 2026-07-09: 60s TTL cache in `app/auth.py`; failures never cached;
  autouse test fixture clears it._
- [x] **3. Email delivery is a stub** — Functional — **S–M** — flows promise
  email (co-admin invites, approval/suspension notices) but `app/emailer.py`
  only logs to the dev outbox. Fix: Resend HTTP API behind
  `RESEND_API_KEY` + `EMAIL_FROM` env; outbox stays the dev/test fallback;
  never raises. Remaining infra: create the Resend account + domain (RT).
  _Done 2026-07-09 (code path; provider account still owed — see PROGRESS
  infra list)._
- [x] **4. No rate limiting on the unauthenticated guest API** — Security —
  **M** — `POST /api/i/{slug}/rsvp` and `POST …/wishes` are hammerable (spam,
  write load); reads also uncapped. Fix: per-instance fixed-window limiter
  (`app/ratelimit.py`) on the guest endpoints — writes 30/min/IP, reads
  120/min/IP, on by default only in production (`RATE_LIMIT_ENABLED`
  overrides). Trade-off: per-serverless-instance counters are approximate —
  Vercel WAF rules (Phase 0 backlog P1-2) stay the durable outer layer;
  revisit Upstash/Redis only if abuse shows up.
  _Done 2026-07-09 (app-side); WAF layer still owed when Vercel exists._

## P1 — soon after launch

- [x] **5. Platform root serves an arbitrary tenant's content** — Product/
  privacy — **S** — `GET /api/landing` (`tenancy.primary_wedding`) returns the
  earliest active+published wedding's landing copy: single-tenant leftover.
  Replace with a real platform landing (or static copy) once the product has a
  name.
  _Done 2026-07-09: endpoint + `primary_wedding` removed; `app/page.tsx` is a
  static platform landing (no fetch) with /create + /dashboard CTAs; smoke test
  asserts no tenant names leak to the root; per-wedding `/api/w/{slug}/landing`
  unchanged._
- [x] **6. Phone region hardcoded to SG** — Correctness — **S–M** —
  `validation.DEFAULT_REGION = "SG"`: non-SG guests typing national-format
  numbers get 422s or wrong normalization. Make it a per-wedding setting
  threaded into `normalize_phone` (already TODO'd in the code).
  _Done 2026-07-09: `settings["phone_region"]` (owner PATCH /settings,
  validated ISO code) → `wedding_phone_region()` threaded into guest RSVP,
  admin guest CRUD and import; SG stays the fallback. Owner-facing UI knob
  still owed (no settings panel exists yet; API is ready)._
- [x] **7. `max_storage_mb` entitlement never enforced** — Cost/abuse — **M**
  — uploads are per-file capped (15 MB) but unlimited in count. Needs
  per-wedding usage accounting: DB byte counter incremented on upload +
  occasional reconciliation against the bucket (counter alone drifts).
  _Done 2026-07-10: `weddings.storage_bytes_used` (migration `a7b8c9d0e1f2`),
  `check_storage` gate on /upload (exact compressed size, checked
  pre-persist; 0 MB = uploads off), counter surfaced in admin `/me`;
  `app/usage.py` reconcile (skips unmeasurable namespaces) via
  `/api/internal/cron/reconcile-storage`. Infra owed: the Vercel cron entry
  (weekly is plenty). Dashboard usage meter UI can come later._
- [x] **8. Platform console N+1 + unpaginated** — Scaling — **M** —
  `/platform/weddings` (4 queries/wedding), `/platform/users`
  (1 count/profile), `/platform/approvals` (rules re-eval per item); all
  unbounded. Grouped-count queries + limit/offset. Fine until ~hundreds of
  tenants; do before promoting broadly.
  _Done 2026-07-09: `_platform_wedding_cards` batches counts/plans/owner
  emails (fixed query count, pinned by tests); rules read once per approvals
  page; `limit`/`offset` (default 100, max 500) on weddings/users/approvals.
  Console UI pagination controls can come when needed._
- [x] **9. Archived-wedding purge job missing** — Compliance/PII — **M** — the
  promised "30-day undo, then purge" has no purge: archived weddings (guest
  emails/phones) persist forever. Needs a scheduled job (Vercel cron → internal
  endpoint) + hard-delete path. Keep the audit trail (`wedding_id` already
  SET NULL). Also the seam for GDPR-style deletion requests.
  _Done 2026-07-09: `weddings.archived_at` (migration `f1a2b3c4d5e6`; archive
  sets it, reinstate clears it), `app/purge.py` (30-day window, NULL timestamp
  never purged, audit kept + pointer nulled, best-effort media cleanup),
  `POST /api/platform/purge-archived` + `/api/internal/cron/purge-archived`
  (`CRON_SECRET` bearer; 404 when unset). Infra owed: the Vercel cron entry._
- [x] **10. Observability** — Ops — **S–M** — `print()` logging, no error
  tracking, `/health` doesn't ping the DB. Sentry both apps, structured logs
  with `wedding_id`/`user_sub`, DB check in `/health`. (Sentry account = infra
  list.)
  _Done 2026-07-09 (backend): `app/obs.py` — logging setup (`LOG_LEVEL`),
  `log_event` logfmt helper, Sentry init behind `SENTRY_DSN` (sentry-sdk
  pinned); prints → loggers; `/health` does SELECT 1 (`db_ok`, status
  `degraded`, always HTTP 200). Owed: Sentry account/DSN + frontend
  `@sentry/nextjs` (infra list)._

## P2 — hardening

- [ ] **11. Check-then-insert races surface as 500s** — **S** — wedding-slug
  create, RSVP upsert (unique `guest_id`), guest-slug mint, `check_limit`
  TOCTOU. Catch `IntegrityError` → 409 (or retry for slug mint).
- [ ] **12. Invite-accept can 500 for an existing member** — **S** —
  `invite_member` matches by `invited_email` only; a member whose sign-in email
  changed can be re-invited under the new email, and acceptance then violates
  `uq_member_wedding_user`. Guard in `accept_invite` (existing active
  membership for `user.sub` → clean 409/merge).
- [ ] **13. Unbounded JSON on content endpoints** — **S** —
  `ContentUpdate`/`StoryArcUpdate` accept arbitrary dicts; `_deep_merge`
  recurses on attacker-nested input (RecursionError → 500) and blob size is
  uncapped outside Vercel's body limit. Add max-depth/max-size validation
  (generous limits).
- [ ] **14. Import row/file caps** — **S** — `/import` parses the whole upload
  before the guest-cap check bounds creates. Cap file size (~15 MB) and rows
  (~5,000) up front.
- [ ] **15. `ensure_profile` commits on every request** — **S** — the auth
  dependency writes/commits even on pure reads. Commit only when the profile
  row actually changed.
- [ ] **16. Missing indexes** — **S** — `wishes(wedding_id, approved)` (public
  wall), `audit_log(created_at)` (tail sort), `rsvps(updated_at)`
  (`/responses` sort). Additive migration.
- [ ] **17. Naive/aware datetime juggling** — **M** — `_naive_utc`, the
  try/except in `platform.stats`, tzinfo branching in `accept_invite` /
  `_plan_assignment`. Standardize on tz-aware UTC + one helper; keep
  SQLite/Postgres both under test. Batch with other work.
- [ ] **18. RSVPs editable forever** — product decision — **S** — no deadline
  or lock after the event. Probably an optional per-wedding "RSVP deadline".
  Decide, then implement.

## P3 — later / deliberate deferrals

- [ ] **19. CSP `unsafe-inline` scripts** — move to nonce-based CSP (Next
  supports it) — **M**. Real XSS surface already small (RichText allowlist).
- [ ] **20. Sync SQLAlchemy + NullPool on serverless** — fresh pooler
  connection per request — **L**. Only revisit (async engine / always-on API
  host) if p95 latency still hurts after P0-1/2.
- [ ] **21. Guest-list pagination** — only needed if plans grow past ~500
  guests (200-guest default cap bounds today's responses).
- [ ] **22. Supabase-side ban on account disable** — API refusal works today;
  a disabled user keeps a valid Supabase session (noted in code).
- [x] **23. `/health` DB ping** — folded into item 10 (done 2026-07-09).
- [ ] **24. Local JWT verification via JWKS** — the durable follow-up to
  item 2's cache (removes the network hop entirely; ties to the project's
  signing-key config).

## Reviewed and fine (don't re-litigate)

Cross-tenant scoping (every query filters `wedding_id`; bulk ops use
`_owned_guests_in`); tier invisibility (server-side caps, clamped prefills,
generic 422s); guest-slug entropy (128-bit); RLS backstop on all tables;
authz status-code contract pinned by tests; hashed single-use expiring invite
tokens with email-match acceptance; contact masking on invite GET with
mask-echo ignored on POST; formula-injection escaping in exports; allowlist
HTML parser (no `dangerouslySetInnerHTML`); `extra="forbid"` + length caps on
schemas; additive-only migrations; dev-token production guards
(ENVIRONMENT + VERCEL, constant-time compare); audit log riding the caller's
transaction; entitlements enforced server-side on create-only.
