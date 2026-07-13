# LEARNINGS

Locked decisions and hard-won gotchas for **saas-events**. Newest first.
Entries below the "Carried over" line were curated from the predecessor
single-wedding build (full history lives in that private repo); everything
above it is new to the platform.

## 2026-07-12 — AI wizard 8.1c: media/images/guests + what the golden set caught
**Reasoning/thinking tokens eat the output budget — the eval caught it live.**
The first golden-set run against gpt-5.1 at effort=high truncated 10/12 drafts:
`max_output_tokens` includes reasoning tokens, so a 4096 budget was consumed
before the JSON finished. Both adapters now add effort-scaled headroom
(low/medium/high → +2048/4096/8192) on top of `prompt.max_tokens`; the same
rule applies to Claude adaptive thinking (counts against `max_tokens`). This
is exactly the class of regression the eval exists to catch — run
`scripts/eval_golden.py` before ANY provider/model change in production.

**`response.model` is a dated snapshot id — price by the REQUESTED id.** The
API answered `gpt-5.1` requests with a snapshot id that missed the
per-(provider, model) price table, so every call ledgered an auditable-but-
wrong $0. Usage rows now record the requested config id (both adapters).

**Gemini's image model returns JPEG, not PNG (verified live).** Never assume
the output format — `sniff_image_mime` reads the magic bytes before
prepare/store, or you ship JPEG bytes under a `.png` name.

**A pipeline step that repeats must key the client loop on object identity.**
The images fan-out advances a couple of beats per /advance and stays on the
same `job.step`; `AiRunProgress`'s effect originally depended on `job.step`
and silently stalled mid-step. Depend on the fresh job object each response.

**Transient AI-input media lives OUTSIDE the metered namespace.** Uploads go
under `ai-inputs/<slug>` so `measure_wedding_media`/the reconcile cron never
count PII that the reap sweep deletes; generated beat art goes in the normal
namespace and IS metered (with bytes tracked in job.state so cancel/apply
sweeps can refund the counter). Deleting an AiInput row must always delete
its stored object in the same breath.

**The apply allowlist is now also kind-scoped.** `SECTIONS_BY_KIND` means a
wizard proposal smuggling a `guests` key writes no guests — the hostile-
proposal test caught the widening the moment the guests writer landed.
Guests apply recomputes tiers via `infer_tier()` from bounded companion
counts; the proposal's own `invite_tier` strings are never read.

## 2026-07-12 — AI wizard 8.4b: UI + offline-dev gotchas
**A per-request provider dependency means no per-instance state in adapters.**
`get_job_text_model` constructs a fresh adapter every request, so the fake's
demo "variety" cycles had to be module-level — as first written (cycles inside
`demo_responses()`) every regeneration returned content identical to the
original, and only the E2E smoke caught it (the API tests script their own
fake). Same trap for anything else an adapter might "remember" across calls.

**Don't re-derive the in-focus job from the jobs list after apply.** AiPanel's
first post-apply refresh reset `job` from `listJobs()` (no active job → null),
which unmounted the review panel's success state — including the "use it as
your cover icon" switch — before it could be used. Refresh the list and
credits; leave the job object the panel is showing alone.

**The AI mark renders via `dangerouslySetInnerHTML` — safe ONLY because the
stored form is sanitised.** The pipeline runs the allowlist-rebuild sanitiser
before anything is persisted, and `content.brand.icon_svg` is written
exclusively by the apply path. `GlyphMark`/`Wordmark` must never be handed raw
model output, and nothing else may write that key. `icon_mode: "svg"` without
a stored mark falls back to the default glyph (parse-time, like
custom-without-url).

**E2E text assertions on MUI need the innermost element.** `clickText("div",
"Version 2")` matches the outermost container first (textContent includes the
whole subtree) — click the chip label's `closest(".MuiPaper-root")` instead.
And "an svg exists on the cover" was a false-positive check (the built-in cat
glyph is also a 100×100 svg); assert against the stored `icon_svg` content.

