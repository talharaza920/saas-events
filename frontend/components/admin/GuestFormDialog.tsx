"use client";

import { useState } from "react";

import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { MuiTelInput } from "mui-tel-input";

import type { AnswerValue, GuestAdmin, QuestionAdmin, StoryArcAdmin } from "@/lib/adminApi";

import AnswerField, { isAnswered } from "./AnswerField";

/** One attendee's editable draft: a name plus their answers keyed by question id. */
export interface PersonDraft {
  name: string;
  answers: Record<string, AnswerValue>;
}

export interface GuestFormValues {
  /** The primary attendee's name — optional (the guest can fill it at RSVP). */
  name: string;
  /** Mandatory invite greeting (e.g. "John & Jane") — the cover's "Dear …" line. */
  greeting_name: string;
  email: string;
  phone: string;
  invite_tier: string;
  side: string;
  relationship: string;
  group_name: string;
  batch: string;
  /** Owner's pre-RSVP headcount estimate (incl. the invitee). "" = no estimate. */
  expected_party_size: string;
  invited: boolean;
  /** Story-arc override (arc ids). Empty = this guest sees every visible arc. */
  story_arc_ids: string[];
  /** RSVP status the owner can set/correct: pending | attending | declined. */
  rsvp_status: string;
  /** The primary's own person answers + the invitee-scope answers (party answers). */
  partyAnswers: Record<string, AnswerValue>;
  /** The adult companions (the +1 for plus_one; several extra adults for plus_family):
   * each name + their person answers. */
  adults: PersonDraft[];
  /** The children: each name + their person answers. */
  children: PersonDraft[];
}

const TIERS = [
  { value: "solo", label: "Solo (no companions)" },
  { value: "plus_one", label: "Plus one (1 guest)" },
  { value: "plus_family", label: "Plus family (extra guests + kids)" },
];

const RSVP_STATUSES = [
  { value: "pending", label: "Pending (not yet contacted)" },
  { value: "invited", label: "Invited (sent, awaiting reply)" },
  { value: "attending", label: "Attending" },
  { value: "declined", label: "Not coming" },
];

// Fallback caps when the wedding hasn't configured content.rsvp.party (matches the
// backend default in tenancy.py). plus_one is always a single adult.
const DEFAULT_FAMILY_ADULTS = 4;
const DEFAULT_FAMILY_KIDS = 4;

/** Whether a companion will be saved: it has a name or at least one answer. Shared
 * with the submit assembly so validation and persistence agree on who's "in". */
export function personIncluded(p: PersonDraft, qs: QuestionAdmin[]): boolean {
  return p.name.trim() !== "" || qs.some((q) => isAnswered(q, p.answers[q.id]));
}

function answersFrom(answers?: { question_id: string; value: AnswerValue }[]): Record<string, AnswerValue> {
  const out: Record<string, AnswerValue> = {};
  for (const a of answers ?? []) out[a.question_id] = a.value;
  return out;
}

function fromGuest(g?: GuestAdmin | null): GuestFormValues {
  // The +1/kids come from the RSVP companions (with their answers) once the guest
  // has a party; otherwise from the admin prefill names (no answers yet).
  const comps = g?.companions ?? [];
  let adults: PersonDraft[];
  let children: PersonDraft[];
  if (comps.length > 0) {
    adults = comps
      .filter((c) => c.kind === "adult")
      .map((c) => ({ name: c.name ?? "", answers: answersFrom(c.answers) }));
    children = comps
      .filter((c) => c.kind === "child")
      .map((c) => ({ name: c.name ?? "", answers: answersFrom(c.answers) }));
  } else {
    const pm = g?.party_members ?? [];
    adults = pm.filter((m) => m.kind === "adult").map((m) => ({ name: m.name ?? "", answers: {} }));
    children = pm.filter((m) => m.kind === "child").map((m) => ({ name: m.name ?? "", answers: {} }));
  }
  return {
    name: g?.name ?? "",
    greeting_name: g?.greeting_name ?? "",
    email: g?.email ?? "",
    phone: g?.phone ?? "",
    invite_tier: g?.invite_tier ?? "solo",
    side: g?.side ?? "",
    relationship: g?.relationship ?? "",
    group_name: g?.group_name ?? "",
    batch: g?.batch ?? "",
    expected_party_size: g?.expected_party_size != null ? String(g.expected_party_size) : "",
    invited: g?.invited ?? true,
    story_arc_ids: g?.story_arc_ids ?? [],
    rsvp_status: g?.rsvp_status ?? "pending",
    partyAnswers: answersFrom(g?.answers),
    adults,
    children,
  };
}

