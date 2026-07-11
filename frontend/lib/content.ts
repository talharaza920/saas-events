import type { WeddingPublic } from "./api";

/**
 * Typed views over the wedding's data-driven `content` + `event_details` JSON
 * (seeded by backend/app/seed_data.py). The API returns these as loose objects;
 * these interfaces describe the shape the invite sections render, and the
 * accessors below read them defensively so a missing field degrades gracefully
 * rather than throwing. Copy + image refs live in the DB — never hardcode them
 * in components (multi-tenant: each wedding supplies its own).
 */
export interface NavLink {
  label: string;
  href: string;
}
export interface NavContent {
  brand?: string;
  links: NavLink[];
  cta?: string;
}
export interface CoverContent {
  kicker?: string;
  greeting?: string;
  invite_line?: string;
  tagline?: string;
  /** Show the "The story" scroll cue at the bottom of the cover. Defaults to
   * true; only an explicit `false` hides it. */
  story_cue?: boolean;
  /** Label under the scroll-cue badge. Undefined falls back to "The story"; an
   * explicit blank string shows the badge alone (no text). */
  story_cue_label?: string;
}
/** How the cover's spinning wordmark renders its center icon. */
export type BrandIconMode = "default" | "custom" | "svg" | "none";
export interface BrandContent {
  /** Text set on the rotating ring around the cover icon. */
  wordmark_text?: string;
  /** "default" = built-in cat glyph, "custom" = uploaded `icon_url`,
   * "svg" = the AI-designed `icon_svg` mark, "none" = no icon. */
  icon_mode: BrandIconMode;
  /** Uploaded square image URL, used only when icon_mode === "custom". */
  icon_url?: string;
  /**
   * SVG children (100×100 viewBox) for the AI-designed mark, used only when
   * icon_mode === "svg". Written exclusively by the AI apply path, which stores
   * the allowlist-rebuild-sanitised form — nothing else may write this key.
   */
  icon_svg?: string;
  /**
   * Separate uploaded square image for the RSVP-flow guide circle (the mascot
   * badge beside the speech bubble + on the confirmation screen). When blank the
   * RSVP circle keeps the built-in cat glyph; the cover/nav/footer marks are
   * unaffected.
   */
  rsvp_icon_url?: string;
}
export interface StoryBeat {
  /**
   * Legacy bullet number ("01".."06"). Optional now — story-arc beats are
   * numbered by position on render, so new/edited beats carry no stored `n`.
   */
  n?: string;
  image?: string;
  text?: string;
  wide?: boolean;
}
export interface StoryClimax {
  label?: string;
  image?: string;
  text?: string;
  cta?: string;
}
export interface StoryContent {
  kicker?: string;
  heading?: string;
  intro?: string;
  beats: StoryBeat[];
  climax: StoryClimax | null;
}
/** A small owner-editable label sitting above the whole story section
 * (e.g. "Our story"). Hidden when `visible` is false or `label` is blank. */
export interface StorySectionContent {
  visible: boolean;
  label?: string;
}
/** One owner-configurable detail cell under the day-card banner. Fully custom:
 * the owner picks the icon, the label and the value (+ an optional muted sub-line),
 * toggles it on/off, and may flag ONE-or-more as a Google-Maps link (the cell
 * becomes tappable, opening `event.map_url`). Rendered 4-up on desktop, 2×2 on
 * mobile; only `enabled` cells show. */
export interface DayCell {
  /** Icon name (see Ico `ICO_NAMES`); unknown values fall back to a dot. */
  icon: string;
  label: string;
  value: string;
  /** Optional second, muted line (e.g. "welcome drinks"). */
  sub?: string;
  enabled: boolean;
  /** When true the cell links to `event.map_url` (the address-as-link cell). */
  map_link?: boolean;
}
export interface DayContent {
  kicker?: string;
  heading?: string;
  intro?: string;
  /** The detail cells under the banner. When absent, the renderer seeds a sensible
   * default set from the event fields (see `defaultDayCells`). */
  cells?: DayCell[];
}

/** Seed cells from the legacy event fields so a wedding with no `day.cells` yet
 * still renders Time / Dress / Address, and the admin editor opens pre-filled. */
