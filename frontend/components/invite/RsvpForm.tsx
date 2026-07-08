"use client";

import AddIcon from "@mui/icons-material/Add";
import RemoveIcon from "@mui/icons-material/Remove";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { keyframes } from "@mui/system";
import { MuiTelInput, matchIsValidTel } from "mui-tel-input";
import { useEffect, useMemo, useRef, useState } from "react";

import type { RsvpContent, RsvpStepKey } from "@/lib/content";
import {
  type AnswerValue,
  type Capabilities,
  type QuestionPublic,
  type RsvpPublic,
  type RsvpSubmit,
  submitRsvp,
} from "@/lib/rsvp";

import MascotBadge from "./brand/MascotBadge";
import Paw from "./brand/Paw";
import RichText from "./RichText";
import Section from "./Section";
import { WishesBody, type WishesProps } from "./Wishes";

/** Per-person answers, keyed by question id. */
type Answers = Record<string, AnswerValue>;
/** A companion captured in the form (the +1 adult or a child). */
type Person = { name: string; answers: Answers };

const fall = keyframes`to { transform: translateY(360px) rotate(360deg); opacity: 0; }`;

/** Whether a question's stored value counts as answered (for required checks). */
function isAnswered(q: QuestionPublic, v: AnswerValue | undefined): boolean {
  if (!v) return false;
  switch (q.qtype) {
    case "text":
      return typeof v.text === "string" && v.text.trim() !== "";
    case "number":
      return typeof v.number === "number" && !Number.isNaN(v.number);
    case "choice":
      return typeof v.choice === "string" && v.choice !== "";
    case "multi_choice":
      return Array.isArray(v.choices) && v.choices.length > 0;
    case "yesno":
      return typeof v.yesno === "boolean";
    default:
      return false;
  }
}

/** Build the submit answer list for the questions a person was actually asked. */
function answerList(qs: QuestionPublic[], answers: Answers) {
  return qs
    .filter((q) => isAnswered(q, answers[q.id]))
    .map((q) => ({ question_id: q.id, value: answers[q.id] as AnswerValue }));
}

/** First required-but-unanswered question in the set, or null. */
function firstMissing(qs: QuestionPublic[], answers: Answers): QuestionPublic | null {
  return qs.find((q) => q.required && !isAnswered(q, answers[q.id])) ?? null;
}

/**
 * The RSVP flow — a multi-step, mascot-guided journey with IDENTICAL chrome for
 * every guest. Beyond Name, everything a guest tells us is an admin-defined
 * QUESTION (lib/rsvp QuestionPublic) with a `scope` (invitee = asked once for the
 * party; person = asked of each attendee) and, for person questions, an
 * `applies_to` (everyone / adults / children). The tier is NEVER exposed — the
 * +1 / kids controls simply don't render when capabilities are zero, and the
 * backend re-validates caps + question visibility + per-person applicability.
 */
