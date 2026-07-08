"use client";

import { useMemo, useState } from "react";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import type {
  AnswerValue,
  CompanionAdmin,
  CompanionUpdate,
  QuestionAdmin,
} from "@/lib/adminApi";

import AnswerField, { isAnswered } from "./AnswerField";

/**
 * Edit one companion (the +1 or a child) attached to a guest's RSVP: their Name
 * plus the per-person questions that apply to them (everyone / their kind). `kind`
 * is structural (tier-gated at invite time) so it's shown read-only. The primary
 * invitee is edited via GuestFormDialog instead — only the primary carries the link.
 */
export default function CompanionFormDialog({
  companion,
  invitee,
  questions,
  onClose,
  onSubmit,
}: {
  companion: CompanionAdmin;
  invitee: string;
  questions: QuestionAdmin[];
  onClose: () => void;
  onSubmit: (values: CompanionUpdate) => Promise<void>;
}) {
  const isChild = companion.kind === "child";
  // The person-scope questions that apply to this companion.
  const applicable = useMemo(
    () =>
      questions
        .filter((q) => q.scope === "person")
        .filter(
          (q) =>
            q.applies_to === "everyone" ||
            (q.applies_to === "adults" && !isChild) ||
            (q.applies_to === "children" && isChild),
        )
        .sort((a, b) => a.sort_order - b.sort_order),
    [questions, isChild],
  );

  const [name, setName] = useState(companion.name ?? "");
  const [answers, setAnswers] = useState<Record<string, AnswerValue>>(() => {
    const out: Record<string, AnswerValue> = {};
    for (const a of companion.answers ?? []) out[a.question_id] = a.value;
    return out;
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setAnswer = (qid: string, v: AnswerValue) => setAnswers((p) => ({ ...p, [qid]: v }));

  async function handleSave() {
    const missing = applicable.find((q) => q.required && !isAnswered(q, answers[q.id]));
    if (missing) {
      setError(`Please answer: ${missing.prompt}`);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const answerList = applicable
        .filter((q) => isAnswered(q, answers[q.id]))
        .map((q) => ({ question_id: q.id, value: answers[q.id] }));
      await onSubmit({ name: name.trim() || null, answers: answerList });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open onClose={saving ? undefined : onClose} fullWidth maxWidth="xs">
      <DialogTitle>Edit {isChild ? "child" : "guest"}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="caption" color="text.secondary">
            {isChild ? "Child" : "Guest"} of {invitee}
          </Typography>
          <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} autoFocus fullWidth />
          {applicable.map((q) => (
            <AnswerField key={q.id} question={q} value={answers[q.id]} onChange={(v) => setAnswer(q.id, v)} />
          ))}
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
          {saving ? "Saving…" : "Save changes"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