export function defaultDayCells(event: EventDetails): DayCell[] {
  return [
    { icon: "clock", label: "Time", value: event.time_display ?? "", enabled: !!event.time_display },
    { icon: "hourglass", label: "Arrive by", value: "", sub: "", enabled: false },
    { icon: "dress", label: "Dress", value: event.dress_code ?? "", enabled: !!event.dress_code },
    {
      icon: "pin",
      label: "Getting there",
      value: event.address ?? "",
      sub: event.getting_there ?? "",
      enabled: !!(event.address || event.getting_there),
      map_link: true,
    },
  ];
}
export interface DressCodeContent {
  kicker?: string;
  heading?: string;
  body?: string;
  /** Theme color token names (keys of ThemeColors) or raw CSS hex (e.g. "#ff7a00"). */
  swatches: string[];
  /** Colours to avoid — same vocabulary as `swatches` (tokens or raw hex). */
  swatches_avoid: string[];
  /** Caption above the "wear" row (shown only when an avoid row also renders). */
  wear_label?: string;
  /** Caption above the "avoid" row. */
  avoid_label?: string;
}
export interface FaqItem {
  q: string;
  a: string;
}
export interface FaqContent {
  kicker?: string;
  heading?: string;
  items: FaqItem[];
}
export interface RsvpChoice {
  emoji?: string;
  title?: string;
  sub?: string;
}
export interface RsvpConfirm {
  yes_title?: string;
  yes_body?: string;
  no_title?: string;
  no_body?: string;
}
// These are `type` aliases (not interfaces) on purpose: an all-string object
// *type* is assignable to `Record<string, string>`, which the `fillStrings`
// merge helper requires — an interface would not be (it can be augmented).
/** The eyebrow + title shown at the top of one RSVP step. */
export type RsvpStep = {
  lead: string;
  title: string;
};
export type RsvpStepKey = "attend" | "contacts" | "guests" | "extras" | "review" | "note";
export type RsvpSteps = Record<RsvpStepKey, RsvpStep>;
export type RsvpReviewLabels = {
  attending: string;
  attending_value: string;
  plus_one: string;
  adults: string;
  children: string;
};
export type RsvpButtons = {
  back: string;
  next: string;
  send: string;
  send_decline: string;
  sending: string;
  edit: string;
};
export type RsvpLabels = {
  validate_attend: string;
  validate_plus_one: string;
  plus_one_toggle: string;
  plus_one_name: string;
  plus_one_placeholder: string;
  adults_prompt: string;
  adult_name: string;
  kids_prompt: string;
  kid_name: string;
  your_details: string;
  your_name: string;
  validate_your_name: string;
  validate_required: string;
  contact_prompt: string;
  email_label: string;
  phone_label: string;
  validate_email: string;
  validate_phone: string;
  validate_contact: string;
};
/** Per-wedding toggles for which contact fields the RSVP asks. Booleans, so parsed
 * separately from the string labels (not via `fillStrings`). Companion dietary is a
 * per-person question now, not a toggle. */
export type RsvpFields = {
  collect_email: boolean;
  email_required: boolean;
  collect_phone: boolean;
  phone_required: boolean;
  /** Require at least one contact: if on, the guest must give an email OR a phone
   * (neither alone is individually mandatory). Lets a guest pick whichever they
   * prefer. Ignored if only one contact field is collected (that one governs). */
  require_contact: boolean;
};
/** plus_family companion allowance (owner-editable). Each group can be switched off
 * and capped; both default to 4. Drives the admin caps; the guest form reads the
 * resolved caps off `capabilities`. */
export type RsvpParty = {
  adults_enabled: boolean;
  max_adults: number;
  kids_enabled: boolean;
  max_kids: number;
};
export interface RsvpContent {
  kicker?: string;
  heading?: string;
  intro?: string;
  speech: Record<string, string>;
  choices: { yes: RsvpChoice; no: RsvpChoice };
  note_placeholder?: string;
  confirm: RsvpConfirm;
  // Step headers, review-row labels, buttons and inline labels. Parsed with the
  // defaults below so the form always has copy even if `content.rsvp` predates
  // these fields (e.g. a wedding seeded before Phase 4e).
  steps: RsvpSteps;
  review_labels: RsvpReviewLabels;
  buttons: RsvpButtons;
  labels: RsvpLabels;
  // Which contact/companion fields to ask (per-wedding). Defaults below.
  fields: RsvpFields;
  // plus_family companion caps (per-wedding). Defaults below.
  party: RsvpParty;
}

