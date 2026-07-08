"use client";

import { useState } from "react";

import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { type ContentAdmin, type QuestionAdmin } from "@/lib/adminApi";
import { RSVP_DEFAULTS } from "@/lib/content";
import type { RsvpStepKey, RsvpSteps } from "@/lib/content";

import QuestionsPanel from "./QuestionsPanel";
import RichTextField from "./RichTextField";
import { rec, s, SectionCard } from "./sectionKit";

// ---------------------------------------------------------------------------
// RSVP-only helpers (moved here with the RSVP sections).
// ---------------------------------------------------------------------------
/** Prefill a string-map state from stored content, keeping defaults for blanks. */
function fillMap<T extends Record<string, string>>(def: T, v: unknown): T {
  const o = rec(v);
  const out = { ...def };
  for (const k of Object.keys(def) as (keyof T)[]) {
    const val = s(o[k as string]);
    if (val) out[k] = val as T[keyof T];
  }
  return out;
}
/** "validate_attend" → "Validate attend" for a field label. */
function humanize(k: string): string {
  const t = k.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}
/** Friendly label + "where it appears" hint for each RSVP nav button, so the admin
 * isn't editing cryptic keys ("send_decline", "sending"). Order = display order. */
const RSVP_BUTTON_FIELDS: { key: keyof typeof RSVP_DEFAULTS.buttons; label: string; help: string }[] = [
  { key: "next", label: "Continue button", help: "Shown on every step except the last." },
  { key: "send", label: "Final submit button", help: "Last step, when the guest is attending." },
  { key: "send_decline", label: "Final submit button (declining)", help: "Last step, when the guest can't make it." },
  { key: "back", label: "Back button", help: "Returns to the previous step." },
  { key: "sending", label: "Submitting… label", help: "Shown on the submit button while saving." },
  { key: "edit", label: "Edit-response link", help: "Shown on the confirmation screen after submitting." },
];

/** A TextField per key of a flat string map (review labels). */
function StringMapEditor<T extends Record<string, string>>({
  value,
  onChange,
}: {
  value: T;
  onChange: (next: T) => void;
}) {
  return (
    <>
      {(Object.keys(value) as (keyof T & string)[]).map((k) => (
        <TextField
          key={k}
          label={humanize(k)}
          value={value[k]}
          onChange={(e) => onChange({ ...value, [k]: e.target.value } as T)}
          fullWidth
          size="small"
        />
      ))}
    </>
  );
}

/**
 * The RSVP tab, organised by the steps a guest actually walks through:
 * Heading, then Step 1 (can you make it?) → Step 2 (contacts) → Step 3 (party +
 * per-person questions) → Step 4 (extras + per-invitee questions) → Step 5
 * (review), plus the decline path (leave a note) and an "Others" bucket for the
 * cross-step buttons. Each section saves only its own slice (deep-merged
 * server-side), so splitting fields across steps never clobbers the rest.
 */