export default function RsvpForm({
  guestSlug,
  fullName,
  greetingName,
  partyMembers,
  initialEmail,
  initialPhone,
  capabilities,
  questions,
  initialRsvp,
  rsvp,
  wishes,
  guideIconUrl,
}: {
  guestSlug: string;
  fullName: string;
  /** Invitee-level greeting override (e.g. "Riley & Jamie"); used for the intro's {name}. */
  greetingName?: string | null;
  /** Admin-curated prefill party (the +1/kids' names) shown before the guest replies. */
  partyMembers?: { kind: string; name: string }[] | null;
  initialEmail?: string | null;
  initialPhone?: string | null;
  capabilities: Capabilities;
  questions: QuestionPublic[];
  initialRsvp: RsvpPublic | null;
  rsvp: RsvpContent;
  /** Wish-form data, so the confirmation screen can offer "leave a wish" as a final optional step. */
  wishes: WishesProps;
  /** Optional uploaded image for the mascot guide circle in the RSVP flow (admin → Brand mark). */
  guideIconUrl?: string;
}) {
  const fields = rsvp.fields;

  // Split + sort questions by scope/applicability once.
  const inviteeQs = useMemo(
    () => questions.filter((q) => q.scope === "invitee").sort((a, b) => a.sort_order - b.sort_order),
    [questions],
  );
  const personQs = useMemo(
    () => questions.filter((q) => q.scope === "person").sort((a, b) => a.sort_order - b.sort_order),
    [questions],
  );
  // Which person-scope questions a given person is asked.
  const qsFor = useMemo(
    () => (isChild: boolean) =>
      personQs.filter(
        (q) =>
          q.applies_to === "everyone" ||
          (q.applies_to === "adults" && !isChild) ||
          (q.applies_to === "children" && isChild),
      ),
    [personQs],
  );
  const primaryQs = qsFor(false); // the invited guest is an adult
  const adultQs = qsFor(false);
  const childQs = qsFor(true);

  // --- Hydrate from an existing RSVP --------------------------------------
  const qScope = useMemo(() => new Map(questions.map((q) => [q.id, q.scope])), [questions]);
  const initAdults = (initialRsvp?.companions ?? []).filter((c) => c.kind === "adult");
  const initKids = (initialRsvp?.companions ?? []).filter((c) => c.kind === "child");
  const answersFromList = (list: RsvpPublic["answers"]): Answers => {
    const out: Answers = {};
    for (const a of list) out[a.question_id] = a.value as AnswerValue;
    return out;
  };
  const initPartyAnswers = answersFromList(initialRsvp?.answers ?? []);
  const initInviteeAnswers: Answers = {};
  const initPrimaryAnswers: Answers = {};
  for (const [qid, val] of Object.entries(initPartyAnswers)) {
    (qScope.get(qid) === "person" ? initPrimaryAnswers : initInviteeAnswers)[qid] = val;
  }

  // Seed the +1/kids from an existing RSVP if there is one (answers + names), else
  // from the admin's prefill party (names only) so the form opens ready to confirm.
  const prefillAdults = (partyMembers ?? []).filter((m) => m.kind === "adult");
  const prefillKids = (partyMembers ?? []).filter((m) => m.kind === "child");
  const seedAdults: Person[] = initialRsvp
    ? initAdults.map((c) => ({ name: c.name ?? "", answers: answersFromList(c.answers) }))
    : prefillAdults.map((m) => ({ name: m.name ?? "", answers: {} }));
  const seedKids: Person[] = initialRsvp
    ? initKids.map((c) => ({ name: c.name ?? "", answers: answersFromList(c.answers) }))
    : prefillKids.map((m) => ({ name: m.name ?? "", answers: {} }));

  const [attending, setAttending] = useState<boolean | null>(initialRsvp ? initialRsvp.attending : null);
  const [primaryName, setPrimaryName] = useState(fullName);
  const [email, setEmail] = useState(initialEmail ?? "");
  const [phone, setPhone] = useState(initialPhone ?? "");
  const [primaryAnswers, setPrimaryAnswers] = useState<Answers>(initPrimaryAnswers);
  const [inviteeAnswers, setInviteeAnswers] = useState<Answers>(initInviteeAnswers);
  // Open the +1 by default whenever there's a name to confirm (RSVP or prefill).
  const [bringPlusOne, setBringPlusOne] = useState(seedAdults.length > 0);
  const [plusOne, setPlusOne] = useState<Person>(seedAdults[0] ?? { name: "", answers: {} });
  // plus_family can bring several additional adults (add/remove list, like kids);
  // plus_one keeps the single +1 toggle above. Both seed from the same prefill/RSVP
  // adults — only the one matching this invite's mode is rendered/submitted.
  const [adults, setAdults] = useState<Person[]>(seedAdults);
  const [kids, setKids] = useState<Person[]>(seedKids);
  const [note, setNote] = useState(initialRsvp?.notes ?? "");

  const [step, setStep] = useState(0);
  // Each step can be a different height, so advancing/going back can leave the
  // form's top scrolled off-screen. Snap the card's top back into view on every
  // step change (but not on first mount — the page lands wherever it was linked).
  const formTopRef = useRef<HTMLDivElement>(null);
  const didMount = useRef(false);
  useEffect(() => {
    if (!didMount.current) {
      didMount.current = true;
      return;
    }
    formTopRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [step]);
  const [err, setErr] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState<boolean | null>(initialRsvp ? initialRsvp.attending : null);
  const [justSaved, setJustSaved] = useState(false);

  // plus_family renders an add/remove ADULTS list (multiple extra adults); plus_one
  // shows the single +1 toggle. Driven by a capability, never the tier name.
  const multiAdults = capabilities.adults_multi && capabilities.max_adult_companions > 0;
  const singlePlusOne = capabilities.allow_plus_one && !multiAdults;
  const hasParty = capabilities.allow_plus_one || capabilities.max_child_companions > 0;
  const showGuests = hasParty || primaryQs.length > 0;
  const showContacts = fields.collect_email || fields.collect_phone;
  const showExtras = inviteeQs.length > 0;
  // Either/or mode: both contacts collected and "at least one" is on. Neither field
  // is individually required, so don't show a misleading "*" on either.
  const eitherOrContact = fields.require_contact && fields.collect_email && fields.collect_phone;
  const emailRequired = !eitherOrContact && fields.email_required;
  const phoneRequired = !eitherOrContact && fields.phone_required;

  const flow = useMemo<RsvpStepKey[]>(() => {
    if (attending === false) return ["attend", "note"];
    if (attending === true) {
      const f: RsvpStepKey[] = ["attend"];
      if (showContacts) f.push("contacts");
      if (showGuests) f.push("guests");
      if (showExtras) f.push("extras");
      f.push("review");
      return f;
    }
    return ["attend"];
  }, [attending, showContacts, showGuests, showExtras]);
  const cur = flow[Math.min(step, flow.length - 1)] ?? "attend";

  // --- mutators -----------------------------------------------------------
  const setPrimaryAnswer = (qid: string, v: AnswerValue) =>
    setPrimaryAnswers((p) => ({ ...p, [qid]: v }));
  const setInviteeAnswer = (qid: string, v: AnswerValue) =>
    setInviteeAnswers((p) => ({ ...p, [qid]: v }));
  const setPlusOneAnswer = (qid: string, v: AnswerValue) =>
    setPlusOne((p) => ({ ...p, answers: { ...p.answers, [qid]: v } }));
  function setKidCount(n: number) {
    setKids((prev) => {
      const next = prev.slice(0, n);
      while (next.length < n) next.push({ name: "", answers: {} });
      return next;
    });
  }
  const updateKid = (i: number, patch: Partial<Person>) =>
    setKids((prev) => prev.map((k, idx) => (idx === i ? { ...k, ...patch } : k)));
  const setKidAnswer = (i: number, qid: string, v: AnswerValue) =>
    setKids((prev) => prev.map((k, idx) => (idx === i ? { ...k, answers: { ...k.answers, [qid]: v } } : k)));
  function setAdultCount(n: number) {
    setAdults((prev) => {
      const next = prev.slice(0, n);
      while (next.length < n) next.push({ name: "", answers: {} });
      return next;
    });
  }
  const updateAdult = (i: number, patch: Partial<Person>) =>
    setAdults((prev) => prev.map((a, idx) => (idx === i ? { ...a, ...patch } : a)));
  const setAdultAnswer = (i: number, qid: string, v: AnswerValue) =>
    setAdults((prev) => prev.map((a, idx) => (idx === i ? { ...a, answers: { ...a.answers, [qid]: v } } : a)));

  // --- validation ---------------------------------------------------------
  function contactError(): string | null {
    const hasEmail = !!email.trim();
    const hasPhone = !!phone.trim();
    // A typed phone must be a valid number regardless of required-ness.
    if (fields.collect_phone && hasPhone && !matchIsValidTel(phone)) return rsvp.labels.validate_phone;
    // Either/or mode (both contacts collected): at least one must be given, and it
    // OVERRIDES the per-field "required" flags so neither is individually forced.
    if (fields.require_contact && fields.collect_email && fields.collect_phone) {
      return hasEmail || hasPhone ? null : rsvp.labels.validate_contact;
    }
    // Otherwise honour the per-field hard requirements.
    if (fields.collect_email && fields.email_required && !hasEmail) return rsvp.labels.validate_email;
    if (fields.collect_phone && fields.phone_required && !hasPhone) return rsvp.labels.validate_phone;
    return null;
  }
  function guestsError(): string | null {
    if (!primaryName.trim()) return rsvp.labels.validate_your_name;
    if (singlePlusOne && bringPlusOne && !plusOne.name.trim()) {
      return rsvp.labels.validate_plus_one;
    }
    if (firstMissing(primaryQs, primaryAnswers)) return rsvp.labels.validate_required;
    if (singlePlusOne && bringPlusOne && firstMissing(adultQs, plusOne.answers)) {
      return rsvp.labels.validate_required;
    }
    if (multiAdults && adults.some((a) => firstMissing(adultQs, a.answers))) {
      return rsvp.labels.validate_required;
    }
    if (kids.some((k) => firstMissing(childQs, k.answers))) return rsvp.labels.validate_required;
    return null;
  }
  function extrasError(): string | null {
    return firstMissing(inviteeQs, inviteeAnswers) ? rsvp.labels.validate_required : null;
  }

  function go(dir: number) {
    setErr("");
    if (dir > 0) {
      if (cur === "attend" && attending === null) return setErr(rsvp.labels.validate_attend);
      const e =
        cur === "contacts" ? contactError() : cur === "guests" ? guestsError() : cur === "extras" ? extrasError() : null;
      if (e) return setErr(e);
    }
    setStep((s) => Math.min(Math.max(s + dir, 0), flow.length - 1));
  }

  async function handleSubmit() {
    setErr("");
    // Declining only collects a note — skip contact/guest/extra validation,
    // those steps aren't part of the decline flow.
    const e = attending === false ? null : contactError() || guestsError() || extrasError();
    if (e) return setErr(e);
    setSubmitting(true);

    const companions: RsvpSubmit["companions"] = [];
    if (multiAdults) {
      for (const a of adults.slice(0, capabilities.max_adult_companions)) {
        companions.push({ kind: "adult", name: a.name.trim() || null, answers: answerList(adultQs, a.answers) });
      }
    } else if (singlePlusOne && bringPlusOne && plusOne.name.trim()) {
      companions.push({ kind: "adult", name: plusOne.name.trim(), answers: answerList(adultQs, plusOne.answers) });
    }
    for (const k of kids.slice(0, capabilities.max_child_companions)) {
      companions.push({ kind: "child", name: k.name.trim() || null, answers: answerList(childQs, k.answers) });
    }

    const payload: RsvpSubmit = {
      attending: attending!,
      name: primaryName.trim() || null,
      notes: note.trim() || null,
      email: fields.collect_email ? email.trim() || null : null,
      phone: fields.collect_phone ? phone.trim() || null : null,
      companions,
      answers: [...answerList(inviteeQs, inviteeAnswers), ...answerList(primaryQs, primaryAnswers)],
    };

    try {
      await submitRsvp(guestSlug, payload);
      setDone(attending);
      setJustSaved(true);
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  const cardSx = {
    maxWidth: 620,
    mx: "auto",
    p: { xs: 3, sm: 5 },
    border: "2px solid",
    borderColor: "text.primary",
    borderRadius: (t: import("@mui/material/styles").Theme) => `${t.extra.radiusLg}px`,
    bgcolor: "background.default",
    boxShadow: (t: import("@mui/material/styles").Theme) => t.extra.shadows.pop,
    position: "relative" as const,
    overflow: "hidden" as const,
  };

  // --- Confirmation view ---------------------------------------------------
  if (justSaved) {
    return (
      <Section id="rsvp" kicker={rsvp.kicker} heading={rsvp.heading} maxWidth="md">
        <Paper elevation={0} sx={cardSx}>
          {done && <Confetti />}
          <Stack spacing={2.5} sx={{ alignItems: "center", textAlign: "center", py: 2 }}>
            <MascotBadge size={86} mood={done ? "happy" : "idle"} imageUrl={guideIconUrl} />
            <Typography variant="h3" component="h3">
              <RichText text={done ? rsvp.confirm.yes_title : rsvp.confirm.no_title} variant="inline" />
            </Typography>
            <Typography sx={{ color: "text.secondary", maxWidth: 420, lineHeight: 1.7 }}>
              <RichText text={done ? rsvp.confirm.yes_body : rsvp.confirm.no_body} />
            </Typography>
            <Button variant="text" color="inherit" onClick={() => { setJustSaved(false); setStep(0); }}>
              {rsvp.buttons.edit}
            </Button>
          </Stack>

          {/* Final optional step: leave a wish (the RSVP is already saved). Same
              form as the standalone #wishes section; the wall lives there, so we
              show just the form here to avoid duplicating the list back-to-back. */}
          <Box sx={{ borderTop: "2px solid", borderColor: "divider", mt: 3, pt: 4 }}>
            <Typography variant="h4" component="h3" sx={{ textAlign: "center", mb: 2 }}>
              {wishes.copy.heading || "Leave us a wish"}
            </Typography>
            <WishesBody {...wishes} showWall={false} />
          </Box>
        </Paper>
      </Section>
    );
  }

  // --- The flow ------------------------------------------------------------
  const intro = (rsvp.intro ?? "").replace("{name}", greetingName?.trim() || fullName);
  const isLast = step >= flow.length - 1;

  return (
    <Section id="rsvp" kicker={rsvp.kicker} heading={rsvp.heading} intro={intro || undefined} maxWidth="md">
      <Paper ref={formTopRef} elevation={0} sx={{ ...cardSx, scrollMarginTop: 88 }}>
        {/* Mascot guide + speech bubble */}
        <Stack direction="row" spacing={2} sx={{ alignItems: "center", mb: 3 }}>
          <MascotBadge size={56} mood={cur === "review" ? "happy" : "peek"} imageUrl={guideIconUrl} />
          <Box
            sx={{
              position: "relative",
              bgcolor: "background.paper",
              border: "2px solid",
              borderColor: "text.primary",
              borderRadius: 3,
              px: 2,
              py: 1.25,
              fontFamily: (t) => t.extra.typography.story,
              fontStyle: "italic",
            }}
          >
            <RichText text={rsvp.speech[cur] ?? ""} variant="inline" />
          </Box>
        </Stack>

        {/* Paw-trail progress */}
        <Stack direction="row" spacing={1} sx={{ justifyContent: "center", mb: 3 }}>
          {flow.map((s, i) => (
            <Paw
              key={s + i}
              size={20}
              sx={{
                color: i <= step ? "primary.main" : "divider",
                transform: i === step ? "scale(1.25)" : "none",
                transition: "color .2s, transform .2s",
              }}
            />
          ))}
        </Stack>

        {/* Step body */}
        <Box sx={{ minHeight: 180 }}>
          {cur === "attend" && (
            <StepShell lead={rsvp.steps.attend.lead} title={rsvp.steps.attend.title}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <ChoiceCard
                  emoji={rsvp.choices.yes.emoji}
                  title={rsvp.choices.yes.title}
                  sub={rsvp.choices.yes.sub}
                  selected={attending === true}
                  tone="success"
                  onClick={() => { setAttending(true); setErr(""); }}
                />
                <ChoiceCard
                  emoji={rsvp.choices.no.emoji}
                  title={rsvp.choices.no.title}
                  sub={rsvp.choices.no.sub}
                  selected={attending === false}
                  tone="error"
                  onClick={() => { setAttending(false); setErr(""); }}
                />
              </Stack>
            </StepShell>
          )}

          {cur === "contacts" && (
            <StepShell lead={rsvp.steps.contacts.lead} title={rsvp.steps.contacts.title}>
              <Stack spacing={2}>
                {fields.collect_email && (
                  <TextField
                    type="email"
                    label={rsvp.labels.email_label}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required={emailRequired}
                    fullWidth
                  />
                )}
                {fields.collect_phone && (
                  <MuiTelInput
                    label={rsvp.labels.phone_label}
                    value={phone}
                    onChange={(v) => setPhone(v)}
                    defaultCountry="SG"
                    required={phoneRequired}
                    fullWidth
                  />
                )}
              </Stack>
            </StepShell>
          )}

          {cur === "guests" && (
            <StepShell lead={rsvp.steps.guests.lead} title={rsvp.steps.guests.title}>
              <Stack spacing={3}>
                {/* The invited guest — Name now editable (prefilled), plus their own
                    person questions. Identical chrome to the +1 block. */}
                <PersonBlock
                  name={primaryName}
                  nameLabel={rsvp.labels.your_name}
                  onName={setPrimaryName}
                  questions={primaryQs}
                  answers={primaryAnswers}
                  onAnswer={setPrimaryAnswer}
                />

                {singlePlusOne && (
                  <Box>
                    <ToggleRow on={bringPlusOne} onClick={() => setBringPlusOne((v) => !v)}>
                      {rsvp.labels.plus_one_toggle}
                    </ToggleRow>
                    {bringPlusOne && (
                      <Box sx={{ mt: 2 }}>
                        <PersonBlock
                          name={plusOne.name}
                          namePlaceholder={rsvp.labels.plus_one_placeholder}
                          nameLabel={rsvp.labels.plus_one_name}
                          onName={(v) => setPlusOne((p) => ({ ...p, name: v }))}
                          questions={adultQs}
                          answers={plusOne.answers}
                          onAnswer={setPlusOneAnswer}
                        />
                      </Box>
                    )}
                  </Box>
                )}

                {multiAdults && (
                  <Box>
                    <Typography sx={{ fontWeight: 600, mb: 1 }}>{rsvp.labels.adults_prompt}</Typography>
                    <Stepper
                      value={adults.length}
                      min={0}
                      max={capabilities.max_adult_companions}
                      onChange={setAdultCount}
                      label={adults.length === 0 ? "No other guests" : adults.length === 1 ? "1 guest" : `${adults.length} guests`}
                    />
                    {adults.length > 0 && (
                      <Stack spacing={2} sx={{ mt: 2 }}>
                        {adults.map((a, i) => (
                          <PersonBlock
                            key={i}
                            name={a.name}
                            nameLabel={rsvp.labels.adult_name}
                            onName={(v) => updateAdult(i, { name: v })}
                            questions={adultQs}
                            answers={a.answers}
                            onAnswer={(qid, v) => setAdultAnswer(i, qid, v)}
                          />
                        ))}
                      </Stack>
                    )}
                  </Box>
                )}

                {capabilities.max_child_companions > 0 && (
                  <Box>
                    <Typography sx={{ fontWeight: 600, mb: 1 }}>{rsvp.labels.kids_prompt}</Typography>
                    <Stepper
                      value={kids.length}
                      min={0}
                      max={capabilities.max_child_companions}
                      onChange={setKidCount}
                      label={kids.length === 0 ? "No kids" : kids.length === 1 ? "1 child" : `${kids.length} children`}
                    />
                    {kids.length > 0 && (
                      <Stack spacing={2} sx={{ mt: 2 }}>
                        {kids.map((k, i) => (
                          <PersonBlock
                            key={i}
                            name={k.name}
                            nameLabel={rsvp.labels.kid_name}
                            onName={(v) => updateKid(i, { name: v })}
                            questions={childQs}
                            answers={k.answers}
                            onAnswer={(qid, v) => setKidAnswer(i, qid, v)}
                          />
                        ))}
                      </Stack>
                    )}
                  </Box>
                )}
              </Stack>
            </StepShell>
          )}

          {cur === "extras" && (
            <StepShell lead={rsvp.steps.extras.lead} title={rsvp.steps.extras.title}>
              <Stack spacing={3}>
                {inviteeQs.map((q) => (
                  <QuestionField
                    key={q.id}
                    question={q}
                    value={inviteeAnswers[q.id]}
                    onChange={(v) => setInviteeAnswer(q.id, v)}
                  />
                ))}
              </Stack>
            </StepShell>
          )}

          {cur === "review" && (
            <StepShell lead={rsvp.steps.review.lead} title={rsvp.steps.review.title}>
              <Review
                rows={[
                  [rsvp.review_labels.attending, rsvp.review_labels.attending_value],
                  singlePlusOne && bringPlusOne ? [rsvp.review_labels.plus_one, plusOne.name || "—"] : null,
                  multiAdults && adults.length > 0
                    ? [rsvp.review_labels.adults, adults.map((a) => a.name || "Guest").join(", ")]
                    : null,
                  capabilities.max_child_companions > 0 && kids.length > 0
                    ? [rsvp.review_labels.children, kids.map((k) => k.name || "Child").join(", ")]
                    : null,
                  fields.collect_email && email.trim() ? [rsvp.labels.email_label, email.trim()] : null,
                  fields.collect_phone && phone.trim() ? [rsvp.labels.phone_label, phone.trim()] : null,
                ]}
              />
            </StepShell>
          )}

          {cur === "note" && (
            <StepShell lead={rsvp.steps.note.lead} title={rsvp.steps.note.title}>
              <TextField
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={rsvp.note_placeholder ?? "(optional)"}
                fullWidth
                multiline
                minRows={4}
              />
            </StepShell>
          )}
        </Box>

        {err && <Alert severity="error" sx={{ mt: 2 }}>{err}</Alert>}

        {/* Nav */}
        <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mt: 3 }}>
          <Box>
            {step > 0 && (
              <Button variant="text" color="inherit" onClick={() => go(-1)}>
                {rsvp.buttons.back}
              </Button>
            )}
          </Box>
          {cur === "attend" && attending === null ? (
            // No choice yet: show a disabled "Next" rather than jumping straight to
            // the submit button — the guest must pick attend/decline first.
            <Button variant="contained" color="primary" disabled endIcon={<Paw size={16} sx={{ color: "#fff" }} />} sx={{ borderRadius: 999, px: 3 }}>
              {rsvp.buttons.next}
            </Button>
          ) : !isLast ? (
            <Button variant="contained" color="primary" onClick={() => go(1)} endIcon={<Paw size={16} sx={{ color: "#fff" }} />} sx={{ borderRadius: 999, px: 3 }}>
              {rsvp.buttons.next}
            </Button>
          ) : (
            <Button variant="contained" color="primary" onClick={handleSubmit} disabled={submitting} endIcon={<Paw size={16} sx={{ color: "#fff" }} />} sx={{ borderRadius: 999, px: 3 }}>
              {submitting ? rsvp.buttons.sending : attending === false ? rsvp.buttons.send_decline : rsvp.buttons.send}
            </Button>
          )}
        </Stack>
      </Paper>
    </Section>
  );
}

// --- small presentational pieces -------------------------------------------

function StepShell({ lead, title, children }: { lead: string; title: string; children: React.ReactNode }) {
  return (
    <Stack spacing={2}>
      <Box>
        <Typography sx={{ color: "text.secondary", fontSize: 13, letterSpacing: "0.08em", textTransform: "uppercase" }}>
          <RichText text={lead} variant="inline" />
        </Typography>
        <Typography variant="h4" component="h3" sx={{ mt: 0.5 }}>
          <RichText text={title} variant="inline" />
        </Typography>
      </Box>
      {children}
    </Stack>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <Typography sx={{ fontWeight: 600 }}>{children}</Typography>;
}

/**
 * One attendee's block: their Name (read-only for the invited guest, editable for
 * a +1 / child) followed by the questions that apply to them. Bordered so each
 * person reads as a distinct card.
 */
function PersonBlock({
  heading,
  name,
  nameLabel,
  namePlaceholder,
  onName,
  questions,
  answers,
  onAnswer,
}: {
  heading?: string;
  name: string;
  nameLabel?: string;
  namePlaceholder?: string;
  onName?: (v: string) => void;
  questions: QuestionPublic[];
  answers: Answers;
  onAnswer: (qid: string, v: AnswerValue) => void;
}) {
  return (
    <Box sx={{ border: "2px solid", borderColor: "divider", borderRadius: 2, p: 2 }}>
      <Stack spacing={2}>
        {onName ? (
          <TextField label={nameLabel ?? "Name"} value={name} placeholder={namePlaceholder} onChange={(e) => onName(e.target.value)} fullWidth />
        ) : (
          <Box>
            {heading && (
              <Typography sx={{ color: "text.secondary", fontSize: 12, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                {heading}
              </Typography>
            )}
            <Typography sx={{ fontWeight: 700 }}>{name}</Typography>
          </Box>
        )}
        {questions.map((q) => (
          <QuestionField key={q.id} question={q} value={answers[q.id]} onChange={(v) => onAnswer(q.id, v)} />
        ))}
      </Stack>
    </Box>
  );
}

function ChoiceCard({
  emoji,
  title,
  sub,
  selected,
  tone,
  onClick,
}: {
  emoji?: string;
  title?: string;
  sub?: string;
  selected: boolean;
  tone: "success" | "error";
  onClick: () => void;
}) {
  return (
    <Box
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onClick()}
      sx={{
        flex: 1,
        cursor: "pointer",
        textAlign: "center",
        p: 3,
        borderRadius: 3,
        border: "2px solid",
        borderColor: selected ? `${tone}.main` : "divider",
        bgcolor: selected ? `${tone}.main` : "background.paper",
        color: selected ? "#fff" : "text.primary",
        transition: "all .15s ease",
        "&:hover": { borderColor: `${tone}.main`, transform: "translateY(-2px)" },
      }}
    >
      <Box sx={{ fontSize: 32 }}>{emoji}</Box>
      <Typography sx={{ fontWeight: 700, mt: 0.5 }}>
        <RichText text={title} variant="inline" />
      </Typography>
      <Typography sx={{ fontSize: 13, opacity: 0.85 }}>
        <RichText text={sub} variant="inline" />
      </Typography>
    </Box>
  );
}

function ToggleRow({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <Box
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onClick()}
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        cursor: "pointer",
        p: 1.5,
        borderRadius: 2,
        border: "2px solid",
        borderColor: on ? "primary.main" : "divider",
        bgcolor: on ? (t) => `${t.extra.colors.primary}14` : "transparent",
        transition: "all .15s ease",
      }}
    >
      <Box sx={{ width: 18, height: 18, borderRadius: "50%", border: "2px solid", borderColor: on ? "primary.main" : "divider", bgcolor: on ? "primary.main" : "transparent", flex: "none" }} />
      <Box>{children}</Box>
    </Box>
  );
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <Box
      component="button"
      type="button"
      onClick={onClick}
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.75,
        cursor: "pointer",
        px: 1.75,
        py: 0.75,
        borderRadius: 999,
        border: "2px solid",
        borderColor: on ? "primary.main" : "divider",
        bgcolor: on ? "primary.main" : "transparent",
        color: on ? "#fff" : "text.primary",
        fontWeight: 600,
        fontSize: 14,
        fontFamily: "inherit",
      }}
    >
      {on && <Paw size={13} sx={{ color: "#fff" }} />}
      {children}
    </Box>
  );
}