/** Default RSVP step/label/button copy — the wording the invite has always shown.
 * Shared by the parser (render fallback) and the admin editor (prefill), so the
 * two never drift. */
export const RSVP_DEFAULTS = {
  steps: {
    attend: { lead: "The big question…", title: "Can you make it?" },
    contacts: { lead: "Staying in touch", title: "How can we reach you?" },
    guests: { lead: "Your party", title: "Who's coming?" },
    extras: { lead: "A few details", title: "Help us plan" },
    review: { lead: "Almost there", title: "Look good?" },
    note: { lead: "We'll miss you", title: "Leave a note?" },
  } as RsvpSteps,
  review_labels: {
    attending: "Attending",
    attending_value: "Yes — joyfully 🎉",
    plus_one: "Plus one",
    adults: "Guests",
    children: "Children",
  } as RsvpReviewLabels,
  buttons: {
    back: "← Back",
    next: "Next",
    send: "Send my RSVP",
    send_decline: "Send reply",
    sending: "Sending…",
    edit: "Edit my response",
  } as RsvpButtons,
  labels: {
    validate_attend: "Pick an answer first 🐾",
    validate_plus_one: "Add your guest's name (or toggle them off).",
    plus_one_toggle: "I'm bringing a +1",
    plus_one_name: "Your guest's name",
    plus_one_placeholder: "e.g. Jamie Tan",
    adults_prompt: "Bringing other guests?",
    adult_name: "Guest's name",
    kids_prompt: "Bringing little ones?",
    kid_name: "Child's name (optional)",
    your_details: "Your details",
    your_name: "Your name",
    validate_your_name: "Please add your name.",
    validate_required: "Please answer all required questions.",
    contact_prompt: "How can we reach you?",
    email_label: "Email",
    phone_label: "Phone",
    validate_email: "Please add your email.",
    validate_phone: "Please add your phone number.",
    validate_contact: "Please add an email or a phone number.",
  } as RsvpLabels,
  fields: {
    collect_email: true,
    email_required: false,
    collect_phone: true,
    phone_required: false,
    require_contact: true,
  } as RsvpFields,
  party: {
    adults_enabled: true,
    max_adults: 4,
    kids_enabled: true,
    max_kids: 4,
  } as RsvpParty,
};

/** A starter invite message the owner can copy-and-send per guest. Placeholders are
 * substituted from each guest + the wedding's event details when copied from the
 * admin guest list. Supported: {greeting} {name} {link} {couple} {venue} {date} {time}. */
export const DEFAULT_INVITE_MESSAGE = `Hi {greeting}! 💛

{couple} would love for you to join our wedding celebration on {date} at {venue}.

Tap here for all the details and to RSVP: {link}

Can't wait to celebrate with you! 🐾`;
export interface FooterContent {
  hashtag?: string;
  signoff?: string;
}
export interface WishesContent {
  kicker?: string;
  heading?: string;
  intro?: string;
  name_label?: string;
  message_label?: string;
  button?: string;
  success?: string;
}

/** Copy for the public "no link" landing page (the site root for someone without
 * a personal invite link). Hidden text when `visible` is false. */
export interface LandingContent {
  visible: boolean;
  heading?: string;
  tagline?: string;
  body?: string;
}

/** Fallback landing copy — used when the backend is unreachable so the root page
 * still renders something sensible. Deliberately generic (no couple facts). */
export const LANDING_DEFAULTS: LandingContent = {
  visible: true,
  heading: "Welcome",
  tagline: "We're getting married!",
  body: "The invitation lives at your personal link.",
};

/** Read the loose `landing` JSON into a typed shape. A field that was NEVER set
 * (absent) falls back to its default; a field the owner explicitly cleared stays
 * empty (the page hides empty heading/tagline/body via render guards), so "blank
 * the body" is honoured. `visible` defaults to true. */
export function parseLanding(v: unknown): LandingContent {
  const o = obj(v);
  return {
    visible: o.visible === undefined ? true : Boolean(o.visible),
    heading: o.heading === undefined ? LANDING_DEFAULTS.heading : str(o.heading) ?? "",
    tagline: o.tagline === undefined ? LANDING_DEFAULTS.tagline : str(o.tagline) ?? "",
    body: o.body === undefined ? LANDING_DEFAULTS.body : str(o.body) ?? "",
  };
}