## 2026-07-11 — AI wizard 8.4a: API-surface decisions
**Selection writes into the proposal, so apply never learns variants exist.**
`select_variant` copies the chosen `ai_variants` row's content into
`job.proposal` and the apply allowlist stays exactly as 8.3 shipped it — one
reviewable surface, one writer path. The original output is seeded as
variant 0 on first regeneration, so "regenerate" can never destroy the
version the couple preferred. And a regenerated draft gets a fresh grounding
pass: it can invent facts exactly like the first one.

**The provider seam doubles as a FastAPI dependency.** The advance/regenerate
endpoints take `text_model = Depends(get_job_text_model)`; tests override
that one dependency to inject a scripted FakeTextModel — no config contortion,
and it's the same seam a real provider swap uses. Related: for the authz
matrix test, nonexistent job UUIDs are fine — `require_wedding` fires before
any path-param lookup, so 401/404 assertions don't need fixtures per endpoint.

**Failed regenerations keep their ledger rows.** A refusal mid-regen (draft
succeeded, grounding refused) still spent real dollars — commit the staged
`ai_usage_ledger` rows before raising, but never move the couple's credits.
Charging (`job.credits_held += 1`) happens strictly after generation succeeds.

## 2026-07-11 — AI wizard 8.3: guardrail decisions
**Sanitise model SVG at BOTH ends, and never filter — rebuild.** `app/ai/svg.py`
parses with defusedxml and constructs a NEW tree from the element/attribute
allowlist (anything else — script, on*, style, href, url(#), text nodes,
namespaces — never exists in the output, so there's nothing to pattern-match).
It runs inside the glyph pipeline step (the review UI must never render raw
model output) AND again in `apply` (a proposal is stored JSON that could have
been written by an older/buggier pipeline; its `sanitised: true` flag is data,
not proof). An unusable mark = a failed, refunded generation — never "render
it anyway".

**The daily cost ceiling must queue, not fail.** Tripping
`ai.daily_cost_ceiling_usd` raises 503 (+Retry-After) with NO job-state
change, so the run resumes when the window/ceiling clears; the reap cron is
the net that eventually expires-and-refunds a job that never resumes. If the
ceiling marked jobs failed, a platform-wide budget event would consume every
in-flight couple's held credits.

**Apply is a dispatch table of writers, not a merge.** `apply.py` maps each
allowlisted section to an explicit writer function; unknown proposal keys are
unreachable by construction (the hostile-proposal test pins slug/status/
published/invite_tier/settings/theme as non-writable). Deep-copy
`wedding.content`, mutate, reassign — same SQLAlchemy JSON trap as ever.

## 2026-07-11 — AI wizard 8.1b: pipeline gotchas
**Order the friendly gates before the money math.** The one-active-job rule
is enforced by the DB partial index, but with only that, a second create
surfaced as 403 "out of credits" (the free-arc allowance was consumed by the
active job) instead of 409 "already running". `create_job` now does a cheap
active-run SELECT before `compute_hold`; the index stays the backstop that
holds under concurrent instances. General rule: user-facing precondition
checks in intent order, DB constraints as the race net.

**JSON columns don't track in-place mutation.** Every step builds
`state = dict(job.state or {})`, mutates the copy, and REASSIGNS `job.state`
— editing the dict in place silently persists nothing (same SQLAlchemy trap
as `wedding.settings`).

## 2026-07-10 — AI wizard 8.1: provider-port decisions
**Adapters never leak SDK exception types.** The pipeline has exactly one
failure path (job → failed, hold refunded), so `app/ai/types.py` defines
`ProviderError`/`ProviderRefusal` and every adapter maps into them. Tests
stub the SDK client (injectable constructor arg + lazy import) — the whole
suite runs without the `anthropic` package installed.

**Anthropic request shape pins that will bite if forgotten (Opus 4.8):**
`thinking: {"type": "adaptive"}` must be EXPLICIT (omitting = no thinking);
`temperature`/`top_p`/`top_k` all 400; effort lives in `output_config`;
a refusal is HTTP 200 with `stop_reason == "refusal"` — check before reading
content; min cacheable prefix is 4096 tokens (below = silent no-op). Pinned
in `test_ai_provider_port.py::test_anthropic_adapter_request_shape…`.

**Unknown model in the price table records cost 0, never guesses.** The
ledger is append-only money-at-write-time; a silent wrong price is worse
than an auditable zero + a `ai.pricing.unknown_model` log line.

## 2026-07-10 — AI wizard 8.0: schema gotchas
**Postgres forbids NULL in primary-key columns.** The plan's `ai_prompts`
"(key, provider, version) PK with provider = NULL as the shared fallback"
can't exist — a unique constraint would treat NULLs as distinct (dup fallback
rows) and a PK rejects NULL outright. The fallback row uses `provider = ''`
(NOT NULL, server_default `''`). Same trap applies to any future "nullable
discriminator in a composite key" design.

**Partial unique indexes work — and are testable — on SQLite.** The
one-queued/running-job-per-wedding ceiling is
`Index(..., unique=True, sqlite_where=..., postgresql_where=...)`; both
dialects enforce it, so the DB-level concurrency guarantee is pinned by an
offline test (`test_ai_models.py`) instead of being a Postgres-only hope.

**Append-only money/audit tables must be excluded from the purge cascade.**
`ai_usage_ledger` deliberately has NO `Wedding` relationship (ORM cascade
would delete it with the tenant); purge nulls its `wedding_id`/`job_id`
explicitly, mirroring the `audit_log` treatment, because SQLite dev runs
don't enforce FK `SET NULL`.

## 2026-07-10 — P2 hardening gotchas
**`IntegrityError` fires at flush, not just commit.** Guarding `db.commit()`
with try/except misses constraint violations raised by an explicit or
auto-flush earlier in the handler (`create_wedding` flushes to get the id, the
import loop flushes per row). Hot paths wrap the whole insert block for a
specific 409 message; `app/main.py` adds an app-wide `IntegrityError → 409`
exception handler as the backstop so no check-then-insert race can ever
surface as a 500.

**Bound free-form JSON at the schema edge, and check depth BEFORE recursing.**
`_check_json_bounds` (schemas.py) rejects >16 deep / >25k nodes / >50k-char
strings on every owner-editable blob. Because every write is bounded, the
stored blob stays bounded too, which is what keeps `_deep_merge` (recursion
follows the patch) safe — no need to re-validate on read.

## 2026-07-09 — Phases 1–5: identity/tenancy build gotchas
**Server log lines must be ASCII.** A `print(f"[email → …]")` in the emailer
500'd `submit-approval`/`approve` on the live server (Windows console =
cp1252; `→` raises `UnicodeEncodeError`) while every test passed — tests
don't print to a real console. Committed state + failed response = confusing
half-applied transitions. `send_email` now encodes ASCII-with-replace inside
try/except; treat any post-commit side effect (email, logging) as
must-never-raise.

