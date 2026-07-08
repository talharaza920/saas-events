# SaaS Platform Plan — multi-tenant wedding-RSVP product

_Drafted 2026-07-08 from RT's decisions. This plan governs THIS repo — the
new, separate product. The predecessor single-wedding repo/deployment stays
live and otherwise frozen (see "Relationship to the predecessor wedding
site")._

## Decisions locked (RT, 2026-07-08)

1. **Separate product from day one.** Fork this codebase into a **new repo**, new
   Supabase project, new Vercel projects. The live wedding site never shares a
   database, storage bucket, or deployment with the platform. Two codebases are
   accepted; the live site gets only security/bug fixes.
2. **URL model: path-based.** `yourdomain.com/{wedding-slug}/admin`,
   `yourdomain.com/{wedding-slug}/i/{guestSlug}`. Custom domains / subdomains
   become a **paid-tier feature later** (Phase 7) — no wildcard-DNS work now.
3. **Entitlements now, payments later.** Build the plans/limits engine and the
   super-admin UI to define tiers and assign them manually. Stripe (or similar)
   slots in later without rework (Phase 6).
4. RT may implement **in stages and change models along the way** — every phase
   below is independently shippable, additive-only (no phase requires rework of
   an earlier one), and has explicit exit criteria so work can pause at any
   boundary.

## Roles (target model)

| Role | Scope | Powers |
|---|---|---|
| **Platform admin** (super admin, RT) | whole platform | approve/deny/suspend weddings, auto-approval rules, define plans & entitlements, assign/override plans, manage users & other platform admins, cross-tenant support views, audit everything |
| **Wedding owner** | one wedding (creator) | everything a wedding admin can, plus: invite/remove co-admins, transfer ownership, delete the wedding, (later) billing |
| **Wedding admin** (co-admin) | one wedding | edit content/theme, manage guests/questions/arcs, moderate wishes, import/export, publish (configurable) |
| **Guest** | one invite link | no account ever — the signed slug stays the only guest credential |

A user can belong to multiple weddings (many-to-many membership) and hold
different roles in each.

---

## Phase 0 — Fork, personal-data scrub, security hardening

**Goal:** a clean, neutral, hardened codebase with zero of RT's personal data,
running on fresh infrastructure. Nothing platform-y yet — it should still boot
as "one wedding" against an empty DB.

### 0.1 Fork & fresh infrastructure
- New GitHub repo (fork/copy — decide whether to keep git history; recommend a
  **squashed fresh start** so personal content never lives in the new repo's
  history). New Supabase project, new Vercel frontend + backend projects, new
  env vars throughout. `hnd1`/region pinning lesson carries over (LEARNINGS
  2026-07-08 entry).
- Do **not** copy: `0_REFERENCE/`, `docs/WEDDING_CONTEXT.md`, real `.env`
  values, `dev.db`, any guest data, the proposal-comic images.

### 0.2 Personal-data & branding scrub (hard requirement)
The fork must contain **no** trace of the predecessor wedding. Verify with a
final case-insensitive grep sweep — the term list itself is personal data, so
it lives in the predecessor repo's copy of this plan, not here. Known
locations:
- `backend/app/seed_data.py` — full personal copy/story/details → replace with
  a **neutral default template** (placeholder couple "Alex & Sam", generic
  venue/date placeholders, lorem-adjacent but tasteful story beats).
- `frontend/public/invite/story/*.png`, `wordmark.png` — proposal comic and
  personal wordmark → remove; ship neutral illustrated placeholders.
- `frontend/lib/content.ts` `RSVP_DEFAULTS` and any render fallbacks →
  neutral microcopy defaults.
- Cat/mascot components (`CatGlyph`, `MascotBadge`, `PetTheCat`, `Paw`,
  `Wordmark` ring text): **decided 2026-07-08** — generalized into an optional
  theme feature with the built-in glyph as neutral default art.
- `docs/` — carry over only PLAN-style architecture docs, rewritten without
  personal facts; start a fresh LEARNINGS.md.

### 0.3 Security hardening (from the 2026-07-08 security review)
Apply **all** of these in the fork. Items marked ⚠ should ALSO be cherry-picked
back to the live wedding deployment, since it serves real guests today.

**P1 (before any external user touches it):**
1. ⚠ Dev-token bypass hardening (`backend/app/auth.py`): refuse the dev path
   when `os.environ.get("VERCEL")` is set (belt-and-braces against the
   `ENVIRONMENT` misconfig incident), and compare with
   `secrets.compare_digest()`. *Easy.*
2. ⚠ Rate limiting via Vercel WAF rules: POST `/api/i/*` ~10/min/IP,
   `/api/admin/*` ~60/min/IP, signup/auth endpoints tighter. Revisit app-level
   limiting (Redis) only if WAF proves insufficient. *Easy (dashboard).*
3. ⚠ Stop sending owner-only data to guests: strip `event_details.capacity`
   (and allowlist `event_details`/`content` keys) from the invite payload
   (`invite.py` `WeddingPublic`). *Easy.*
4. ⚠ Bound RSVP answer payloads: validate `AnswerSubmit.value` to the known
   shapes (text/number/choice/choices/yesno), cap text length (~2,000 chars),
   cap answers-list length, reject duplicate `question_id`s. *Easy.*

**P2:**
5. Security headers in `next.config.ts` `headers()`: CSP (script-src 'self',
   frame-ancestors 'none'; MUI needs style-src 'unsafe-inline'),
   `X-Content-Type-Options: nosniff`, explicit `Referrer-Policy:
   strict-origin-when-cross-origin` (protects guest slugs in referrers).
   *Medium — needs iteration with MUI.*
6. ⚠ Pin `next/image` `remotePatterns` to the exact Supabase project host
   (today's `*.supabase.co` wildcard is an open image-proxy vector). *Easy.*
7. Mask guest contacts in `GET /api/i/{slug}` (e.g. `t•••@gmail.com`,
   `+65 •••• 1234`); accept full values only on POST. Links get forwarded —
   platform users' guests deserve this by default. *Medium.*
8. Keep Next.js on the latest patch (npm-audit moderates via bundled postcss;
   framework CVE history is the real reason). *Easy, recurring.*

**P3:**
9. Trim `/health` (don't advertise env/db backend). *Easy.*
10. Enforce upload size before reading the whole body; keep the 15 MB image cap
    but check `Content-Length` first. *Easy.*
11. Log failed admin-auth attempts (structured, visible in Vercel logs). *Easy.*
12. Drop `x-upsert: true` on Supabase Storage uploads. *Easy.*

### Exit criteria
Clean repo boots against the fresh Supabase with a neutral seeded wedding; grep
sweep returns zero personal hits; P1+P2 hardening merged; tests green.

---

## Phase 1 — Identity & tenancy core (accounts, membership, authz)

**Goal:** real user accounts and the membership-based authorization model.
Still no self-serve signup UI — accounts are created but weddings are made by
script/platform admin. This phase is the deepest plumbing; do it before any UX.

### 1.1 Auth
- Supabase Auth: **Google OAuth + email/password with mandatory email
  verification**. (Password policy per Supabase defaults; add hCaptcha on
  signup if abuse appears.)
- Transactional email provider (Resend or Supabase's built-in SMTP → replace
  with Resend when volume matters) for verification, invites, approval notices.

### 1.2 Schema (additive)
- `profiles` — `user_id (PK, = auth.users.id)`, `display_name`, `created_at`.
  Filled by trigger on signup.
- `wedding_members` — `id`, `wedding_id`, `user_id NULL`, `invited_email`,
  `role ∈ {owner, admin}`, `status ∈ {invited, active, revoked}`, `invited_by`,
  timestamps. Unique on `(wedding_id, user_id)` and `(wedding_id, invited_email)`.
- `platform_admins` — `user_id`, `granted_by`, `created_at`. Bootstrap row for
  RT seeded by migration/env; the `ADMIN_EMAILS` env var remains only as the
  bootstrap fallback.
- `weddings` gains: `status` extended to
  `draft | pending_approval | active | suspended | archived`, plus
  `published BOOLEAN` (RSVP/public pages live) — approval and publication are
  independent switches.
- `audit_log` — `id`, `wedding_id NULL` (null = platform-level), `actor_user_id`,
  `action`, `target_type/target_id`, `detail JSONB`, `created_at`. Written by a
  small helper from every mutating admin/platform endpoint. (Best practice:
  cheap to write now, impossible to retrofit history later.)

### 1.3 Authorization seams (the one planned in PLAN.md, now executed)
- Replace `owner_wedding` (`backend/app/routers/admin.py`) with
  `require_wedding_member(role_at_least)` — resolves the wedding **from the
  path** (`/{wedding-slug}/…` → wedding), then requires: platform admin, OR an
  `active` membership row. Owner-only endpoints (member management, delete,
  transfer) take `role_at_least="owner"`.
- New `require_platform_admin` dependency for `/api/platform/*`.
- Wedding-scoped API paths: `/api/w/{wedding_slug}/admin/*` (guest endpoints
  keep `/api/i/{guestSlug}` — the guest slug is still globally unique and
  tenant-carrying; the wedding slug in the *frontend* URL is cosmetic/routing).
- Frontend routes: `/{weddingSlug}/admin` (dashboard), `/{weddingSlug}` (public
  wedding page), `/{weddingSlug}/i/{guestSlug}` (invite). **Reserved-slug
  blocklist** (admin, api, platform, login, signup, w, i, www, static, …)
  enforced at wedding creation.
- RLS stance (documented, deliberate): backend remains the sole DB actor via
  the owner role with app-level scoping; RLS stays enabled-with-no-policies so
  the Supabase anon surface is denied everything. Supabase client SDK in the
  browser is **auth-only**. Revisit real JWT-keyed RLS policies only if we ever
  expose PostgREST directly.

### 1.4 Multi-wedding UX shell
- Post-login home `/dashboard`: list of weddings you belong to + role chips;
  wedding switcher. (Creation flow arrives in Phase 2.)

### Exit criteria
Login works (Google + email/verified password); memberships gate every admin
endpoint; platform-admin dependency exists; audit log writing; all existing
admin UI functions under `/{weddingSlug}/admin` with a member account.

---

## Phase 2 — Self-serve signup, wedding creation & approval workflow

**Goal:** a stranger can sign up, create a wedding from the neutral template,
and (once approved) publish an RSVP site.

### 2.1 Creation wizard
- `/create`: couple names → auto-suggested slug (editable, uniqueness +
  blocklist checked live) → event date/venue (optional at creation) → done.
- Seeds: neutral template content + default theme tokens + default RSVP
  questions; creator gets the `owner` membership row; wedding starts in
  `draft`.
- Empty-state dashboard guides: edit content → add guests → request publish.

### 2.2 Approval workflow (RT's allow / auto-allow / cancel requirement)
- Owner clicks **"Submit for approval"** (or it happens implicitly on first
  publish attempt): `draft → pending_approval`.
- `platform_settings` (single-row JSONB or key-value table) holds
  **auto-approval rules**, editable in the platform console (Phase 4):
  - `auto_approve: on|off`
  - conditions when on: email verified, account age ≥ N hours, ≤ N weddings
    per account, guest count at submission ≤ N, no banned-word hits in
    slug/content. All pass → instant `active`; any fail → queued for manual
    review.
- Manual queue: platform admin approves (`active`), denies with reason
  (`draft` + notification), or suspends later (`suspended`).
- **Suspension semantics:** public + invite pages return a neutral 404/holding
  page; wedding admins see a "suspended" banner and read-only dashboard;
  platform admin can reinstate. Guests never see why.
- **Publish** (independent of approval): owner toggles `published` once
  `active`; unpublished active weddings are editable but publicly invisible.
- All transitions → `audit_log` + email notifications.

### 2.3 Validation & abuse controls
- Rate-limit signup + wedding creation (WAF + per-account caps from
  entitlements).
- Content flags for platform review: banned-word list scan on publish;
  storage-size and guest-count anomalies surfaced in the console (Phase 4).

### Exit criteria
End-to-end cold-start demo: new Google account → create wedding → edit content
→ add guests → submit → (auto-)approve → publish → guest opens invite and
RSVPs. RT's own test wedding created this way, not seeded.

---

## Phase 3 — Co-admins & team management

**Goal:** the "add other admins to their wedding" requirement.

- **Invite by email** from a new Members tab: creates an `invited` membership
  row + a single-use, expiring, signed invite token emailed out. Accepting
  (logged-in, email must match, or claim-by-login) flips it `active`.
- Owner powers: change roles, revoke members, transfer ownership (two-step
  confirm), delete wedding (soft-delete → `archived`, hard purge after 30 days
  — gives an undo window and satisfies "cancel permission" cleanly).
- Admin (non-owner) powers: everything content/guest/RSVP; **not** member
  management, not delete/transfer. Publish rights: owner-only by default,
  owner can grant to admins (a per-wedding setting).
- Every membership change → `audit_log` + email to the affected user.

### Exit criteria
Two-account demo: owner invites a co-admin, co-admin edits guests, owner revokes,
access dies immediately (membership checked per-request, no long-lived caching).

---

## Phase 4 — Platform (super admin) console

**Goal:** RT's cockpit. Frontend at `/platform` (platform-admin only), backend
under `/api/platform/*` behind `require_platform_admin`.

- **Weddings view:** all weddings + status, owner, member count, guest count,
  storage used, plan; actions: approve / deny / suspend / reinstate / archive;
  drill-in read-only view of any wedding ("view as" — always audit-logged,
  visually bannered, no silent impersonation).
- **Approval queue:** pending weddings with the rule-evaluation trace (which
  auto-rule failed), one-click approve/deny with reason.
- **Rules editor:** the `platform_settings` auto-approval knobs (2.2) + banned
  words + platform-wide defaults (e.g. default plan for new weddings).
- **Users view:** all accounts, weddings per account, verified status; disable
  account (Supabase ban) — audit-logged.
- **Plans & entitlements editor** (engine ships in Phase 5; the UI lands here —
  build the console shell so 5 plugs in).
- **Ops widgets:** signups/week, weddings by status, RSVPs/day, storage total,
  recent audit-log tail.

### Exit criteria
RT can run the whole approval lifecycle and inspect any tenant from `/platform`
without touching SQL.

---

## Phase 5 — Plans & entitlements engine (no payments)

**Goal:** tiered capability limits, defined and assigned by the super admin.

### 5.1 Schema
- `plans` — `id`, `name`, `description`, `is_default`, `entitlements JSONB`,
  `created_at`, `archived`.
- `wedding_plans` — `wedding_id (unique)`, `plan_id`, `overrides JSONB`
  (per-wedding exceptions RT grants), `assigned_by`, `valid_until NULL`,
  timestamps. Effective entitlements = plan ∪ overrides.

### 5.2 Entitlement keys (initial set — JSONB so adding keys needs no migration)
`max_guests`, `max_members`, `max_custom_questions` (0 = feature off),
`max_story_arcs`, `max_storage_mb`, `wishes_enabled`, `export_enabled`,
`import_enabled`, `custom_domain` (future), `remove_platform_badge`,
`max_weddings_per_account` (account-level, checked at creation).

### 5.3 Enforcement
- One helper: `require_entitlement(wedding, key)` / `check_limit(wedding, key,
  current_count)` used inside create-endpoints (guest create/import, question
  create, member invite, upload) — **server-side is the source of truth**;
  the frontend reads an `entitlements` block from `/api/w/{slug}/admin/me` to
  gray out UI and show friendly "not on your plan" messaging with an upgrade
  hint (no payments yet — the hint says "contact us"/is dormant).
- Limits are checked on **create**, never retroactively destructive: lowering a
  plan below current usage blocks *new* adds, never deletes data.
- Default plan auto-assigned at wedding creation (`plans.is_default`).

### Exit criteria
Two plans defined in the console (e.g. Free: 50 guests, no custom questions;
Plus: 300 guests, questions on); limits provably enforced via API attempts, UI
degrades gracefully; RT can override a single wedding.

---

## Phase 6 — Billing (deferred; design constraints only)

Not built until RT decides to charge. The Phase 5 design keeps this drop-in:
- Stripe Checkout + customer portal; webhook → set/clear `wedding_plans`
  (subscription state maps to plan assignment; `valid_until` covers grace
  periods). Manual assignments keep working alongside (comps).
- Singapore specifics when the time comes: Stripe SG, GST registration
  threshold awareness, invoice fields.
- Trials = default plan with `valid_until`.

---

## Phase 7 — Growth & platform polish (backlog, order per demand)

- **Custom domains / subdomains** as a paid entitlement (Vercel Domains API,
  per-domain tenant mapping, DNS-verification UX).
- Template gallery (multiple neutral themes/content presets at creation).
- Theme editor expansion (beyond curated tokens).
- Invite delivery: email/WhatsApp sends from the dashboard (flips
  `invite_sent` automatically — the M14.2 hook).
- Per-wedding analytics (RSVP funnel, invite-open tracking).
- **Compliance/data-rights:** self-serve wedding data export (full JSON/XLSX)
  and account deletion (PDPA/GDPR); privacy policy + terms pages (needed
  earlier — draft placeholders in Phase 2, real text before public launch).
- Localization (copy is already data; the chrome strings need an i18n pass).

---

## Cross-cutting engineering practices (all phases)

- **Additive-only migrations**, applied to Supabase as part of every deploy
  (the 2026-06-13 lesson). Staging Supabase project + Vercel preview envs from
  Phase 1 on; never test migrations on the production platform DB.
- **Backups:** Supabase PITR/scheduled backups on from Phase 2 (real user data
  exists from then).
- **Observability:** Sentry (frontend + FastAPI) from Phase 1; structured logs
  with `wedding_id` + `user_id` on every request; uptime check on `/health`
  (trimmed variant).
- **Testing DoD per phase** (per rt-code-preferences): pytest for every authz
  seam (esp. cross-tenant negative tests: member of wedding A hitting wedding
  B must 404), typecheck/lint, browser-verified, PROGRESS/LEARNINGS updated,
  tagged release.
- **Cross-tenant test suite is sacred:** every new endpoint ships with a
  "wrong-tenant 404" and "no-membership 401/403" test. This is the #1 SaaS
  failure mode.
- **Secrets:** only in Vercel/Supabase env config; names-only `.env.example`;
  new service keys per environment; rotate anything that ever touched the fork.

## Relationship to the predecessor wedding site

- The predecessor repo stays the production site for the original wedding.
  Change policy there: security fixes (the ⚠ items above) + critical bugs only.
- No shared infrastructure with the platform, ever (separate Supabase, Vercel,
  buckets, domains).
- Optional after that wedding: import it into the platform as a normal
  tenant (keepsake archive). Nice-to-have; not planned work.

## Open questions for RT (needed by the phase noted)

1. **Platform name + domain** (Phase 0 — repo name, branding, neutral wordmark).
2. **Mascot decision** (Phase 0.2): strip the cat entirely, or generalize
   "mascot/motif" into a theme feature with neutral default art?
3. **Repo hosting/visibility** (Phase 0): private GitHub under your account?
4. **Auth breadth** (Phase 1): Google + email/password (planned) — also want
   Apple/Facebook, or keep it minimal?
5. **Publish rights default** (Phase 3): owner-only publish OK as the default?
6. **Terms/Privacy** (before Phase 2 goes public): self-drafted from templates,
   or is a proper review wanted?
