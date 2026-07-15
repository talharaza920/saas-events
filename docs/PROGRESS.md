# PROGRESS — saas-events platform

The resumable source of truth for platform work. Phases are defined in
`SAAS_PLAN.md`. The predecessor build's milestone history (M1–M14) lives in
that private repo, not here.

_Last updated: 2026-07-14 (Phases 1–5 built & tested locally; review P0, P1
AND P2 items all landed — see `REVIEW_BACKLOG.md`; P3 items are deliberate
deferrals. Phase 8 (AI wizard, `AI_WIZARD_PLAN.md`): 8.0–8.4b + 8.1c + the
8.5a funnel + the AI-config/console rework + **8.5b, the staged story wizard**
(text first, free hand edits, images one deliberate click at a time) + **8.5c,
guests** (one intake: a spreadsheet read by a parser for free, a messy list read
by the model, which asks about lines it can't read instead of guessing) +
**8.5d, likeness** (photos of the couple, behind a consent box, drawn as
stylised illustrations and never as photographs of them) + **8.5e, theme
presets** (~10 platform-curated looks a couple starts from, then edits on top;
console-managed catalogue) are all done locally. **Phase 8.5 is complete.**
Remaining: Anthropic key, the approval-queue decision, **the likeness legal
framing before public launch**, infra.)_

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
seam, guest-API rate limiting) are done. Suite: **458 pytest, 1 skipped**
(offline) + **25/25 E2E smoke** checks (`frontend/scripts/smoke-e2e.mjs`) +
**57/57 AI smoke** checks (`frontend/scripts/smoke-ai.mjs`, both against local
dev servers); `tsc`/`eslint`/`next build` clean.

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
- [x] `max_storage_mb` metered + enforced (2026-07-10, review P1-7):
  `storage_bytes_used` counter gates `/upload`; reconcile cron corrects drift.

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
- [x] P1-7 storage metering (2026-07-10): `storage_bytes_used` counter
  (migration `a7b8c9d0e1f2`) gates `/upload` against `max_storage_mb`;
  reconcile cron (`app/usage.py`) corrects drift against the bucket.
- [x] **P2 hardening — ALL DONE 2026-07-10** (items 11–18, details in
  `REVIEW_BACKLOG.md`): check-then-insert races → 409 (targeted catches + an
  app-wide `IntegrityError` backstop handler); invite-accept merges cleanly
  for an existing member; content/story-arc JSON bounded (depth/nodes/string
  caps in schemas); import caps (15 MB / 5,000 rows, enforced during parse);
  `ensure_profile` commit discipline verified + pinned; hot-path indexes
  (migration `b8c9d0e1f2a3`: wishes wall, audit tail, responses sort);
  tz-aware UTC standardized in `app/timeutil.py`; optional per-wedding
  **RSVP deadline** (`settings.rsvp_deadline`, guest POST 403 after it,
  `rsvp_open` flag in the invite payload; owner UI knob owed with the
  settings panel).
- [ ] Remaining review items are P3 (deliberate deferrals — revisit when the
  triggering condition appears, see `REVIEW_BACKLOG.md`).

## Phase 6 (billing) / Phase 7 (growth) — not started (by design)

## Phase 8 — AI creation wizard (`AI_WIZARD_PLAN.md`)

- [x] **8.0 Data model — DONE (local) 2026-07-10.** Migration `c9d0e1f2a3b4`:
  `ai_jobs` (partial unique index `uq_ai_jobs_one_active` = one queued/running
  job per wedding, enforced in the DB; `(wedding_id, idempotency_key)` unique),
  `ai_inputs`, `ai_usage_ledger` (append-only; survives purge with pointers
  nulled, like `audit_log` — purge.py updated), `ai_variants`, `ai_prompts`
  (platform-owned; `provider=''` = shared fallback since Postgres forbids NULL
  PK columns). Tenant tables ride the Wedding ORM purge cascade. AI entitlement
  keys (`ai_enabled` off by default, credits/regen/input caps) in
  `DEFAULT_ENTITLEMENTS`. Tests: `tests/test_ai_models.py`.
- [x] **8.1a Provider port — DONE (local) 2026-07-10.** `app/ai/` package:
  `types.py` (one-method `TextModel` port — `generate_structured(prompt,
  schema, effort)`; `ProviderRefusal`/`ProviderError` are the only failure
  surface), `providers/anthropic.py` (reference adapter: explicit adaptive
  thinking, `output_config.effort`, cache-hint breakpoint on the system block,
  no sampling knobs, refusal/truncation mapping, lazy SDK import + injectable
  client), `providers/fake.py` (deterministic offline adapter — also the
  golden-set replay seam), `pricing.py` + `ledger.py` (money priced at write
  time; unknown model → 0, auditable), config knobs (`ai_text_provider|model|
  effort`, `anthropic_api_key`). Tests: `tests/test_ai_provider_port.py`.
  **`providers/openai.py` added 2026-07-11** (RT has a key): Responses API
  `responses.parse(text_format=…)`, port Effort → `reasoning.effort` (one
  logged retry without it for non-reasoning models), refusal parts +
  content-filter → `ProviderRefusal`, cache hint ignored (auto prefix cache),
  refuses a Claude model id with the fix named; `openai_api_key` config,
  gpt-5-family prices in the table, `openai==2.45.0` pinned. NOTE: a
  production provider swap still gates on the golden-set eval (8.1c).