**Local multi-user auth without Supabase:** the dev bearer token grew a
composite form — `<token>` = the bootstrap platform admin (sub `dev`),
`<token>:<email>` = an ordinary user (sub `dev:<email>`). All membership /
cross-tenant / invite flows are exercisable offline; tests in
`tests/helpers.py` (`platform_auth()` / `user_auth(email)`) build on it. The
composite compare is still `secrets.compare_digest`, still refused in
production/Vercel.

**One module-level `setAdminWedding(slug)` beats threading a prop through 17
panels.** The admin panels all import the `adminApi` singleton; the
`[weddingSlug]` route sets the slug once (render-time side effect, idempotent,
one dashboard mounted at a time) and `req()` builds
`/api/w/{slug}/admin/...`. If dashboards ever render side-by-side this must
become context/per-instance clients.

**Next route-segment config can't be re-exported.** The wedding-scoped invite
route (`/{weddingSlug}/i/[guestSlug]`) re-exports the canonical page component
+ `generateMetadata`, but `export { dynamic } from ...` is a build error —
declare `export const dynamic = "force-dynamic"` literally in each route file.

**Authz status-code contract (pin it in tests):** unauthenticated 401; a
non-member gets 404 (never confirm a wedding exists); a member below the
required role gets 403; suspended = reads OK / writes 403; archived = 404 for
members, visible to platform admins. `tests/test_identity_authz.py` is the
spec.

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