export interface EventDetails {
  title?: string;
  venue?: string;
  address?: string;
  area?: string;
  date_display?: string;
  time_display?: string;
  date_iso?: string;
  start_time?: string;
  end_time?: string;
  map_url?: string;
  /** Label for the "Open in Maps" button under the venue line (defaults to "Open in Maps"). */
  map_cta?: string;
  /** When false, hide the "Open in Maps" button in the day banner (defaults to shown when a map_url exists). */
  map_button?: boolean;
  dress_code?: string;
  getting_there?: string;
  timezone?: string;
}

export interface InviteContent {
  nav: NavContent;
  cover: CoverContent;
  brand: BrandContent;
  storySection: StorySectionContent;
  story: StoryContent;
  day: DayContent;
  dressCode: DressCodeContent;
  faq: FaqContent;
  rsvp: RsvpContent;
  footer: FooterContent;
  wishes: WishesContent;
  event: EventDetails;
}

function obj(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : {};
}
function arr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}
function str(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined;
}
function strList(v: unknown): string[] {
  return arr(v).filter((x): x is string => typeof x === "string");
}

/**
 * Flatten rich-text copy to plain text for plain-only consumers — the page
 * `<title>`, the social/link-preview description, anywhere a raw string (not React)
 * is needed. Strips the HTML formatting tags the admin editor emits AND the legacy
 * `**bold**` markup, and decodes the handful of entities those can contain.
 */
export function toPlainText(input: string | undefined): string {
  if (!input) return "";
  return input
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<\/p\s*>/gi, " ")
    .replace(/<[^>]+>/g, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&#x27;/gi, "'")
    .replace(/\s+/g, " ")
    .trim();
}

function parseBeats(v: unknown): StoryBeat[] {
  return arr(v)
    .map((x) => obj(x))
    // Keep a beat if it has any renderable content (image or text); the bullet
    // number `n` is no longer required (arc beats are numbered by position).
    .filter((x) => x.image || x.text)
    .map((x) => ({
      n: x.n ? String(x.n) : undefined,
      image: str(x.image),
      text: str(x.text),
      wide: Boolean(x.wide),
    }));
}

/** Build a typed StoryContent from a loose story/arc `content` object. */
export function parseStoryContent(v: unknown): StoryContent {
  const story = obj(v);
  return {
    kicker: str(story.kicker),
    heading: str(story.heading),
    intro: str(story.intro),
    beats: parseBeats(story.beats),
    climax: story.climax ? (obj(story.climax) as StoryClimax) : null,
  };
}

/** The story section label. `visible` defaults to true (a row seeded before this
 * field still shows the label) — the section component also requires a non-blank
 * label to actually render it. */
function parseStorySection(v: unknown): StorySectionContent {
  const o = obj(v);
  return {
    visible: o.visible === undefined ? true : Boolean(o.visible),
    label: str(o.label),
  };
}

/** Brand mark for the cover wordmark. Unknown/missing icon_mode falls back to
 * "default" (the built-in cat glyph) so the cover always renders something. */
function parseBrand(v: unknown): BrandContent {
  const b = obj(v);
  const mode = b.icon_mode;
  const icon_svg = str(b.icon_svg);
  // "svg" without a stored mark falls back to default, like custom-without-url.
  const icon_mode: BrandIconMode =
    mode === "custom" || mode === "none" || (mode === "svg" && icon_svg)
      ? (mode as BrandIconMode)
      : "default";
  return {
    wordmark_text: str(b.wordmark_text),
    icon_mode,
    icon_url: str(b.icon_url),
    icon_svg,
    rsvp_icon_url: str(b.rsvp_icon_url),
  };
}

function parseFaqItems(v: unknown): FaqItem[] {
  return arr(v)
    .map((x) => obj(x))
    .filter((x) => x.q && x.a)
    .map((x) => ({ q: String(x.q), a: String(x.a) }));
}

/** Accepts the current object shape `{kicker, heading, items}` or a bare array. */
function parseFaq(v: unknown): FaqContent {
  if (Array.isArray(v)) return { items: parseFaqItems(v) };
  const f = obj(v);
  return { kicker: str(f.kicker), heading: str(f.heading), items: parseFaqItems(f.items) };
}