- [x] **8.2 Prompt registry (backend) — DONE (local) 2026-07-10.**
  `app/ai/prompts.py`: the four code-default system prompts (extract /
  draft_arc / ground / glyph), `ai_prompts` DB overrides (provider-specific >
  shared > code default; malformed/inactive rows fall back — never brick),
  allowlisted `string.Template.safe_substitute` rendering (injection-safe;
  tested with `${x.__class__}` payloads). Editor API landed with 8.4a; the
  console UI page landed with 8.4b.
- [x] **8.1b Pipeline core — DONE (local) 2026-07-11.** `app/ai/jobs.py`
  state machine (create → advance-one-step → awaiting_review; cancel/fail/
  expire all refund + sweep inputs), fixed step lists per kind (wizard:
  transcribe→extract→resolve→draft→ground; story_arc; glyph),
  `schemas.py` (bounded, extra=forbid step outputs — no free-text channel),
  `credits.py` (flat per-kind cost, free-arc allowance, hold-is-charge until
  Phase 6 settles against actual dollars), `media.py` (text passes through;
  Gemini call stubbed behind ProviderError until a billing-enabled key
  exists), `resolve.py` (Places text-search; no key → couple's own words,
  never invented), `ai` platform-settings blob with `kill_switch`. Creation
  gates: ai_enabled 403 · kill switch 503 · active-run 409 (friendly check +
  DB index backstop) · credits 403 · cross-tenant inputs 404. Tests:
  `tests/test_ai_pipeline.py`.