function Stepper({ value, min, max, onChange, label }: { value: number; min: number; max: number; onChange: (v: number) => void; label: string }) {
  const btn = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: 36,
    height: 36,
    p: 0,
    borderRadius: "50%",
    border: "2px solid",
    borderColor: "text.primary",
    color: "text.primary",
    bgcolor: "transparent",
    cursor: "pointer",
    lineHeight: 1,
    fontFamily: "inherit",
    "&:disabled": { opacity: 0.35, cursor: "default" },
  };
  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
      <Box component="button" type="button" aria-label="Remove one" sx={btn} disabled={value <= min} onClick={() => onChange(Math.max(min, value - 1))}>
        <RemoveIcon fontSize="small" />
      </Box>
      <Typography sx={{ fontWeight: 700, minWidth: 16, textAlign: "center" }}>{value}</Typography>
      <Box component="button" type="button" aria-label="Add one" sx={btn} disabled={value >= max} onClick={() => onChange(Math.min(max, value + 1))}>
        <AddIcon fontSize="small" />
      </Box>
      <Typography sx={{ fontSize: 13, color: "text.secondary", ml: 1 }}>{label}</Typography>
    </Stack>
  );
}

function Review({ rows }: { rows: ([string, string] | null)[] }) {
  const items = rows.filter((r): r is [string, string] => r !== null);
  return (
    <Box sx={{ border: "2px solid", borderColor: "divider", borderRadius: 2, overflow: "hidden" }}>
      {items.map(([k, v], i) => (
        <Stack
          key={k}
          direction="row"
          sx={{ justifyContent: "space-between", gap: 2, px: 2, py: 1.5, bgcolor: i % 2 ? "background.default" : "background.paper" }}
        >
          <Typography sx={{ color: "text.secondary", fontWeight: 600, fontSize: 14 }}>{k}</Typography>
          <Typography sx={{ fontWeight: 600, textAlign: "right" }}>{v}</Typography>
        </Stack>
      ))}
    </Box>
  );
}