## Serverless + NullPool makes lazy loading a footgun
Any endpoint whose serializer walks ORM relationships (rsvp → companions →
answers) MUST `selectinload` them: on local SQLite the N+1 is invisible, but
each lazy load is a full round-trip to the Supabase pooler from a serverless
function (NullPool, no cache) — a 200-guest list turns into ~600 queries.
`tests/test_query_efficiency.py` pins the SELECT count per hot endpoint so a
regression fails the suite instead of shipping slow.

## Module-level caches need a test-reset seam
The auth introspection cache and rate-limit buckets are module-level (right
for serverless: per-instance is the scope you want), but tests reuse the same
bearer strings and client IP — an autouse conftest fixture clears both between
tests or results bleed across files. Cache only SUCCESSES keyed by token
hash; failures must always re-verify.

## The alembic chain doesn't run on a FRESH SQLite database
`migrations/versions/9a4e0c2acead_initial_schema.py` uses Postgres-only
`server_default=sa.text('now()')`, so `alembic upgrade head` on a brand-new
SQLite file fails in the very first migration. This has always been true:
local SQLite is created by `scripts.dev_setup` (metadata `create_all`), and
alembic is only ever run against Supabase/Postgres. Keep new migrations
additive and dual-dialect anyway (plain `add_column` is fine), and don't burn
time "fixing" a fresh-SQLite alembic run unless we decide to support it.

## Scheduler-driven endpoints: shared-secret internal routes
Vercel cron can't hold a Supabase session, so machine-to-machine jobs live
under `/api/internal/*` gated by `Authorization: Bearer $CRON_SECRET`
(constant-time compare; unset secret → neutral 404 so the surface doesn't
exist until ops enables it). Cron only issues GETs — register GET alongside
POST. The purge job (`app/purge.py`) is the pattern to copy.

## A terminal job status will unmount your review UI if you refetch
The AI review panel lives inside whichever component owns the `job` state. That
owner typically revives an in-flight run by refetching the job list and picking
the ACTIVE one (`queued`/`running`/`awaiting_review`). Do NOT run that same
refetch in the apply callback: `applied` is a terminal status, so the run drops
out of the active list and the panel unmounts *the moment the couple hits
Apply* — the success banner (and the glyph's "use it as your cover icon"
switch, which lives in it) flashes and vanishes. Keep the applied job in local
state and let the user dismiss it ("Start another"). `AiPanel` carried a comment
about this; `AiAssist` re-learned it the hard way, and the smoke caught it only
because the API check passed while the UI check failed — a combination worth
treating as a signal, not a flake.

## Local `.env` keys make "offline" smokes spend real money
`backend/.env` holds real `GEMINI_API_KEY` / `GOOGLE_PLACES_API_KEY`. Setting
only `AI_TEXT_PROVIDER=fake` fakes the *text* model — the pipeline still calls
Google Places in `resolve` and Nano Banana in `images`. Run browser smokes with
those two vars blanked as well (`AI_TEXT_PROVIDER=fake GEMINI_API_KEY=
GOOGLE_PLACES_API_KEY= …uvicorn`); the pipeline degrades cleanly (venue keeps
the couple's own words, beats stay text-only) which is exactly what the fake
fixtures expect. The tell was a smoke asserting "Fern Hall" and getting the very
real "Fern Hall Estate".

## Puppeteer leaf-only text matching misses `<strong>Label:</strong> value`
The smokes' `visibleHas` only scans elements with no element children, so a
`<Typography><strong>Venue:</strong> Fern Hall</Typography>` is invisible to it
(the leaf `<strong>` holds only "Venue:"). Use a `document.body.innerText`
check for strings that straddle inline markup.
