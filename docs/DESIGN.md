# Design direction — "Ever after" (the default theme template)

The platform's default invite theme. Inherited from the predecessor build's
hand-drawn comic-story invite and generalized: every wedding gets this as its
starting look and can re-theme via stored `theme_tokens` and re-write every
line of copy via stored `content`. Nothing below is hardcoded in components.

## Concept

A **story-driven single-page invite**: the guest opens their personal link,
is greeted by name ("Dear {name},"), and scrolls through short comic-style
story beats that land on "…and you're invited" → the RSVP. An optional
**mascot** (default art: a hand-drawn cat glyph) acts as guide — it appears in
the nav, the RSVP walkthrough, and the footer, and can be replaced with an
uploaded image (`content.brand.icon_mode/icon_url`, plus a separate RSVP-guide
icon) or effectively hidden by owner copy/theme choices.

## Visual language

- **Paper-cream background** — an off-white comic-page feel.
- **Ink-black line art** — bold linework for headings, the circular wordmark,
  icons.
- **Soft pastels as accents only** — muted lavender, peach, sky, sage; never
  the whole UI.
- **Manga-style panels** — story beats framed as edge-feathered panels
  (image optional; the template ships text-only beats).

### Default theme tokens (config-driven — `frontend/theme/defaultThemeConfig.ts`)
```
colors:
  bg/paper      #F3EEE3   (cream page)
  ink           #1A1714   (near-black line art / text)
  primary       #D98C6A   (warm peach/terracotta)
  secondary     #8E9BB3   (dusty periwinkle)
  accentSage    #9DAE8E
  accentLav     #C9BBD6
  success/yes   #6FA38A
  decline/no    #B0796E
typography:
  display  -> a friendly rounded / hand-comic face for headings + wordmark
  story    -> a warm serif for narrator captions
  body     -> clean humanist sans for forms & details
radius: 14   spacingUnit: 8
```
All values live in the config; components reference tokens only. Per-wedding
`theme_tokens` deep-merge over these defaults (curated keys editable in the
admin Theme tab).

## Page structure (single-page scroll + separate admin)

Guest-facing, in scroll order — each is a "panel/chapter":

1. **Cover** — "Dear {name}," + couple names, countdown, spinning circular
   wordmark with the mascot/custom icon.
2. **Our story** — owner-written beats (one or more "arcs", optionally
   targeted per guest); text-first, images optional.
3. **The day** — venue, date/time, map, getting-there notes.
4. **Dress code** — guidance + theme-token swatch rows.
5. **RSVP** — name-gated; +1 / kids per the guest's link tier; dietary +
   custom questions; confirmation state.
6. **FAQ** — owner-editable Q&A items.
7. **Wishes** — optional moderated guestbook wall.
8. **Footer** — mascot sign-off + hashtag.

Easter eggs (subtle, on-brand): a konami-style "pet the cat" interaction and
a paw-print scroll-progress cue — both part of the generalized mascot feature.

## The invite-tier mechanism — design intent

Each guest gets a unique link `/i/{guest-slug}`. The slug maps server-side to
an **invite tier**:

| Tier | RSVP shows | Guest never sees |
|---|---|---|
| `solo` | "Will you be there?" — just them | any +1 field at all |
| `plus_one` | option to add **1** companion | the word "limit" |
| `plus_family` | add adults **and** children (capped, configurable) | — |

The UI is identical chrome for everyone; it simply renders fewer/more fields.
A `solo` guest sees a clean personal RSVP with **no hint** a +1 was ever an
option. Tier is encoded server-side against the slug (not guessable/editable
in the URL).

## Admin experience

Private dashboard per wedding:
- **Guest list** — import/export (split-row XLSX), per guest: side, group,
  batch, tier, link, RSVP status, dietary, companions.
- **Question builder** — custom questions (choice / multi-choice / text /
  number / yes-no) with scope (per-party / per-person) and targeting.
- **Links** — generate & copy per-guest links; track send batches.
- **Content & theme** — every section's copy, the brand mark, theme tokens.
- **Responses dashboard** — live counts, headcount incl. companions, dietary
  summary, capacity tracking, export.

## Why this reads "premium, not template"
One cohesive narrative device (the story + mascot), a restrained palette,
MUI for correct/accessible mechanics, and genuinely useful admin tooling.
Owners make it *theirs* by replacing copy, art, and tokens — the platform
never bakes any couple's identity into code.