/** A collapsible titled section. */
function Section({
  title,
  subtitle,
  defaultExpanded = true,
  children,
}: {
  title: string;
  subtitle?: string;
  defaultExpanded?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Accordion defaultExpanded={defaultExpanded} disableGutters>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Box>
          <Typography sx={{ fontWeight: 600 }}>{title}</Typography>
          {subtitle && (
            <Typography variant="caption" color="text.secondary">
              {subtitle}
            </Typography>
          )}
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2}>{children}</Stack>
      </AccordionDetails>
    </Accordion>
  );
}

export default function GuestFormDialog({
  guest,
  arcs = [],
  primaryQuestions = [],
  inviteeQuestions = [],
  childQuestions = [],
  maxAdults = DEFAULT_FAMILY_ADULTS,
  maxKids = DEFAULT_FAMILY_KIDS,
  onClose,
  onSubmit,
}: {
  guest?: GuestAdmin | null;
  arcs?: StoryArcAdmin[];
  /** Person-scope questions asked of the primary + the +1 (everyone / adults). */
  primaryQuestions?: QuestionAdmin[];
  /** Invitee-scope questions, asked once for the whole party. */
  inviteeQuestions?: QuestionAdmin[];
  /** Person-scope questions asked of a child (everyone / children). */
  childQuestions?: QuestionAdmin[];
  /** plus_family caps from the wedding's content.rsvp.party (0 = group off). */
  maxAdults?: number;
  maxKids?: number;
  onClose: () => void;
  onSubmit: (values: GuestFormValues) => Promise<void>;
}) {
  // Mounted only while open (parent uses a key), so props seed initial state.
  const [values, setValues] = useState<GuestFormValues>(fromGuest(guest));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (k: keyof GuestFormValues, v: string) =>
    setValues((prev) => ({ ...prev, [k]: v }));
  const setPartyAnswer = (qid: string, v: AnswerValue) =>
    setValues((prev) => ({ ...prev, partyAnswers: { ...prev.partyAnswers, [qid]: v } }));
  const setAdult = (i: number, patch: Partial<PersonDraft>) =>
    setValues((prev) => ({
      ...prev,
      adults: prev.adults.map((a, idx) => (idx === i ? { ...a, ...patch } : a)),
    }));
  const setAdultAnswer = (i: number, qid: string, v: AnswerValue) =>
    setValues((prev) => ({
      ...prev,
      adults: prev.adults.map((a, idx) =>
        idx === i ? { ...a, answers: { ...a.answers, [qid]: v } } : a,
      ),
    }));
  const addAdult = () =>
    setValues((prev) => ({ ...prev, adults: [...prev.adults, { name: "", answers: {} }] }));
  const removeAdult = (i: number) =>
    setValues((prev) => ({ ...prev, adults: prev.adults.filter((_, idx) => idx !== i) }));
  const setChild = (i: number, patch: Partial<PersonDraft>) =>
    setValues((prev) => ({
      ...prev,
      children: prev.children.map((c, idx) => (idx === i ? { ...c, ...patch } : c)),
    }));
  const setChildAnswer = (i: number, qid: string, v: AnswerValue) =>
    setValues((prev) => ({
      ...prev,
      children: prev.children.map((c, idx) =>
        idx === i ? { ...c, answers: { ...c.answers, [qid]: v } } : c,
      ),
    }));
  const addChild = () =>
    setValues((prev) => ({ ...prev, children: [...prev.children, { name: "", answers: {} }] }));
  const removeChild = (i: number) =>
    setValues((prev) => ({ ...prev, children: prev.children.filter((_, idx) => idx !== i) }));

  const arcTitle = (id: string) => arcs.find((a) => a.id === id)?.title ?? "Removed arc";

  // RSVP editing only makes sense for an existing guest (a brand-new guest is
  // "pending" until they respond or the owner edits them afterwards).
  const showRsvp = Boolean(guest);
  const attendingNow = showRsvp && values.rsvp_status === "attending";
  // Effective caps by tier: plus_one is always a single adult; plus_family uses the
  // wedding's configured caps (either group can be 0/off); solo has none.
  const adultCap =
    values.invite_tier === "plus_family" ? maxAdults : values.invite_tier === "plus_one" ? 1 : 0;
  const kidCap = values.invite_tier === "plus_family" ? maxKids : 0;
  const showAdult = adultCap > 0;
  const showKids = kidCap > 0;
  const hasAnyQuestion =
    primaryQuestions.length + inviteeQuestions.length + childQuestions.length > 0;

  async function handleSave() {
    if (!values.greeting_name.trim()) {
      setError("Greeting is required — it's the invite's “Dear …” line.");
      return;
    }
    if (attendingNow) {
      // Required party questions (the primary's own + invitee-scope).
      const missingParty = [...primaryQuestions, ...inviteeQuestions].find(
        (q) => q.required && !isAnswered(q, values.partyAnswers[q.id]),
      );
      if (missingParty) {
        setError(`Please answer: ${missingParty.prompt}`);
        return;
      }
      // Required questions for each companion that will be saved.
      if (showAdult) {
        for (const [i, a] of values.adults.entries()) {
          if (!personIncluded(a, primaryQuestions)) continue;
          const m = primaryQuestions.find((q) => q.required && !isAnswered(q, a.answers[q.id]));
          if (m) {
            setError(`Guest ${i + 1} — please answer: ${m.prompt}`);
            return;
          }
        }
      }
      if (showKids) {
        for (const [i, c] of values.children.entries()) {
          if (!personIncluded(c, childQuestions)) continue;
          const m = childQuestions.find((q) => q.required && !isAnswered(q, c.answers[q.id]));
          if (m) {
            setError(`Child ${i + 1} — please answer: ${m.prompt}`);
            return;
          }
        }
      }
    }
    setSaving(true);
    setError(null);
    try {
      await onSubmit(values);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  /** Render a person's answer fields (only meaningful once attending). */
  const answerFields = (
    qs: QuestionAdmin[],
    get: (qid: string) => AnswerValue | undefined,
    onChange: (qid: string, v: AnswerValue) => void,
  ) => qs.map((q) => <AnswerField key={q.id} question={q} value={get(q.id)} onChange={(v) => onChange(q.id, v)} />);

  return (
    <Dialog open onClose={saving ? undefined : onClose} fullWidth maxWidth="sm">
      <DialogTitle>{guest ? "Edit guest" : "Add guest"}</DialogTitle>
      <DialogContent>
        <Stack spacing={1} sx={{ mt: 1 }}>
          {/* 1–3. Invitation: greeting, tier, RSVP status */}
          <Section title="Invitation">
            <TextField
              label="Greeting"
              value={values.greeting_name}
              onChange={(e) => set("greeting_name", e.target.value)}
              required
              autoFocus
              fullWidth
              placeholder="e.g. John & Jane"
              helperText="How the invite says “Dear …”. Required — the only name shown on the cover, for the whole invite."
            />
            <TextField
              label="Invitation tier"
              value={values.invite_tier}
              onChange={(e) => set("invite_tier", e.target.value)}
              select
              fullWidth
              helperText="Controls whether this guest can bring a +1 / kids. Never shown to the guest."
            >
              {TIERS.map((t) => (
                <MenuItem key={t.value} value={t.value}>
                  {t.label}
                </MenuItem>
              ))}
            </TextField>
            {showRsvp && (
              <>
                <TextField
                  label="RSVP status"
                  value={values.rsvp_status}
                  onChange={(e) => set("rsvp_status", e.target.value)}
                  select
                  fullWidth
                  helperText="Record or correct this guest's response on their behalf."
                >
                  {RSVP_STATUSES.map((s) => (
                    <MenuItem key={s.value} value={s.value}>
                      {s.label}
                    </MenuItem>
                  ))}
                </TextField>
                {hasAnyQuestion && !attendingNow && (
                  <Alert severity="info" variant="outlined">
                    Set the status to <strong>Attending</strong> to record each person&rsquo;s
                    answers (dietary, age, song, …). Answers are only kept for guests who are coming.
                  </Alert>
                )}
              </>
            )}
          </Section>

          {/* 4. Fixed guest-level fields */}
          <Section title="Contact & details" defaultExpanded={false}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField
                label="Email"
                type="email"
                value={values.email}
                onChange={(e) => set("email", e.target.value)}
                fullWidth
                helperText="Optional — for the couple's comms"
              />
              <MuiTelInput
                label="Phone"
                value={values.phone}
                onChange={(v) => setValues((prev) => ({ ...prev, phone: v }))}
                defaultCountry="SG"
                fullWidth
              />
            </Stack>
            <Stack direction="row" spacing={2}>
              <TextField label="Side" value={values.side} onChange={(e) => set("side", e.target.value)} fullWidth />
              <TextField
                label="Relationship"
                value={values.relationship}
                onChange={(e) => set("relationship", e.target.value)}
                fullWidth
              />
            </Stack>
            <Stack direction="row" spacing={2}>
              <TextField label="Group" value={values.group_name} onChange={(e) => set("group_name", e.target.value)} fullWidth />
              <TextField label="Batch" value={values.batch} onChange={(e) => set("batch", e.target.value)} fullWidth />
            </Stack>
            <TextField
              label="Expected party size"
              type="number"
              value={values.expected_party_size}
              onChange={(e) => set("expected_party_size", e.target.value)}
              fullWidth
              slotProps={{ htmlInput: { min: 0, max: 50 } }}
              helperText="Your estimate of how many will come, including this guest. Admin-only. Leave blank if unknown."
            />
          </Section>

          {/* 5. Primary guest: name + their own answers */}
          <Section title="Primary guest" subtitle="The invited guest">
            <TextField
              label="Primary guest name (optional)"
              value={values.name}
              onChange={(e) => set("name", e.target.value)}
              fullWidth
              helperText="The main guest's name. Optional — pre-fills their (editable) Name field on the RSVP."
            />
            {attendingNow && answerFields(primaryQuestions, (qid) => values.partyAnswers[qid], setPartyAnswer)}
          </Section>

          {/* 6. Guests: each name + answers, with add/remove (plus_one = 1, plus_family = N) */}
          {showAdult && (
            <Section
              title={values.invite_tier === "plus_one" ? "Plus-one" : "Guests"}
              subtitle={values.invite_tier === "plus_one" ? "The +1 (extra guest)" : `Up to ${adultCap} extra guests`}
            >
              {values.adults.length === 0 && (
                <Typography variant="caption" color="text.secondary">
                  No guests added yet.
                </Typography>
              )}
              {values.adults.map((a, i) => (
                <Box key={i} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, p: 2 }}>
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: attendingNow ? 1.5 : 0 }}>
                    <TextField
                      label={`Guest ${i + 1} name`}
                      value={a.name}
                      onChange={(e) => setAdult(i, { name: e.target.value })}
                      fullWidth
                      placeholder="e.g. Jamie Tan"
                    />
                    <Button color="inherit" onClick={() => removeAdult(i)}>
                      Remove
                    </Button>
                  </Stack>
                  {attendingNow && (
                    <Stack spacing={2}>
                      {answerFields(primaryQuestions, (qid) => a.answers[qid], (qid, v) => setAdultAnswer(i, qid, v))}
                    </Stack>
                  )}
                </Box>
              ))}
              {values.adults.length < adultCap && (
                <Button size="small" onClick={addAdult} sx={{ alignSelf: "flex-start" }}>
                  + Add guest
                </Button>
              )}
            </Section>
          )}

          {/* 7. Children: each name + answers, with add/remove */}
          {showKids && (
            <Section title="Children" subtitle={`Up to ${kidCap} kids`}>
              {values.children.length === 0 && (
                <Typography variant="caption" color="text.secondary">
                  No children added yet.
                </Typography>
              )}
              {values.children.map((c, i) => (
                <Box key={i} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, p: 2 }}>
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: attendingNow ? 1.5 : 0 }}>
                    <TextField
                      label={`Child ${i + 1} name`}
                      value={c.name}
                      onChange={(e) => setChild(i, { name: e.target.value })}
                      fullWidth
                    />
                    <Button color="inherit" onClick={() => removeChild(i)}>
                      Remove
                    </Button>
                  </Stack>
                  {attendingNow && (
                    <Stack spacing={2}>
                      {answerFields(childQuestions, (qid) => c.answers[qid], (qid, v) => setChildAnswer(i, qid, v))}
                    </Stack>
                  )}
                </Box>
              ))}
              {values.children.length < kidCap && (
                <Button size="small" onClick={addChild} sx={{ alignSelf: "flex-start" }}>
                  + Add child
                </Button>
              )}
            </Section>
          )}

          {/* 8. Invitee-level questions (asked once for the whole party) */}
          {inviteeQuestions.length > 0 && (
            <Section title="Invitee questions" subtitle="Asked once for the whole invite">
              {attendingNow ? (
                answerFields(inviteeQuestions, (qid) => values.partyAnswers[qid], setPartyAnswer)
              ) : (
                <Typography variant="caption" color="text.secondary">
                  Set the status to Attending to record these.
                </Typography>
              )}
            </Section>
          )}

          {/* Story-arc override (advanced) */}
          {arcs.length > 1 && (
            <Section title="Story arc override" subtitle="Advanced" defaultExpanded={false}>
              <TextField
                label="Story arc override"
                select
                fullWidth
                value={values.story_arc_ids}
                onChange={(e) =>
                  setValues((prev) => ({
                    ...prev,
                    story_arc_ids:
                      typeof e.target.value === "string"
                        ? e.target.value.split(",").filter(Boolean)
                        : (e.target.value as unknown as string[]),
                  }))
                }
                helperText="Leave empty to show every visible arc. Pick one or more to show only those to this guest."
                slotProps={{
                  select: {
                    multiple: true,
                    displayEmpty: true,
                    renderValue: (selected: unknown) => {
                      const ids = selected as string[];
                      if (ids.length === 0)
                        return <Box sx={{ color: "text.secondary" }}>All visible arcs</Box>;
                      return (
                        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                          {ids.map((id) => (
                            <Chip key={id} size="small" label={arcTitle(id)} />
                          ))}
                        </Box>
                      );
                    },
                  },
                }}
              >
                {arcs.map((a) => (
                  <MenuItem key={a.id} value={a.id}>
                    <Checkbox checked={values.story_arc_ids.includes(a.id)} />
                    <ListItemText primary={a.title} secondary={a.visible ? undefined : "Hidden"} />
                  </MenuItem>
                ))}
              </TextField>
            </Section>
          )}

          {error && (
            <Alert severity="error" variant="outlined">
              {error}
            </Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button onClick={handleSave} variant="contained" disabled={saving}>
          {saving ? "Saving…" : guest ? "Save changes" : "Add guest"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