- [x] **8.1c Media, images, guests, eval — DONE (local + live-verified)
  2026-07-12.** Model ids confirmed against Google's docs that day and pinned
  in CONFIG (`gemini_transcribe_model=gemini-3.5-flash`,
  `gemini_image_model=gemini-3.1-flash-image` "Nano Banana 2"; google-genai
  2.11.0 pinned; `generate_content` remains first-class — the Interactions
  API is recommended-not-required).
  **Media:** `app/ai/media.py` grew the real `GeminiMedia` adapter (lazy SDK,
  injectable client, refusal/blocked mapping, usage→ledger with Gemini
  prices); POST `…/ai/inputs/upload` (multipart; audio/image/PDF, 10 MB cap =
  inline-request headroom) stores under a transient UNMETERED
  `ai-inputs/<slug>` namespace with per-object delete wired into every input
  sweep (terminate/apply/reap/purge). Transcribe step ledgers per media call.
  **Images:** new `images` pipeline step (wizard + story_arc, after draft):
  one Nano Banana request per beat capped by `ai_max_images_per_arc`,
  IMAGES_PER_ADVANCE=2 per /advance with the step REPEATING until done (runner
  returns False; AiRunProgress now keys its loop on object identity); refusal
  or missing key or full storage degrade to text-only beats, never fail the
  run; output format sniffed by magic bytes (Gemini returns JPEG — verified
  live); generated art is metered + byte-tracked in job.state so cancel
  refunds the counter and apply sweeps unkept files; per-image pricing table
  (`IMAGE_PRICES`); proposal carries `beat_images` BESIDE the draft (an
  `image` field inside ArcBeat would invite the model to fill it); per-beat
  regeneration (`arc.beat.N` variants, steer rides the scene text,
  new-image auto-selected) and arc.text selection restores each draft's own
  art. **Guests:** kind `guests` (transcribe→guests): the model returns raw
  lines EXACTLY as written (GuestLines schema); `guest_import.build_guests`/
  `infer_tier()` assign tiers in code; apply writer recomputes tiers from
  bounded counts (tampered proposal tiers ignored — tested), creates rows
  with fresh 128-bit slugs, `seed_meta.ai_generated`, `expected_party_size`,
  `story_arc_ids` NULL, `max_guests` re-checked; `SECTIONS_BY_KIND` scopes
  apply sections per kind (a wizard proposal can't smuggle guests). UI:
  AiPanel attach-files + "Extract a guest list", review panel renders beat
  images/variants and the guests/tiers section. **Eval:** `evals/golden.py`
  (12 fictional fixtures: nulls-where-silent, prompt injection, distractor
  venue, 3 planted hallucinations, 2 glyphs) + `scripts/eval_golden.py`
  (live per provider/model, records to `evals/recordings/`, budgets on
  median cost/latency) + `tests/test_ai_golden_replay.py` (offline re-judge
  of recordings). The first LIVE run (gpt-5.1, effort=high) caught two real
  adapter bugs: reasoning tokens truncating structured output
  (effort-scaled headroom added to BOTH adapters) and snapshot model ids
  ledgering $0 (usage now records the requested id). Live Gemini sanity
  check passed (transcribe $0.002; 1408×768 image $0.067). Tests:
  `tests/test_ai_media_guests.py` (19).
- [x] **8.3 Guardrails — DONE (local) 2026-07-11.** `app/ai/svg.py`
  (defusedxml parse → allowlist REBUILD → re-serialise; script/handlers/style/
  hrefs/url(#)/non-currentColor paint/text all dropped by construction; runs
  inside the glyph step so the review UI never sees raw model output, and again
  at apply). `app/ai/apply.py` (human-gated transactional apply; writes ONLY
  couple_names / event_details display keys / one new story arc / brand.icon_svg;
  never slug/status/published/invite_tier/settings/theme; re-checks
  `max_story_arcs` + platform banned-word scan at apply time; audit
  `ai.job.apply` with `source: "ai"`; `ai_generated: true` stamped on created
  rows — hostile-proposal test proves the non-writes). Daily cost ceiling
  (`ai.daily_cost_ceiling_usd`, ledger-summed since UTC midnight) checked with
  the kill switch before every advance — tripping QUEUES the job (503 +
  Retry-After, no state change), never fails it. Reap cron:
  `/api/internal/cron/reap-ai-jobs` (`require_cron_secret`) expires stuck
  active jobs past `expires_at` (refund + input sweep) and deletes orphan
  `ai_inputs` older than 24 h. Tests: `tests/test_ai_guardrails.py` (19).
- [x] **8.4a API surface (backend) — DONE (local) 2026-07-11.**
  `app/routers/ai_admin.py` — `/api/w/{slug}/admin/ai/*` riding
  `require_wedding`: POST `inputs` (text now; media kinds land with the Gemini
  seam in 8.1c), POST `jobs` (Idempotency-Key header), GET `jobs` +
  `jobs/{id}` (proposal + variants; `state` never crosses the wire), POST
  `advance` / `regenerate` / `select` / `apply` / `cancel`, GET `credits`.
  New `app/ai/variants.py` — per-artifact regeneration (`arc.text` re-drafts
  AND re-grounds; `glyph` re-sanitises): appends `ai_variants` rows with the
  original seeded as variant 0 (nothing destroyed), first regen of each
  artifact free then 1 credit (rides the job's hold), capped by
  `ai_max_regens_per_artifact`; the bounded `steer` note goes in the USER
  turn only; refused/failed regens never charge (ledger still records calls
  that ran). `select` writes the keeper into `job.proposal`, so the apply
  allowlist never learns variants exist. Platform console API in
  `platform.py`: GET/PUT `/settings/ai` (kill switch + ceiling, audited),
  GET/PUT `/ai/prompts` + `/activate` (versioned saves, rollback =
  deactivate, falls back to code defaults; unknown keys 404), GET `/ai/usage`
  (spend by day/kind/provider, top weddings, jobs by status).
  `check_circuit_breaker` extracted in `jobs.py` (advance + regenerate share
  it). Tests: `tests/test_ai_api.py` (18) — the 401/404 matrix over every
  endpoint, wrong-tenant job 404 through a member's own path, suspended
  read-only, platform 403s, full wizard→apply over HTTP, idempotency,
  step-replay, regen credits/cap/refusal, select swap-and-back, glyph regen
  sanitised, console settings/prompts/usage.
- [x] **8.4b Wizard/review UI + consoles — DONE (local) 2026-07-12.**
  Frontend: `aiApi` in `lib/adminApi.ts` (same transport/wedding binding) and
  AI methods in `lib/platformApi.ts`. Shared components in `components/ai/`:
  `AiRunProgress` (drives POST `advance` one step at a time with
  `expected_step` replay-safety; a 503 breaker/ceiling pauses with a retry,
  never fails), `AiReviewPanel` (per-section apply checkboxes, amber
  grounding flags matched to beats, variants side-by-side with select +
  bounded steer + regenerate, apply/cancel, credits chip, post-apply "use it
  as your cover icon" switch), `GlyphMark` (renders ONLY the server-sanitised
  SVG). `/create` gains an optional story field — the wedding is created
  FIRST (plan's rule), then the wizard runs inline under the normal admin
  API, with a friendly fallback when the plan has `ai_enabled=false`. Admin
  dashboard gains an **AI tab** (`components/admin/AiPanel.tsx`: credits,
  start story_arc/glyph runs, revive in-flight runs on reload, recent-runs
  list). Platform console gains an **AI tab**
  (`components/platform/AiConsoleTab.tsx`: kill switch + daily ceiling,
  usage widgets — today/30 days/by step/by provider/top spenders/jobs by
  status — and the prompt registry editor: versioned saves, activate/
  deactivate rollback, live/effective markers). Glyph icon opt-in:
  `BrandIconMode` gains `"svg"` (cover `Wordmark` renders
  `content.brand.icon_svg` inline in currentColor; only the AI apply path
  ever writes that key; DetailsPanel offers "AI mark" when one exists; apply
  itself still never touches `icon_mode` — the switch is the owner's call).
  Dev seams so all of this runs offline: the provider factory's `fake` branch
  now serves `demo_responses()` (full wizard offline, one amber flag by
  default, module-level cycles so regenerated variants actually differ) and
  `dev_setup` seeds a default **Local dev plan** with `ai_enabled` + 50
  credits. Verified end-to-end in a real browser by
  `frontend/scripts/smoke-ai.mjs` (17/17): story run → amber flag → free
  regen → variant select → apply (arc row `ai_generated` via API), glyph run
  → apply → icon switch (API-checked `icon_mode=svg`), guest cover renders
  the stored sanitised mark, platform AI console, `/create` story wizard
  through to the dashboard handoff.
- [x] **8.5a Funnel — DONE (local) 2026-07-12.** The monolithic `wizard` kind
  is **demoted to `details`** (transcribe → extract → resolve only; 1 text
  call, 1 credit, no free-arc allowance — that stays with `story_arc`), and
  its apply allowlist shrinks to `couple_names` + `event_details`
  (`SECTIONS_BY_KIND`). A retired-kind job row now expires with a refund
  instead of KeyError-ing on its step list. `/create` slims to **names +
  slug** and hands off to a new **`/{weddingSlug}/setup`** — three skippable
  steps (Key details → Your story → Guest list), each embedding the same new
  **`AiAssist`** component the tabs now use, so there is no parallel wizard
  code path. Per-tab AI entry points: Details (`details`), Story
  (`story_arc`), Guests (`guests`, beside the existing deterministic import);
  the AI tab keeps credits, the mark designer and run history.
  `SetupChecklistCard` on the wedding dashboard re-enters the flow —
  completion is **derived** from the wedding (details/arcs/guests), so only
  the owner's `settings.setup_dismissed` is stored (`AdminMe.setup_dismissed`
  + the existing owner-only settings PATCH). Gotcha fixed in review: after an
  apply, `AiAssist` must NOT re-derive its job from the active list —
  `applied` is terminal, so the refetch unmounted the success state the
  instant the couple applied.
- [x] **AI config: one live-call switch + per-provider models — DONE 2026-07-13.**
  Going offline used to mean setting three unrelated things
  (`AI_TEXT_PROVIDER=fake` *and* blanking `GEMINI_API_KEY` *and*
  `GOOGLE_PLACES_API_KEY`); missing one is what made the "offline" browser smoke
  spend real money on images. Now `AI_LIVE_CALLS=false` is the master switch —
  no AI call leaves the process, whatever keys are set — with per-capability
  overrides (`AI_LIVE_TEXT` / `_IMAGES` / `_TRANSCRIBE` / `_PLACES`) that can
  only turn things *off*: a `true` can never re-open what the master shut. Call
  sites ask `settings.ai_text_live` / `ai_transcribe_enabled` /
  `ai_images_enabled` / `ai_places_enabled`, each folding "is it configured?"
  together with "are we allowed?"; off degrades exactly like the no-key case
  (fake text adapter, media refused, beats text-only, venue keeps the couple's
  words). Model ids are now per-provider (`AI_MODEL_ANTHROPIC`,
  `AI_MODEL_OPENAI`, + the two Gemini ids) and `settings.text_model` resolves
  the one for the configured provider, so `AI_TEXT_PROVIDER=openai` alone is a
  complete config — it previously also needed `AI_TEXT_MODEL`, and forgetting
  pointed a Claude id at OpenAI. The backend prints its AI mode on boot;
  `eval_golden.py` forces live calls (a faked green eval would be a lie).
  `tests/test_ai_config.py` (12 tests) pins both footguns.
- [x] **Prompts AND models are console-editable — DONE 2026-07-13.** Model ids
  churn faster than deploys, so which provider/model the pipeline uses is now a
  platform-admin decision, not a redeploy — the same argument that already put
  the prompt registry in the DB. `.env` keeps the *bootstrap* default (and the
  API keys, which never leave it); the `platform_settings['ai']` blob gains
  `text_provider` / `text_model` / `text_effort`, each `""` = "use the deployed
  default", so clearing a field restores it rather than leaving a stale pin.
  `ai/runtime.effective_settings()` overlays the blob onto `Settings` and is
  applied once, at the AI router's settings dependency, so the choice reaches
  `render_prompt(provider=…)`, the effort default and the adapter alike. Same
  never-brick-a-tenant discipline as the prompt registry: a malformed override is
  logged and ignored (falls back to env), a model from the wrong family is
  refused at the console (422) rather than at the provider on a couple's next
  run, and switching provider drops a stale `AI_TEXT_MODEL` env pin so it can't
  ride along to the new provider. The console **cannot** re-enable AI that
  `AI_LIVE_CALLS` switched off (a stop switch that needs the DB fails exactly
  when needed) and `fake` is not selectable (stopping AI is the kill switch's
  job — it fails closed; canned prose would fail open). The AI tab gains a Text
  model card showing what is *actually* in force, whether it came from env or
  the console, whether the environment is even making live calls, and which
  providers have a key (booleans only — a key never crosses the wire). Prompts
  were already fully editable (template/provider/model/effort/max-tokens,
  versioned, activate-to-roll-back). `tests/test_ai_console_model.py` (12).
- [x] **8.5b Staged story wizard — DONE (local) 2026-07-13.** A `story_arc` run
  is now TEXT ONLY (`STEPS` drops `images`; 4 steps, no image call, no image
  credit) and parks at review as an **editable outline**: `PATCH
  …/ai/jobs/{id}/proposal` (`app/ai/edit.py`) re-validates the couple's edits
  through `DraftArc` (bounds hold; only `story_arc` is writable), records every
  changed path in `proposal.user_edited`, and **drops the grounding flags on
  lines they rewrote** — the fact-check exists to catch the model inventing
  things, and a sentence the couple typed needs no receipt. Editing is free and
  makes no provider call. Illustration became an explicit stage
  (`app/ai/images.py`): `POST …/illustrate {targets?}` renders panels — the
  beats **and the climax** (`DraftArc.climax_image_prompt`, applied as
  `climax.image`, which the guest Story component already renders) — two per
  call, **1 credit each onto the job's hold** (so a cancel refunds the art with
  the text), capped by `ai_max_images_per_arc`, with refusals/full-storage
  leaving that one panel text-only. The couple's path: read → edit → pick a
  **style** → illustrate beat 0 → iterate the style on that one image → then the
  rest. Styles are allowlisted keys owned by the platform
  (`app/ai/styles.py`, `GET …/ai/styles`) plus a bounded, untrusted `style_note`
  that rides the image prompt as data, with the no-text/no-real-people
  guardrails appended AFTER it. Editing a beat's Illustration line unpairs its
  now-stale art. Frontend: `components/ai/StoryDraft.tsx` (the staged wizard),
  `AiVariants.tsx` (shared strip + steer box — the old text-variant preview read
  the wrong key and always rendered blank; fixed), style chips at input in
  `AiAssist`. **`AI_FAKE_IMAGES`** (dev only, refused in production) paints
  placeholder art in-process — the image twin of the offline `fake` text
  adapter — so this whole stage demos and browser-smokes for free; the UI only
  offers the paid buttons when `AiCreditsInfo.images_available` says the server
  can actually illustrate. Tests: `tests/test_ai_staged_story.py` (13) + the
  rewritten image block of `test_ai_media_guests.py`.
- [x] **8.5c Guests: spreadsheet routing + ask-back — DONE (local) 2026-07-13.**
  The Guests tab now has ONE way in (`components/admin/GuestsIntake.tsx`):
  paste it, photograph it, or drop the spreadsheet, and the routing is done FOR
  the couple. A real sheet goes to the **existing deterministic importer** (a
  parser — no model, no credits; `SheetImport.tsx` runs the same server dry-run →
  preview → commit, and the `Id` column still makes an edited export an update);
  everything else goes to the `guests` run. `AiAssist` gained `routeFiles`, a
  last chance for the parent to claim a submission *before* a job exists — the
  cheapest run is the one that never happens. If the sheet turns out not to be
  our layout, the importer offers the assistant as a fallback rather than an
  error. A sheet handed to the AI path still reaches **no provider**:
  `app/ai/sheets.py` flattens it in code (bounded rows/cols/cells), so the sheet
  kind sits on the far side of the transcribe gate and works with
  `AI_LIVE_CALLS=false`. **Ask-back:** `GuestLines` gained a bounded `questions`
  list, and an ambiguous line ("Sam's parents") now comes back as a QUESTION
  instead of a guess — and is **held out of the drafted guests**, because a
  proposal that asks about the Okonjo family *and* invents a solo guest of that
  name has answered its own question wrongly. The job parks with the partial
  list + the questions (`components/ai/GuestQuestions.tsx`); the couple answers
  inline; `POST …/ai/jobs/{id}/answers` (`app/ai/askback.py`) appends the
  answers as an ordinary `AiInput` (swept with the job) inside
  `<clarifications>` tags and runs **ONE** final re-extract — `final=True`, so
  it cannot ask again (hard cap: 2 rounds; a workflow, not a chat). Answering is
  **free** (we're asking because we were unsure; the ledger still records the
  call), unanswered questions leave their line in `guests_unresolved` rather
  than invented, and a failed re-read destroys nothing — round one's list is
  still sitting there, still applicable. Tiers remain 100% deterministic: no
  answer, however phrased ("give them all a plus one!"), can reach an
  `invite_tier` — they come from the markers in the returned lines, in code.
  Tests: `tests/test_ai_guests_askback.py` (13).
- [x] **8.5d Likeness — DONE (local) 2026-07-14.** The couple can be IN the
  illustrations: they attach photos of themselves and the panels are drawn to
  look like them — still illustrations, never photographs. It is the one feature
  shipping ahead of its legal framing (RT, 2026-07-12), so the mechanism is
  small, off by default (`ai_likeness_enabled`), and stoppable. **Consent is a
  property of the file**: it rides the upload that carries the photo and lands on
  the row (`role` / `consent_at` / `consent_by`, migration `d0e1f2a3b4c5`), and
  `consented_references()` is the single predicate every caller passes through —
  a row without consent isn't "a photo you may not use", it simply isn't a
  reference, so no downstream path can hand it to the image model by accident
  (an unconsented id at the references endpoint answers **404**: there is no
  reply that reveals the photo exists). **A face is not source material** — a
  `role="reference"` input is skipped by transcribe (captioning it would push a
  description of the couple's bodies into the extraction prompt for nothing) and
  reaches exactly one call, `GeminiMedia.generate_image`, where it swaps the
  no-recognisable-people guardrail for the likeness direction. **Stylised only:**
  the photographic preset is refused where the style is *chosen* (422, naming the
  way out) and silently downgraded where the prompt is *composed* — the second
  gate is the one that holds if a future path forgets the first. Losing the
  entitlement mid-run stops the render with a 403 that says "remove your photos"
  rather than quietly drawing strangers into a panel they'd have paid for. The
  photos never outlive the run (`POST …/references []`, cancel, expire, apply and
  the sweeps all delete row + stored object). SynthID disclosed in the UI. New:
  `app/ai/likeness.py`, `POST …/ai/jobs/{id}/references`, `role`/`consent` on the
  upload endpoint, `likeness_available` + `max_likeness_references` on credits,
  `likeness_blocked` on the style chips, `components/ai/LikenessPhotos.tsx`.
  Tests: `tests/test_ai_likeness.py` (14).
- [x] **8.5e Theme presets — DONE (local) 2026-07-14.** ~10 platform-curated
  looks on the wedding Theme tab (`app/theme_presets.py`: the code-default
  catalogue + validation), stored as a `platform_settings['theme_presets']` blob
  with the same never-brick stance as prompts/entitlements (missing/broken blob
  → code defaults; one rotten entry is skipped, the rest still serve; an
  admin-emptied catalogue is a *choice*, not a fault). Validation is deliberately
  narrow — hex colours, the numeric knobs, and **only the fonts next/font
  actually loads** (a preset naming an unloaded family would silently render the
  fallback stack, so it's refused). The couple's Theme tab reads the active list
  (`GET …/theme/presets`, disabled withheld, swatches derived from the colours
  when the console didn't pick them) and **applying one COPIES the tokens** onto
  the wedding (`POST …/theme/preset`, replace-not-merge so no leftover of the old
  look survives) — nothing links back, so a later console edit or delete can't
  reach into a wedding that already applied it, and every token stays editable on
  top. Platform console gains a **Themes tab**
  (`components/platform/ThemesTab.tsx`: whole-catalogue GET/PUT so reorder /
  disable / delete / edit is one audited save; the couple's
  `components/admin/ThemePresets.tsx` cards fold into `ThemePanel`'s hand
  editor). Tests: `tests/test_theme_presets.py` (24).
- [x] **8.5 Guided wizard (plan FINAL 2026-07-12, see `AI_WIZARD_PLAN.md`
  Phase 8.5; build order a→e) — ALL SLICES DONE (2026-07-14).**
- [ ] **Blocked on RT:** Anthropic API key (Places + OpenAI + Gemini keys
  landed 2026-07-12, all live-verified; run the golden set on the Anthropic
  adapter once its key exists — it is the configured default text
  provider); decision on forcing AI-drafted weddings through the approval
  queue; likeness legal framing before public launch.

## Test & verification status (2026-07-14, post-8.5e)

- `pytest`: **458 passed, 1 skipped** (434 + `test_theme_presets.py` 24). The
  new suite pins what 8.5e promises: ten presets ship in code and all validate; a
  preset can only name fonts the app loads; the Theme tab never bricks (defaults
  when nothing is stored, defaults on a structurally broken blob, one rotten
  preset skipped while the rest serve, and an *emptied* catalogue stays empty
  rather than resurrecting the defaults); the console sees disabled presets and
  the couple does not; one save is reorder+disable+delete; bad presets are
  refused with a reason (hex / unknown colour / can't-set-shadows / bad slug /
  out-of-range / empty tokens) and duplicate ids rejected; every catalogue save
  is audited; swatches are derived when the console didn't choose them; **applying
  a preset REPLACES the theme** (pick Midnight, get Midnight — no magenta
  leftover) and a hand edit then layers on top; editing or deleting a preset
  afterwards never touches a wedding that took it (apply copied); a
  disabled/unknown preset 404s on apply; and the full authz matrix (catalogue is
  platform-admins-only; a non-member can't see or apply a wedding's themes; a
  suspended wedding reads but can't apply). The shipped catalogue is proven
  immutable-by-a-read (deepcopy, not a shared nested dict).
- E2E smoke: **25/25** (21 + 4 for 8.5e) in a real browser — the platform
  console Themes tab renders the catalogue editor, the couple's Theme tab offers
  the preset cards, and applying Midnight & gold is API-verified to copy its
  primary (`#D9B26A`) onto the wedding. `tsc`/`eslint`/`next build` clean; OpenAPI
  + API types regenerated.

## Test & verification status (2026-07-14, post-8.5d — kept for history)

- `pytest`: **434 passed, 1 skipped** (419 + `test_ai_likeness.py` 15). The new
  suite pins what 8.5d promises: likeness is off in `DEFAULT_ENTITLEMENTS`; an
  upload without the box ticked is refused AND leaves nothing stored; consent is
  recorded on the row (who + when); an unconsented or cross-tenant photo id is a
  404 at the references endpoint; consented photos ride the image call and swap
  the faceless-figures guardrail for the likeness direction, while the text model
  never sees them at all; a redo of a panel keeps the couple in it; the
  photographic style is refused when photos are attached (both orderings) and
  degrades rather than renders if it somehow gets stored; revoking the plan
  mid-run stops the render (nothing charged) and the way out still works with the
  feature off; the plan's photo cap holds even for references claimed straight at
  job creation (the render path enforces it, not just the endpoint); and the
  photos never outlive the run — cancel and apply delete row and stored object
  while the illustration they produced survives.
- Three bugs the self-review caught before commit, each now pinned by a test or
  a comment: the "remove your photos" way out 403'd because removal required the
  same entitlement that had just been revoked; reference photos claimed via
  `create_job`'s `input_ids` bypassed `ai_max_likeness_references` (the endpoint
  was the only gate); and hoisting the Gemini SDK type import above `_get_client`
  turned "SDK not installed" from a friendly degrade-to-text-only into a 500.
- AI smoke: **57/57** (53 + 4 for 8.5d), backend on `AI_LIVE_CALLS=false
  AI_FAKE_IMAGES=true` — in a real browser: the upload is locked until the
  consent box is ticked (tested on the file INPUT, not the label's CSS — see
  LEARNINGS), a consented photo attaches, the server records it against the job,
  and the Photographic chip is withdrawn while it's attached.
- E2E smoke: **21/21**, unchanged by 8.5d. `tsc`/`eslint`/`next build` clean;
  API types regenerated.

## Test & verification status (2026-07-13, post-8.5c — kept for history)

- `pytest`: **419 passed, 1 skipped** (406 + `test_ai_guests_askback.py` 13).
  The new suite pins what 8.5c promises: a spreadsheet is read by a parser and
  reaches no provider even with the AI seam off (and the upload endpoint takes
  it while refusing a voice note in the same configuration); an ambiguous line
  parks as a question BESIDE the partial list and is not drafted as a guest;
  answering re-extracts exactly once, free, with the answers riding the user
  turn as data; an unanswered question leaves its line unresolved; a failed
  re-read keeps round one's list intact; and no answer can reach an
  `invite_tier`.
- AI smoke: **53/53** (46 + 7 for 8.5c), backend on
  `AI_LIVE_CALLS=false AI_FAKE_IMAGES=true` — the sheet route imports a CSV with
  the credit balance API-verified unchanged, and the messy paste asks about the
  line it can't read, takes an answer, and applies with tiers from the markers.
- E2E smoke: **21/21**, unchanged by 8.5c. `tsc`/`eslint`/`next build` clean;
  API types regenerated.

## Test & verification status (2026-07-13, post-8.5b — kept for history)

- `pytest`: **406 passed, 1 skipped** (393 at 8.5a + `test_ai_staged_story.py`
  13). The new suite pins what 8.5b actually promises: a story run parks
  text-only (no image call, no image credit); a hand edit is free, re-validated
  through `DraftArc` (long/empty/extra-field edits are 422s), flagged in
  `user_edited`, and drops the grounding claim on the line it rewrote; images
  charge 1 credit each and stop at the balance BEFORE the provider call; the
  style note reaches the image prompt and never the story text, and an unknown
  style key falls back instead of failing; the dev painter cannot exist in
  production and a real Gemini key is never shadowed by it. The image block of
  `test_ai_media_guests.py` was rewritten around `/illustrate` (batching,
  ledgering, metering, per-arc cap, refusal → text-only panel, cancel refunds +
  sweeps, apply writes beat AND climax art and sweeps the unkept).
- AI smoke (`node scripts/smoke-ai.mjs`, backend started with
  **`AI_LIVE_CALLS=false AI_FAKE_IMAGES=true`**): **46/46** — the staged story
  wizard in a real browser with API-verified writes (text-only park → free hand
  edit saved and flagged → first image → the rest incl. the climax → apply,
  with the applied arc keeping the couple's words and the climax art).
- E2E smoke (`node scripts/smoke-e2e.mjs`): **21/21**, unchanged by 8.5b.
- Frontend: `tsc --noEmit`, `eslint .`, `next build` clean; API types
  regenerated.

## Test & verification status (2026-07-12, post-8.5a — kept for history)

- `pytest`: **393 passed, 1 skipped** (369 at 8.5a + `test_ai_config.py` 12 and
  `test_ai_console_model.py` 12 from the config/console work of 2026-07-13).
  8.5a reshaped the AI tests around the
  kind split: `test_ai_pipeline.py` gains `test_details_run_extracts_event_
  facts_only` (3 steps, ONE model call, no story in the proposal) and its
  happy path becomes a `story_arc` run; `test_ai_api.py` proves the two
  independent HTTP gates (details apply → venue; story apply → arc) plus
  `test_details_proposal_cannot_write_a_story` (SECTIONS_BY_KIND is per-kind,
  not per-proposal); `test_ai_guardrails.py`'s end-to-end apply now covers
  both kinds.
- AI smoke (`node scripts/smoke-ai.mjs`, backend started with
  **`AI_LIVE_CALLS=false`** — the one switch that also holds back the real
  Places + Nano-Banana keys in `backend/.env`): **40/40** — the whole 8.5a
  funnel in a real browser with API-verified writes (details run on the Details
  tab → venue persisted; story on Story; mark on AI; guests on Guests;
  `/create` → `/setup` → three skippable steps → dismissed checklist).
- E2E smoke (`node scripts/smoke-e2e.mjs`): **21/21**, unchanged by 8.5a.

## Test & verification status (2026-07-12, post-8.1c — kept for history)

- `pytest`: **367 passed, 1 skipped** (offline, in-memory SQLite; the skip is
  the golden-set "no recordings" notice, which self-disables once
  `evals/recordings/` exists). Phase 8.1c additions:
  `test_ai_media_guests.py` (19 — media upload authz/caps/no-key, transcribe
  ledgering + refusal sweep incl. stored-object deletion, images fan-out
  partial progress/cap/refusal/no-key/cancel-refund/apply-sweep, guests
  deterministic tiers + tamper-proof apply + max_guests re-check, beat-image
  regen/select over HTTP, per-image pricing, Gemini request-shape pin) and
  `test_ai_golden_replay.py` (re-judges recorded eval runs offline).
- Golden-set eval (`scripts/eval_golden.py`): run LIVE on `openai`/`gpt-5.1`
  (recording in `evals/recordings/`); the run itself surfaced and fixed two
  adapter bugs (reasoning-token truncation; snapshot-id → $0 pricing). Gemini
  seam live-checked (transcribe + one generated image). Anthropic run owed
  when its key lands.
- AI smoke (`node scripts/smoke-ai.mjs`): **23/23** — adds attach-files
  control, guests run → review tiers → apply → API-verified rows
  (`plus_one`/`plus_family` from raw `+1`/kid markers).
- E2E smoke (`node scripts/smoke-e2e.mjs`): **21/21**.
- Frontend: `tsc --noEmit`, `eslint .`, `next build` clean; API types
  regenerated from `openapi.json`.

## Test & verification status (2026-07-12, pre-8.1c — kept for history)

- `pytest`: **346 passed** (offline, in-memory SQLite) — includes the
  authz matrix, lifecycle, members, platform console, entitlements, and the
  pre-platform suites migrated to wedding-scoped paths. Cross-tenant
  negatives throughout (`test_identity_authz.py` is the status-code spec).
  Review-P0 additions: query-count guards (`test_query_efficiency.py`),
  introspection cache, rate limiting, emailer seam. Review-P2 additions:
  `test_p2_hardening.py` (races → 409, invite merge, JSON bounds, import
  caps, profile commit discipline, tz helpers, RSVP deadline). Phase 8.0
  additions: `test_ai_models.py` (one-active-job index, idempotency key,
  purge-vs-ledger, prompt composite key, AI entitlement defaults) and
  `test_ai_provider_port.py` (prompt resolution/rendering, fake + Anthropic
  adapters, factory, pricing, ledger) and `test_ai_pipeline.py` (creation
  gates, full wizard run to proposal, step replay, glyph, refusal/cancel/
  expiry refunds). Phase 8.3 additions: `test_ai_guardrails.py` (sanitiser
  vs real script/onload/url(#)/entity payloads, hostile-proposal apply
  non-writes incl. invite_tier, apply-time entitlement + banned-word
  re-checks, ceiling queues-not-fails, reap + cron-secret endpoint). Phase
  8.4a additions: `test_ai_api.py` (per-endpoint 401/404 authz matrix,
  HTTP-level wizard→apply, regeneration/variants/selection, platform AI
  console).
- Frontend: `tsc --noEmit`, `eslint .`, `next build` clean.
- E2E smoke (`node scripts/smoke-e2e.mjs`, needs both dev servers +
  `scripts.dev_setup`): **20/20** — three tier invites, solo tier-invisibility,
  full family RSVP persisted, landing, dashboard, wedding admin (lifecycle
  strip, Team tab), platform console.
- AI smoke (`node scripts/smoke-ai.mjs`, same prerequisites +
  `AI_TEXT_PROVIDER=fake`): **17/17** — the whole 8.4b surface in a real
  browser with API-verified writes (see the 8.4b entry above). Note the
  fake's demo cycles are per-backend-process: `rm dev.db` + reseed gives a
  deterministic run.

## Infrastructure TODO (when RT provisions accounts)

1. Supabase project → run `alembic upgrade head`, configure Google OAuth +
   email/password with verification, storage bucket, env vars; seed RT's
   platform-admin row.
2. Vercel frontend + backend projects (hnd1), env vars, WAF rate rules (P1-2);
   cron entries with `Authorization: Bearer $CRON_SECRET` (backend code paths
   are in): `/api/internal/cron/purge-archived` daily,
   `/api/internal/cron/reconcile-storage` weekly,
   `/api/internal/cron/reap-ai-jobs` hourly (stuck AI jobs expire after 2 h).
3. Email provider (Resend) → code path is in (`RESEND_API_KEY` + `EMAIL_FROM`
   env vars); create the account + verify the sending domain.
4. Sentry: create the project(s) and set `SENTRY_DSN` (backend init is in);
   add `@sentry/nextjs` to the frontend; uptime check on `/health` (now pings
   the DB — alert on `status: degraded`).
5. Staging Supabase + Vercel preview envs; PITR/backups on from first real user.

## Decisions log
- **2026-07-10 (RT):** per-guest story hiding — `guests.story_arc_ids` became a
  tri-state (null = all visible arcs / [] = story hidden for that guest /
  ids = only those); invite payload gained `show_story`; guest dialog's
  "Story visibility" control replaces the old >1-arc-only override select.
  Verified visually via headless-Chrome script (16 checks incl. no dead
  #story anchors, cover cue retargets to #day).
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