function parseNav(v: unknown): NavContent {
  const n = obj(v);
  return {
    brand: str(n.brand),
    cta: str(n.cta),
    links: arr(n.links)
      .map((x) => obj(x))
      .filter((x) => x.label && x.href)
      .map((x) => ({ label: String(x.label), href: String(x.href) })),
  };
}

/** Overlay stored strings onto a defaults object — a blank/absent value keeps the
 * default, so the form never shows an empty step title or button. */
function fillStrings<T extends Record<string, string>>(def: T, v: unknown): T {
  const o = obj(v);
  const out = { ...def };
  for (const k of Object.keys(def) as (keyof T)[]) {
    const val = str(o[k as string]);
    if (val) out[k] = val as T[keyof T];
  }
  return out;
}

function parseRsvpSteps(v: unknown): RsvpSteps {
  const o = obj(v);
  const out = {} as RsvpSteps;
  for (const k of Object.keys(RSVP_DEFAULTS.steps) as RsvpStepKey[]) {
    out[k] = fillStrings(RSVP_DEFAULTS.steps[k], o[k]);
  }
  return out;
}

/** Read the per-wedding field toggles, defaulting any missing key (so a wedding
 * seeded before this block still collects contacts). A non-boolean stored value
 * falls back to the default. */
function parseRsvpFields(v: unknown): RsvpFields {
  const o = obj(v);
  const out = { ...RSVP_DEFAULTS.fields };
  for (const k of Object.keys(RSVP_DEFAULTS.fields) as (keyof RsvpFields)[]) {
    if (typeof o[k] === "boolean") out[k] = o[k] as boolean;
  }
  return out;
}

/** Read the per-wedding plus_family caps, defaulting any missing key (so a wedding
 * seeded before this block still gets 4/4). A non-boolean/-number stored value falls
 * back to the default; counts are floored at 0. */
function parseRsvpParty(v: unknown): RsvpParty {
  const o = obj(v);
  const out = { ...RSVP_DEFAULTS.party };
  if (typeof o.adults_enabled === "boolean") out.adults_enabled = o.adults_enabled;
  if (typeof o.kids_enabled === "boolean") out.kids_enabled = o.kids_enabled;
  if (typeof o.max_adults === "number") out.max_adults = Math.max(0, Math.floor(o.max_adults));
  if (typeof o.max_kids === "number") out.max_kids = Math.max(0, Math.floor(o.max_kids));
  return out;
}

function parseRsvp(v: unknown): RsvpContent {
  const r = obj(v);
  const choices = obj(r.choices);
  return {
    kicker: str(r.kicker),
    heading: str(r.heading),
    intro: str(r.intro),
    speech: Object.fromEntries(
      Object.entries(obj(r.speech)).map(([k, val]) => [k, String(val)]),
    ),
    choices: {
      yes: obj(choices.yes) as RsvpChoice,
      no: obj(choices.no) as RsvpChoice,
    },
    note_placeholder: str(r.note_placeholder),
    confirm: obj(r.confirm) as RsvpConfirm,
    steps: parseRsvpSteps(r.steps),
    review_labels: fillStrings(RSVP_DEFAULTS.review_labels, r.review_labels),
    buttons: fillStrings(RSVP_DEFAULTS.buttons, r.buttons),
    labels: fillStrings(RSVP_DEFAULTS.labels, r.labels),
    fields: parseRsvpFields(r.fields),
    party: parseRsvpParty(r.party),
  };
}

/** Normalize the API's loose content/event JSON into a typed, safe shape. */
export function parseContent(wedding: WeddingPublic): InviteContent {
  const c = obj(wedding.content);
  const dress = obj(c.dress_code);
  return {
    nav: parseNav(c.nav),
    cover: obj(c.cover) as CoverContent,
    brand: parseBrand(c.brand),
    storySection: parseStorySection(c.story_section),
    story: parseStoryContent(c.story),
    day: obj(c.day) as DayContent,
    dressCode: {
      kicker: str(dress.kicker),
      heading: str(dress.heading),
      body: str(dress.body),
      swatches: strList(dress.swatches),
      swatches_avoid: strList(dress.swatches_avoid),
      wear_label: str(dress.wear_label),
      avoid_label: str(dress.avoid_label),
    },
    faq: parseFaq(c.faq),
    rsvp: parseRsvp(c.rsvp),
    footer: obj(c.footer) as FooterContent,
    wishes: obj(c.wishes) as WishesContent,
    event: obj(wedding.event_details) as EventDetails,
  };
}