export default function RsvpPanel({
  content,
  questions,
  onChanged,
}: {
  content: ContentAdmin;
  questions: QuestionAdmin[];
  onChanged: () => void | Promise<void>;
}) {
  const c = rec(content.content);

  // --- RSVP microcopy ------------------------------------------------------
  const rsvp0 = rec(c.rsvp);
  const speech0 = rec(rsvp0.speech);
  const choices0 = rec(rsvp0.choices);
  const yes0 = rec(choices0.yes);
  const no0 = rec(choices0.no);
  const confirm0 = rec(rsvp0.confirm);
  const [rsvpHead, setRsvpHead] = useState({
    kicker: s(rsvp0.kicker),
    heading: s(rsvp0.heading),
    intro: s(rsvp0.intro),
  });
  const [speech, setSpeech] = useState({
    attend: s(speech0.attend),
    contacts: s(speech0.contacts),
    guests: s(speech0.guests),
    extras: s(speech0.extras),
    review: s(speech0.review),
    note: s(speech0.note),
  });
  const [yes, setYes] = useState({ emoji: s(yes0.emoji), title: s(yes0.title), sub: s(yes0.sub) });
  const [no, setNo] = useState({ emoji: s(no0.emoji), title: s(no0.title), sub: s(no0.sub) });
  const [notePlaceholder, setNotePlaceholder] = useState(s(rsvp0.note_placeholder));
  const [confirm, setConfirm] = useState({
    yes_title: s(confirm0.yes_title),
    yes_body: s(confirm0.yes_body),
    no_title: s(confirm0.no_title),
    no_body: s(confirm0.no_body),
  });

  // --- RSVP steps / review labels / buttons / inline labels ----------------
  const [rsvpSteps, setRsvpSteps] = useState<RsvpSteps>(() => {
    const o = rec(rsvp0.steps);
    const out = {} as RsvpSteps;
    (Object.keys(RSVP_DEFAULTS.steps) as RsvpStepKey[]).forEach((k) => {
      out[k] = fillMap(RSVP_DEFAULTS.steps[k], o[k]);
    });
    return out;
  });
  const [reviewLabels, setReviewLabels] = useState(() => fillMap(RSVP_DEFAULTS.review_labels, rsvp0.review_labels));
  const [rsvpButtons, setRsvpButtons] = useState(() => fillMap(RSVP_DEFAULTS.buttons, rsvp0.buttons));
  const [rsvpLabels, setRsvpLabels] = useState(() => fillMap(RSVP_DEFAULTS.labels, rsvp0.labels));

  // --- RSVP fields (which contact / companion fields the form collects) ----
  const [rsvpFields, setRsvpFields] = useState(() => {
    const o = rec(rsvp0.fields);
    const out = { ...RSVP_DEFAULTS.fields };
    (Object.keys(RSVP_DEFAULTS.fields) as (keyof typeof out)[]).forEach((k) => {
      if (typeof o[k] === "boolean") out[k] = o[k] as boolean;
    });
    return out;
  });
  const setField = (k: keyof typeof rsvpFields, v: boolean) =>
    setRsvpFields((prev) => ({ ...prev, [k]: v }));

  // --- RSVP party (plus_family adult/kid caps) -----------------------------
  const [rsvpParty, setRsvpParty] = useState(() => {
    const o = rec(rsvp0.party);
    const out = { ...RSVP_DEFAULTS.party };
    if (typeof o.adults_enabled === "boolean") out.adults_enabled = o.adults_enabled;
    if (typeof o.kids_enabled === "boolean") out.kids_enabled = o.kids_enabled;
    if (typeof o.max_adults === "number") out.max_adults = Math.max(0, Math.floor(o.max_adults));
    if (typeof o.max_kids === "number") out.max_kids = Math.max(0, Math.floor(o.max_kids));
    return out;
  });
  const setParty = (k: keyof typeof rsvpParty, v: boolean | number) =>
    setRsvpParty((prev) => ({ ...prev, [k]: v }));

  // --- Render helpers ------------------------------------------------------
  // One small TextField per inline-label key (humanized name).
  const labelField = (k: keyof typeof rsvpLabels) => (
    <TextField
      key={k}
      label={humanize(k)}
      value={rsvpLabels[k]}
      onChange={(e) => setRsvpLabels({ ...rsvpLabels, [k]: e.target.value })}
      fullWidth
      size="small"
    />
  );
  // The subset of labels a step saves (deep-merged server-side, so other keys survive).
  const pickLabels = (keys: (keyof typeof rsvpLabels)[]) =>
    Object.fromEntries(keys.map((k) => [k, rsvpLabels[k]]));
  // A step's eyebrow + title, and the speech bubble for that step.
  const stepLeadTitle = (k: RsvpStepKey) => (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
      <RichTextField label="Step eyebrow" value={rsvpSteps[k].lead} variant="inline"
        onChange={(v) => setRsvpSteps({ ...rsvpSteps, [k]: { ...rsvpSteps[k], lead: v } })} />
      <RichTextField label="Step title" value={rsvpSteps[k].title} variant="inline"
        onChange={(v) => setRsvpSteps({ ...rsvpSteps, [k]: { ...rsvpSteps[k], title: v } })} />
    </Stack>
  );
  const stepSpeech = (k: RsvpStepKey) => (
    <RichTextField label="Speech bubble" value={speech[k]} variant="inline"
      onChange={(v) => setSpeech({ ...speech, [k]: v })} />
  );

  // Which inline labels belong to which step (everything in RSVP_DEFAULTS.labels).
  const S1_LABELS: (keyof typeof rsvpLabels)[] = ["validate_attend"];
  const S2_LABELS: (keyof typeof rsvpLabels)[] = [
    "contact_prompt", "email_label", "phone_label",
    "validate_email", "validate_phone", "validate_contact",
  ];
  const S3_LABELS: (keyof typeof rsvpLabels)[] = [
    "your_details", "your_name", "validate_your_name",
    "plus_one_toggle", "plus_one_name", "plus_one_placeholder", "validate_plus_one",
    "adults_prompt", "adult_name", "kids_prompt", "kid_name",
    "validate_required",
  ];

  const personCount = questions.filter((q) => q.scope === "person").length;
  const inviteeCount = questions.filter((q) => q.scope === "invitee").length;

  return (
    <Paper sx={{ p: { xs: 1.5, sm: 2.5 } }}>
      <Typography variant="h6" sx={{ mb: 0.5 }}>
        RSVP
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Organised by the steps a guest walks through. Accepting runs Step 1 → 5;
        declining jumps from Step 1 straight to the note. Each section saves on its
        own. (Steps 2–4 are skipped for a guest who has nothing to show there.)
      </Typography>

      {/* Heading ----------------------------------------------------------- */}
      <SectionCard
        title="Heading"
        subtitle="The kicker, heading and intro above the whole RSVP form"
        defaultExpanded
        onChanged={onChanged}
        build={() => ({
          content: { rsvp: { kicker: rsvpHead.kicker, heading: rsvpHead.heading, intro: rsvpHead.intro } },
        })}
      >
        <RichTextField label="Kicker" value={rsvpHead.kicker} variant="inline"
          onChange={(v) => setRsvpHead({ ...rsvpHead, kicker: v })} />
        <RichTextField label="Heading" value={rsvpHead.heading} variant="inline"
          onChange={(v) => setRsvpHead({ ...rsvpHead, heading: v })} />
        <RichTextField label="Intro" value={rsvpHead.intro}
          onChange={(v) => setRsvpHead({ ...rsvpHead, intro: v })}
          helperText="Use {name} for the invite greeting (e.g. “Riley & Jamie”)" />
      </SectionCard>

      {/* Step 1 — attend --------------------------------------------------- */}
      <SectionCard
        title="Step 1 · Can you make it?"
        subtitle="The opening question and the accept / decline cards"
        onChanged={onChanged}
        build={() => ({
          content: {
            rsvp: {
              steps: { attend: rsvpSteps.attend },
              speech: { attend: speech.attend },
              choices: { yes, no },
              labels: pickLabels(S1_LABELS),
            },
          },
        })}
      >
        {stepLeadTitle("attend")}
        {stepSpeech("attend")}
        <Divider flexItem />
        <Typography variant="subtitle2" color="text.secondary">Accept / decline choices</Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
          <TextField label="Accept emoji" value={yes.emoji}
            onChange={(e) => setYes({ ...yes, emoji: e.target.value })} sx={{ width: { sm: 120 }, flexShrink: 0 }} />
          <RichTextField label="Accept title" value={yes.title} variant="inline"
            onChange={(v) => setYes({ ...yes, title: v })} />
          <RichTextField label="Accept subtitle" value={yes.sub} variant="inline"
            onChange={(v) => setYes({ ...yes, sub: v })} />
        </Stack>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
          <TextField label="Decline emoji" value={no.emoji}
            onChange={(e) => setNo({ ...no, emoji: e.target.value })} sx={{ width: { sm: 120 }, flexShrink: 0 }} />
          <RichTextField label="Decline title" value={no.title} variant="inline"
            onChange={(v) => setNo({ ...no, title: v })} />
          <RichTextField label="Decline subtitle" value={no.sub} variant="inline"
            onChange={(v) => setNo({ ...no, sub: v })} />
        </Stack>
        <Divider flexItem />
        <Typography variant="subtitle2" color="text.secondary">Validation</Typography>
        {labelField("validate_attend")}
      </SectionCard>

      {/* Step 2 — contacts ------------------------------------------------- */}
      <SectionCard
        title="Step 2 · How can we reach you?"
        subtitle="The contact step — which details to collect, and its wording"
        onChanged={onChanged}
        build={() => ({
          content: {
            rsvp: {
              steps: { contacts: rsvpSteps.contacts },
              speech: { contacts: speech.contacts },
              fields: rsvpFields,
              labels: pickLabels(S2_LABELS),
            },
          },
        })}
      >
        {stepLeadTitle("contacts")}
        {stepSpeech("contacts")}
        <Divider flexItem />
        <Typography variant="subtitle2" color="text.secondary">Which details to collect</Typography>
        <FormControlLabel
          control={<Switch checked={rsvpFields.collect_email} onChange={(e) => setField("collect_email", e.target.checked)} />}
          label="Ask guests for their email"
        />
        <FormControlLabel
          sx={{ ml: 3 }}
          control={
            <Switch
              checked={rsvpFields.email_required}
              disabled={
                !rsvpFields.collect_email ||
                (rsvpFields.require_contact && rsvpFields.collect_email && rsvpFields.collect_phone)
              }
              onChange={(e) => setField("email_required", e.target.checked)}
            />
          }
          label="Email is required"
        />
        <FormControlLabel
          control={<Switch checked={rsvpFields.collect_phone} onChange={(e) => setField("collect_phone", e.target.checked)} />}
          label="Ask guests for their phone number"
        />
        <FormControlLabel
          sx={{ ml: 3 }}
          control={
            <Switch
              checked={rsvpFields.phone_required}
              disabled={
                !rsvpFields.collect_phone ||
                (rsvpFields.require_contact && rsvpFields.collect_email && rsvpFields.collect_phone)
              }
              onChange={(e) => setField("phone_required", e.target.checked)}
            />
          }
          label="Phone is required"
        />
        <FormControlLabel
          control={
            <Switch
              checked={rsvpFields.require_contact}
              disabled={!rsvpFields.collect_email || !rsvpFields.collect_phone}
              onChange={(e) => setField("require_contact", e.target.checked)}
            />
          }
          label="Require at least one contact (email or phone)"
        />
        <Typography variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>
          With this on, a guest must give an email <em>or</em> a phone — whichever
          they prefer — but neither alone is forced. Turn on a specific
          “required” switch above to insist on that exact field.
        </Typography>
        <Divider flexItem />
        <Typography variant="subtitle2" color="text.secondary">Labels &amp; validation</Typography>
        {S2_LABELS.map((k) => labelField(k))}
      </SectionCard>

      {/* Step 3 — guests --------------------------------------------------- */}
      <SectionCard
        title="Step 3 · Who's coming?"
        subtitle="Your details, the +1 / extra-guest / kids wording and party caps"
        onChanged={onChanged}
        build={() => ({
          content: {
            rsvp: {
              steps: { guests: rsvpSteps.guests },
              speech: { guests: speech.guests },
              party: rsvpParty,
              labels: pickLabels(S3_LABELS),
            },
          },
        })}
      >
        {stepLeadTitle("guests")}
        {stepSpeech("guests")}
        <Divider flexItem />
        <Typography variant="subtitle2" color="text.secondary">Party companions (family invites)</Typography>
        <FormControlLabel
          control={<Switch checked={rsvpParty.adults_enabled} onChange={(e) => setParty("adults_enabled", e.target.checked)} />}
          label="Let family invites add extra guests"
        />
        <TextField
          label="Max extra guests"
          type="number"
          size="small"
          sx={{ ml: 3, maxWidth: 180 }}
          value={rsvpParty.max_adults}
          disabled={!rsvpParty.adults_enabled}
          onChange={(e) => setParty("max_adults", Math.max(0, Math.floor(Number(e.target.value) || 0)))}
          inputProps={{ min: 0, max: 20 }}
        />
        <FormControlLabel
          control={<Switch checked={rsvpParty.kids_enabled} onChange={(e) => setParty("kids_enabled", e.target.checked)} />}
          label="Let family invites add kids"
        />
        <TextField
          label="Max kids"
          type="number"
          size="small"
          sx={{ ml: 3, maxWidth: 180 }}
          value={rsvpParty.max_kids}
          disabled={!rsvpParty.kids_enabled}
          onChange={(e) => setParty("max_kids", Math.max(0, Math.floor(Number(e.target.value) || 0)))}
          inputProps={{ min: 0, max: 20 }}
        />
        <Typography variant="caption" color="text.secondary">
          Companion caps only affect <strong>plus family</strong> invites. Turn the
          kids group off to make companions a single generic list — then rename the
          “Bringing other guests?” / “Guest&apos;s name” wording below.
        </Typography>
        <Divider flexItem />
        <Typography variant="subtitle2" color="text.secondary">Labels &amp; validation</Typography>
        {S3_LABELS.map((k) => labelField(k))}
      </SectionCard>

      {/* Step 3 questions (per-person) ------------------------------------- */}
      <Accordion disableGutters>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Box>
            <Typography sx={{ fontWeight: 700 }}>
              Step 3 · Per-person questions{personCount ? ` (${personCount})` : ""}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Asked of each attendee (dietary, a child&apos;s age). Each question saves on its own.
            </Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <QuestionsPanel questions={questions} onChanged={onChanged} scope="person" />
        </AccordionDetails>
      </Accordion>

      {/* Step 4 — extras (wording) ----------------------------------------- */}
      <SectionCard
        title="Step 4 · Help us plan"
        subtitle="The “extras” step — shown to a guest only when there are per-invitee questions"
        onChanged={onChanged}
        build={() => ({
          content: {
            rsvp: {
              steps: { extras: rsvpSteps.extras },
              speech: { extras: speech.extras },
            },
          },
        })}
      >
        {stepLeadTitle("extras")}
        {stepSpeech("extras")}
      </SectionCard>

      {/* Step 4 questions (per-invitee) ------------------------------------ */}
      <Accordion disableGutters>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Box>
            <Typography sx={{ fontWeight: 700 }}>
              Step 4 · Per-invitee questions{inviteeCount ? ` (${inviteeCount})` : ""}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Asked once for the whole party (a song request, how they know you). Each question saves on its own.
            </Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <QuestionsPanel questions={questions} onChanged={onChanged} scope="invitee" />
        </AccordionDetails>
      </Accordion>

      {/* Step 5 — review --------------------------------------------------- */}
      <SectionCard
        title="Step 5 · Look good?"
        subtitle="The review summary, its labels and the “you're coming” confirmation"
        onChanged={onChanged}
        build={() => ({
          content: {
            rsvp: {
              steps: { review: rsvpSteps.review },
              speech: { review: speech.review },
              review_labels: reviewLabels,
              confirm: { yes_title: confirm.yes_title, yes_body: confirm.yes_body },
            },
          },
        })}
      >
        {stepLeadTitle("review")}
        {stepSpeech("review")}
        <Divider flexItem />
        <Typography variant="subtitle2" color="text.secondary">Review-summary labels</Typography>
        <StringMapEditor value={reviewLabels} onChange={setReviewLabels} />
        <Divider flexItem />
        <Typography variant="subtitle2" color="text.secondary">Confirmation shown after accepting</Typography>
        <RichTextField label="Accepted — title" value={confirm.yes_title} variant="inline"
          onChange={(v) => setConfirm({ ...confirm, yes_title: v })} />
        <RichTextField label="Accepted — body" value={confirm.yes_body}
          onChange={(v) => setConfirm({ ...confirm, yes_body: v })} />
      </SectionCard>

      {/* Decline — note ---------------------------------------------------- */}
      <SectionCard
        title="If they can’t make it · Leave a note"
        subtitle="The decline step, its note field and the “we'll miss you” confirmation"
        onChanged={onChanged}
        build={() => ({
          content: {
            rsvp: {
              steps: { note: rsvpSteps.note },
              speech: { note: speech.note },
              note_placeholder: notePlaceholder,
              confirm: { no_title: confirm.no_title, no_body: confirm.no_body },
            },
          },
        })}
      >
        {stepLeadTitle("note")}
        {stepSpeech("note")}
        <Divider flexItem />
        <TextField label="Note placeholder" value={notePlaceholder}
          onChange={(e) => setNotePlaceholder(e.target.value)} fullWidth size="small" />
        <Divider flexItem />
        <Typography variant="subtitle2" color="text.secondary">Confirmation shown after declining</Typography>
        <RichTextField label="Declined — title" value={confirm.no_title} variant="inline"
          onChange={(v) => setConfirm({ ...confirm, no_title: v })} />
        <RichTextField label="Declined — body" value={confirm.no_body}
          onChange={(v) => setConfirm({ ...confirm, no_body: v })} />
      </SectionCard>

      {/* Others — buttons -------------------------------------------------- */}
      <SectionCard
        title="Others"
        subtitle="Buttons shown across every step (the catch-all for cross-step wording)"
        onChanged={onChanged}
        build={() => ({ content: { rsvp: { buttons: rsvpButtons } } })}
      >
        <Typography variant="subtitle2" color="text.secondary">Buttons</Typography>
        {RSVP_BUTTON_FIELDS.map(({ key, label, help }) => (
          <TextField
            key={key}
            label={label}
            helperText={help}
            value={rsvpButtons[key]}
            onChange={(e) => setRsvpButtons({ ...rsvpButtons, [key]: e.target.value })}
            fullWidth
            size="small"
          />
        ))}
      </SectionCard>
    </Paper>
  );
}