function Confetti() {
  // Deterministic pseudo-random so it's pure (no Math.random during render) yet
  // still looks scattered. Decorative only.
  const pieces = useMemo(() => {
    const tones = ["primary.main", "secondary.main", "success.main", "error.main"];
    const r = (i: number, n: number) => ((i * 9301 + n * 49297) % 233280) / 233280;
    return Array.from({ length: 24 }, (_, i) => ({
      left: r(i, 1) * 100,
      delay: r(i, 2) * 0.5,
      dur: 1.6 + r(i, 3) * 1.4,
      tone: tones[i % 4],
    }));
  }, []);
  return (
    <Box aria-hidden sx={{ position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none" }}>
      {pieces.map((p, i) => (
        <Box
          key={i}
          sx={{
            position: "absolute",
            top: -16,
            left: `${p.left}%`,
            width: 8,
            height: 12,
            bgcolor: p.tone,
            borderRadius: "2px",
            animation: `${fall} ${p.dur}s ${p.delay}s ease-in forwards`,
            "@media (prefers-reduced-motion: reduce)": { display: "none" },
          }}
        />
      ))}
    </Box>
  );
}

/** A single question, rendered by type. Value shapes: {text|number|choice|choices|yesno}. */
function QuestionField({
  question,
  value,
  onChange,
}: {
  question: QuestionPublic;
  value: AnswerValue | undefined;
  onChange: (v: AnswerValue) => void;
}) {
  const label = question.required ? `${question.prompt} *` : question.prompt;
  const options = (question.options as unknown[]).map((o) => String(o));

  if (question.qtype === "text") {
    return (
      <Box>
        <FieldLabel>{label}</FieldLabel>
        <TextField value={value?.text ?? ""} onChange={(e) => onChange({ text: e.target.value })} fullWidth multiline minRows={1} sx={{ mt: 1 }} />
      </Box>
    );
  }

  if (question.qtype === "number") {
    return (
      <Box>
        <FieldLabel>{label}</FieldLabel>
        <TextField
          value={value?.number != null ? String(value.number) : ""}
          onChange={(e) => {
            const digits = e.target.value.replace(/[^0-9]/g, "");
            onChange(digits === "" ? {} : { number: Number(digits) });
          }}
          inputMode="numeric"
          sx={{ mt: 1, width: { xs: "100%", sm: 160 } }}
        />
      </Box>
    );
  }

  if (question.qtype === "yesno") {
    const current = typeof value?.yesno === "boolean" ? value.yesno : null;
    return (
      <Box>
        <FieldLabel>{label}</FieldLabel>
        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
          {[["Yes", true], ["No", false]].map(([lab, val]) => (
            <Chip key={String(lab)} on={current === val} onClick={() => onChange({ yesno: val as boolean })}>
              {lab as string}
            </Chip>
          ))}
        </Stack>
      </Box>
    );
  }

  if (question.qtype === "multi_choice") {
    const chosen = Array.isArray(value?.choices) ? value!.choices! : [];
    const toggle = (opt: string) =>
      onChange({ choices: chosen.includes(opt) ? chosen.filter((c) => c !== opt) : [...chosen, opt] });
    return (
      <Box>
        <FieldLabel>{label}</FieldLabel>
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mt: 1 }}>
          {options.map((opt) => (
            <Chip key={opt} on={chosen.includes(opt)} onClick={() => toggle(opt)}>
              {opt}
            </Chip>
          ))}
        </Box>
      </Box>
    );
  }

  // choice (single select)
  return (
    <Box>
      <FieldLabel>{label}</FieldLabel>
      <Stack spacing={1} sx={{ mt: 1 }}>
        {options.map((opt) => (
          <ToggleRow key={opt} on={value?.choice === opt} onClick={() => onChange({ choice: opt })}>
            {opt}
          </ToggleRow>
        ))}
      </Stack>
    </Box>
  );
}
