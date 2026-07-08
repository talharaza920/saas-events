# Reference site research

Findings from studying the two reference products RT shared. **No forms were
submitted and no RSVP was registered** on either site. _Researched 2026-06-09._

## 1. WithJoy (withjoy.com) — the feature benchmark

A polished all-in-one US wedding platform. The bits worth copying:

- **Smart RSVP with custom questions.** Couples define their own questions.
  Types: **multiple choice** (pick one), **free text** (dietary, song requests),
  and pre-built suggestions (advice, honeymoon ideas). → drives our admin
  "custom questions" feature (requirement a).
- **Strict name matching ("velvet rope").** Guests RSVP by typing their name
  exactly as on the invite; only people on the guest list can respond. → our
  name-gated RSVP.
- **Parties / grouping.** A guest can RSVP on behalf of their whole grouped
  party (partner, family). If a +1 name is left blank, the guest fills it in and
  it flows back to the guest list. → our +1 / party model.
- **Targeted questions.** A question can be limited to a subset of guests (e.g.
  after-party only). → per-guest question visibility.
- **Multi-event handling.** Not everyone is invited to every event; RSVP and
  schedule respect that. → relevant if we cover both 19 Jul + 21 Nov.
- **Website sections:** story/about, schedule, registry, travel/hotel blocks,
  photo gallery, FAQ.
- **Premium feel** comes from: cohesive theme across web + app, generous free
  digital features, real utility (hotel blocks), and "uniquely yours" framing.

Sources:
- https://withjoy.com/help/en/articles/8293305-customize-your-rsvp-questions
- https://withjoy.com/help/en/articles/8295996-strict-name-matching-for-your-wedding-rsvps
- https://withjoy.com/help/en/articles/8343360-adding-plus-ones-and-parties
- https://withjoy.com/help/en/articles/8319309-asking-rsvp-questions-to-specific-guests
- https://withjoy.com/help/en/articles/11085588-...-multiple-events-...

## 2. Kasihundangan (friend's invite) — the experience + personalization model

Indonesian single-page scrolling digital invitation. This is the **UX template**
and, crucially, the **personalized-link mechanism** RT wants.

Structure (vertical scroll, anchored nav):
1. **Cover / "open invitation"** — couple names, date + **countdown**, poetic
   tagline; an envelope-style reveal before the rest loads.
2. **Couple intro / love story.**
3. **Event details** — venue, ceremony/reception/after-party times, Google Maps,
   hotel booking.
4. **Dress code** — visual guide ("celebrate in color").
5. **RSVP form** — name, email, WhatsApp, attendance choice (e.g. reception only
   vs + after-party), **guest count**, with a transparent note about children.
6. **Gallery.**
7. **Gift** — bank-transfer details for each side.
8. **Wishes / guestbook** — public messages from guests.
9. Background **music**, **#hashtag**, language toggle.

**The key trick — personalized URL:**
`...?package=Personal&kasihundangan=Guest+Name`
- `kasihundangan=Guest+Name` → the guest's name is injected ("Dear Guest Name").
- `package=Personal` → an invite **tier** baked into the link. This is exactly
  RT's requirement (c): the link silently sets what the guest is allowed to do
  (e.g. add guests or not). The guest never sees the tier label; the UI simply
  shows or omits the option.

## How this maps onto our build

| Reference idea | Our implementation |
|---|---|
| WithJoy custom questions | Admin question builder: multiple-choice / text / yes-no, optional per-tier visibility |
| WithJoy strict name match | Guest token/slug in link + name confirm; only listed guests RSVP |
| WithJoy parties / blank +1 | Invite tiers: `solo` / `plus_one` / `plus_family`; guest fills companion names |
| Kasihundangan `?package=` | Per-guest signed link encodes tier **and** identity; tier hidden in UI |
| Kasihundangan scroll story | Single-page narrative theme ("Ever after") — see DESIGN.md |
| Kasihundangan guestbook/gift | Optional wishes wall + optional gift section |
