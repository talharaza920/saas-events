# Plan — architecture & milestones (inherited from the predecessor build)

_Approved by RT 2026-06-09 (incl. multi-tenant-ready constraint). The full
approved plan also lives at `~/.claude/plans/wiggly-leaping-panda.md`._

## Stack (RT defaults + deploy runbook)

Following `rt-code-preferences` + `rt-basic-app-deploy`:

- **Frontend:** Next.js (App Router) + **TypeScript** + **MUI**. Theme is data:
  `frontend/theme/defaultTheme.config.ts` (seed template) merged with a wedding's
  stored `theme_tokens` via `buildTheme.ts` → `ThemeProvider`. Guest invite at
  `/i/[guestSlug]`; owner dashboard at `/admin`.
- **Backend:** **FastAPI** (Python), tenant-aware. Light service: guest/link
  resolution, wedding content/theme fetch, RSVP submission, question CRUD,
  owner-scoped admin endpoints. Emits OpenAPI → `frontend/types/api.ts`.
- **DB + Auth:** **Supabase** (Postgres + auth). Owners sign in (v1: RT only).
  Guests do **not** log in — signed per-guest links. **RLS** isolates tenants.
- **Hosting:** Vercel (frontend + serverless FastAPI) — only when RT asks.

RT confirmed the **standard FastAPI stack** (not Next.js-only).

## Multi-tenant-ready, single-tenant build

Build behaves as one wedding now, but the foundations are multi-tenant so it can
become a platform (any couple signs up, configures, themes, uploads, shares).
**Now:** root `weddings` tenant table + `wedding_id` on every table (v1 = 1 seeded
row); Supabase **RLS**; page content + theme stored as **data** on the wedding
(seeded from `defaultTheme.config.ts` / DESIGN.md), never hardcoded; images in
Supabase Storage namespaced per wedding; `weddings.owner_id` → auth user;
`/i/{globally-unique guestSlug}` routing that already carries the tenant.
**Deferred platform milestones:** self-serve signup/onboarding, in-app theme
editor, template gallery, photo-upload UI, custom domains, billing,
**per-wedding favicon** (the browser-tab icon is one static, app-level
`frontend/app/icon.svg` today — the brand cat glyph; per-tenant it should be
driven by `content.brand.icon_url` via the `/i/[slug]` route's `generateMetadata`
`icons`, falling back to the default glyph — same pattern as the per-wedding
title/description added in M10 Phase 4c).

### Admin roles — future two-tier model (additive, non-blocking)

RT wants two distinct admin levels eventually. Capture now so the build stays
forward-compatible; **do not implement yet** (v1 is one wedding, one owner).

- **Platform admin** (platform owner) — oversees the whole platform: approves /
  denies new-wedding creation requests, can act across tenants, platform ops.
- **Wedding owner / admin** — owns ONE wedding; manages its guests/content/RSVPs
  and can **nominate co-admins by email** for that wedding only.

**How today's build maps onto it (so the evolution is purely additive):**
- `weddings.owner_id` is already the **primary owner / creator** of a wedding.
  Co-admins arrive later via a new **`wedding_members`** join table
  (`user_id`, `wedding_id`, `role` ∈ {owner, admin}, `invited_email`, `status`)
  — additive, `owner_id` stays as the creator.
- The global **`ADMIN_EMAILS`** env allowlist (today's gate) becomes the
  **platform-admin** list, or graduates to a `platform_admins` table. Per-wedding
  access then = "platform admin (any) OR a `wedding_members` row for this
  wedding".
- New-wedding **creation requests**: a new `wedding_requests` table (or reuse
  `weddings.status` with a `pending` state) + a platform-admin approve/deny
  endpoint. Additive.
- **The single authz seam to change is `app/routers/admin.py:owner_wedding`**
  (swap the `owner_id ==` check for a membership check) plus a new
  `require_platform_admin` dependency. All existing tables are untouched; the
  migration is add-only. RLS policies extend by `wedding_members` membership.

## Data model — every table carries `wedding_id`

- **weddings** (tenant root): id, slug, owner_id, couple_names, event_details
  (venue/date/time/map JSON), content (story/dress/FAQ JSON), `theme_tokens`
  JSON, status. v1: one seeded row.
- **guests**: id, wedding_id, slug (globally unique), name, side, relationship,
  group, batch, invite_tier (`solo|plus_one|plus_family`), invited, seed_meta.
- **rsvps**: id, wedding_id, guest_id, attending, responded_at, dietary, notes.
- **companions**: id, wedding_id, rsvp_id, kind (`adult|child`), name, dietary.
- **questions**: id, wedding_id, prompt, qtype (`choice|text|yesno`), options[],
  required, visibility (`all|tier|guests`), visibility_ref, sort_order.
- **answers**: id, wedding_id, rsvp_id, question_id, value.
- **wishes**: id, wedding_id, guest_id?, name, message, approved.
- **RLS** policies isolate every table by wedding_id / ownership.

Seed: `seed_wedding.py` (default wedding content+theme) then `import_guests.py`
(map Side/Relationship/Group/Batch/Dietary/+1; infer tier from `+1`/kid rows;
default `solo`), all scoped to that wedding_id.

## Milestones (scoped for parallel / resumable work)

| # | Milestone | Parallel-safe | Depends |
|---|-----------|---------------|---------|
| 1 | Scaffold: Next.js+MUI, FastAPI, Supabase project, default theme config, docs, GitHub repo | — | — |
| 2 | DB schema + tenancy + RLS + migrations + seed_wedding + guest import | — | 1 |
| 3 | Backend API (tenant-scoped): resolve, wedding fetch, RSVP, questions CRUD, responses (OpenAPI → TS) | ✅ w/ 4 | 2 |
| 4 | Guest site shell + theme from stored content: Cover/Story/Day/Dress/FAQ (browser-verified) | ✅ w/ 3 | 1 |
| 5 | RSVP flow wired: name-gate, tier-driven +1/kids, custom questions, dietary, confirm | — | 3,4 |
| 6 | Admin/owner dashboard: guest list, link generation, question builder, responses + dietary summary, CSV | ✅ w/ 5 | 3 |
| 7 | Wishes/guestbook + polish + easter eggs | ✅ | 4 |
| 8 | Deploy to Vercel + Supabase (via `rt-basic-app-deploy`) when RT asks | — | 5,6 |
| 9 | **Gift section** (cash / PayNow / bank-transfer) — separate, later | ✅ | 4 |
| 10 | **Admin-configurable storyline / copy / styling** (3 phases) — see below | — | 6 |
| 11 | **Guest management overhaul** (schema + per-person RSVP, admin views, import/export; 3 phases) — see below | — | 6 |
| F | **Future platform** (signup, two-tier admin roles + co-admin nomination + wedding-creation approval, theme editor, templates, domains, billing) — now fully planned in **`docs/SAAS_PLAN.md`** (RT 2026-07-08: separate product/fork, path-based URLs, entitlements-before-payments; this repo stays the live wedding site, security fixes only) | ✅ | — |

### M10 — Admin-configurable storyline / copy / styling (in progress)

Makes the invite owner-editable from `/admin`, single-tenant build / multi-tenant
design. Full plan + decisions: `~/.claude/plans/buzzing-dancing-stream.md`. Three
sequential phases, each STOP-for-RT-verification:

1. **Story arc + editor + image upload (DONE).** New `story_arcs` table (one arc per
   row: `title/visible/sort_order/content`; numbered beats + optional unnumbered
   finale), seeded from the legacy `content.story` (Alembic `b1f2c3d4e5f6`). Image
   uploads via `app/storage.py` (local `/media` in dev, Supabase Storage in prod) +
   `POST /api/admin/upload`. Owner edits via `GET/PATCH /api/admin/content` (deep-
   merge) + `GET/POST/PATCH/DELETE /api/admin/story-arcs`. Invite returns
   `story_arcs` (visible, ordered); tier never leaks.
2. **Copy / details / theme editor (DONE).** `Details` + `Theme` admin tabs over the
   same `PATCH /content` (no new endpoints). `DetailsPanel` = accordion sections
   (names/cover, the day incl. MUI X DatePicker, dress writeup + wear/avoid token
   swatches, FAQ, RSVP microcopy, nav/footer), each saving its own deep-merged
   partial. `ThemePanel` = curated brand colours + heading/body font dropdowns
   (next/font-registered faces only) → `theme_tokens.{colors,typography}`, live
   preview. `seed_data.dress_code` gained `swatches_avoid`/`wear_label`/`avoid_label`;
   `DressCode.tsx` renders both swatch rows.
3. **Multiple arcs + per-invitee targeting + carousel (DONE — pending RT check).**
   `guests.story_arc_ids` (nullable JSON, Alembic `c2d3e4f5a6b7`); `tenancy.visible_arcs`
   honors it as a TRI-STATE (2026-07-10): null = all `visible` arcs; [] = the story is
   hidden for this guest (`show_story: false` on the invite payload — the page skips
   the section, its nav link and the cover's scroll cue); non-empty = exactly those
   ids, validated to the wedding, in sort order. `StoryPanel` manages arcs
   (add/duplicate/visible-toggle/reorder/delete, inline `ArcEditor`);
   `GuestFormDialog` has a "Story visibility" control (All / No story / Only
   specific arcs — the custom pick needs >1 arc); `Story.tsx` renders ≥2 arcs as a
   carousel. Targeting by arc id only — the tier is never the selector and the override
   never crosses the guest wire.
4. **Brand mark + remaining white-label copy gaps (added 2026-06-10, RT-requested).**
   A sweep for copy still hardcoded to one couple, all wired through the same data-driven
   `content` + `PATCH /content` (no new endpoints). Sub-items:
   - **4a Brand mark (DONE).** `content.brand` = `{wordmark_text, icon_mode, icon_url}`.
     The cover `Wordmark` ring text is editable and its center icon is configurable —
     `default` (built-in cat glyph) / `custom` (uploaded square raster, fit-contained) /
     `none`. New "Brand mark" section in the Details tab; raster-only upload reuses the
     Phase-1 pipeline (no SVG → no XSS surface). The spinning ring itself is untouched.
   - **4b Wishes copy (DONE).** `content.wishes` = `{kicker, heading, intro, name_label,
     message_label, button, success}`. `Wishes.tsx` was fully hardcoded (incl. a mascot
     mention) — now reads content with safe fallbacks; new "Wishes / guestbook" section in
     the Details tab.
   - **4c Per-wedding invite metadata (DONE).** `/i/[guestSlug]` got `generateMetadata`
     (title = `cover.kicker — couple_names`, description = `cover.tagline`/`invite_line`),
     deriving the browser tab + link/social preview from the wedding's own data instead of
     the hardcoded layout title. Kept couple-level (no guest name). `fetchInvite` wrapped in
     React `cache()` so metadata + page share one backend call.
   - **4d Cover kicker/tagline mismatch (DONE).** Both fields were editable in admin but
     never rendered; 4c gives them a real effect (they now drive the metadata), and their
     admin helper text says so — no change to the (liked) cover layout.
   - **4e RSVP step copy (DONE).** Moved the hardcoded `RsvpForm.tsx` chrome under
     `content.rsvp`: `steps` (per-step lead/title), `review_labels`, `buttons` and inline
     `labels` (incl. the attend-step validation and the +1/kids/dietary prompts).
     A shared `RSVP_DEFAULTS` in `lib/content.ts` is used by both the parser (render
     fallback, so a wedding seeded before 4e still renders) and the admin editor (prefill),
     so the two never drift; the nested types are `type` aliases (not interfaces) so they
     satisfy the `Record<string,string>` merge helper. New "RSVP steps & buttons" section in
     the Details tab; deep-merge means it never clobbers the mascot speech bubbles / choices.
5. **Story section label + wish approval flow (added 2026-06-10, RT-requested).** Two
   pre-deploy asks, both within the data-driven `content` pattern (no new endpoints).
   - **5a "Our story" section label (DONE).** `content.story_section` =
     `{visible, label}`. A small, owner-editable eyebrow above the whole story
     section — a muted letter-spaced uppercase label in `secondary.main` (subtle, so
     it doesn't compete with each arc's own kicker/heading). `Story.tsx` renders it
     above the single arc *and* the carousel, supplying the section's top padding so
     the body trims its own. New "Story section label" section in the Details tab
     (show/hide switch + text); blank label or switch-off hides it. Parser defaults
     `visible` true but also requires a non-blank label, so a pre-existing row is safe.
   - **5b Wish approval flow (DONE).** Guest wishes now arrive **unapproved** —
     `create_wish` sets `approved=False` (model default stays `True` for seed/owner
     rows). The public wall already showed `approved` only, and the moderation API
     already existed; `WishesPanel` was reworked (pending-count banner, Pending / On
     the wall chips, **Approve**/**Hide**). The guest success copy now says the wish
     is awaiting the couple's approval. So nothing shows publicly until the couple
     approve it from `/admin`.

Each milestone: library components + config theme, tests written & passing, UI
browser-verified, PROGRESS.md + LEARNINGS.md updated, committed & pushed, tagged
release with notes once tests pass (per skill Definition of Done).

### M11 — Guest management overhaul (in progress)

Richer guest/RSVP data + usable admin tooling for the real wedding. Single-tenant
build / multi-tenant design. Full plan + decisions:
`~/.claude/plans/zazzy-orbiting-honey.md`. **Schema = hybrid** (RT 2026-06-10):
`email`/`phone` (on `guests`) and `age` (on `companions`) are real columns; the rest
stays fixed-core-fields + per-wedding **config toggles** (`content.rsvp.fields`) +
the existing custom `questions`/`answers`. Three phases, each verified before the next:

1. **Schema + per-person RSVP capture (DONE).** Columns + Alembic `d3e4f5a6b7c8` +
   `app/validation.py` (E.164 phone via `phonenumbers`, email via `email-validator`).
   RSVP "who" step is now per-person (+1 name+dietary; each kid name + **required
   age** + dietary); validated email + intl phone (`mui-tel-input`) on the details
   step, prefilled + hydrated. Contacts stored on the guest (blank never wipes).
   `GuestAdmin` now embeds the companions+answers rollup (Phase-2-ready). Tier still
   never leaks.
2. **Admin views (DONE).** `GuestsPanel` has grouping (by invitee / by person) +
   layout (list / cards) toggles surfacing contacts, kid ages, per-person dietary and
   the configured custom-question answers (fed by the P1 `GuestAdmin` rollup);
   `GuestFormDialog` has email/phone (`MuiTelInput`); the Details tab has an "RSVP
   fields" toggle section (`content.rsvp.fields`); `ResponsesPanel` shows child ages.
3. **XLSX export + template + import (DONE).** Pure `app/export_import.py` defines the
   canonical **split-row** schema (one row per person) keyed on a `Link` column for
   upserts (blank = create new). `export.csv`/`export.xlsx` + `template.xlsx` +
   `POST /import?commit=` (dry-run preview → commit); tier-from-sheet authoritative
   with companion-cap enforcement (over-tier rows error, never widened); contacts
   normalized, blank cells never wipe. `ImportPanel` drives it from the Guests tab.

## Decisions (locked by RT 2026-06-09)
1. **Scope:** a single reception event per wedding — no multi-event logic.
2. **Stack:** **Next.js + FastAPI + Supabase** (standard, on the deploy path).
3. **Gift section (M9):** **deferred — reaffirmed 2026-06-10.** Not built yet and
   not before deploy. When built it's a tasteful cash-gift / PayNow / bank-transfer
   block, following the data-driven content pattern (a `content.gift` block on the
   wedding, seeded in `app/seed_data.py`, rendered by a `Gift.tsx` section — no new
   endpoint). **Seed placeholders** (e.g. `PAYNOW_NUMBER_HERE`) for RT to fill in
   himself before deploy — keep real financial details out of the repo. Methods
   TBD (PayNow / bank / ang-bao-at-venue / honeymoon-fund) — ask RT when building.
4. **Story artwork:** the predecessor build echoed a personal comic; the
   platform ships text-only template beats — story art is uploaded per wedding
   by its owner.

### M14 — Family adults · Invited status · grid multi-sort · dashboard counts (RT 2026-06-15)

Five owner-requested changes, delivered as separable sub-milestones. Full plan:
`~/.claude/plans/jazzy-napping-manatee.md`.

- **M14.1 — Multiple adults in plus_family.** `plus_family` now allows several extra
  **adults** (add/remove +/− list, like kids), not just one +1. Caps are a per-wedding
  setting (`content.rsvp.party.{adults_enabled,max_adults,kids_enabled,max_kids}`,
  default 4/4 — **no migration**); either group can be switched off and **every label is
  editable**. A new `Capabilities.adults_multi` flag tells the guest form to render the
  multi-adult list without leaking the tier. Threaded through the guest RSVP, admin
  Details (a "Party companions" section), the guest edit dialog, and import caps.
  `plus_one` keeps its single +1; `solo` unchanged.
- **M14.2 — "Invited" status.** New `guests.invite_sent` column (Alembic
  `d9e0f1a2b3c4`, **must migrate Supabase on deploy**). Status now derives Pending
  (not contacted) → **Invited** (owner sent it) → Attending/Declined. Set **manually**:
  a per-row quick toggle (Pending↔Invited), the bulk "Set status" menu, and the edit
  dialog. Surfaced in chips, the summary (`invited` count), and a new export **`Invite
  Sent`** column (distinct from the existing `Invited` = on-the-list).
- **M14.3 — Multi-column sort.** Multi-sort is Pro-only in MUI X DataGrid (Community
  truncates to one column), so both admin guest grids use a **custom** multi-sort:
  `useMultiSort` (ordered, persisted per view) + `applyMultiSort` (JS sort) + `<SortBar>`
  chips; `disableColumnSorting` + header-click (Shift-click adds a level).
- **M14.4 — Dashboard counts.** Overview hero now states **invitations vs guests
  (people) vs expected** explicitly; the import preview reports both invitee and
  person (incl. companion) counts (`ImportResult.people_created/updated`).
- **M14.5 — Name rule (verify-only) + this backlog.** Name is already mandatory in the
  guest RSVP UI (`RsvpForm.guestsError`) and optional in admin — confirmed, no change.

### Future / backlog priorities (item 6 — NOT built)
- **Comms sync (LATER, optional).** Send the invite by email / WhatsApp from the admin
  (integrate a messaging product). Pairs with M14.2: marking a guest **Invited** on send
  is the natural hook (consider auto-flipping `invite_sent` when a message is actually
  dispatched, vs today's manual toggle).
- **AI-generated wish (LATER, optional).** A new question *type* whose answer is
  generated by an LLM (backend OpenAI/Claude integration), non-editable by the guest,
  with an owner notification. Latest models per CLAUDE.md (Opus 4.8 etc.).
