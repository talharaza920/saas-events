"use client";

import { useState } from "react";

import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { aiApi, type AiJobAdmin } from "@/lib/adminApi";

export interface GuestQuestion {
  about_line?: string;
  question?: string;
}

/** Open questions on a guest-list proposal (8.5c). */
export function questionsOf(job: AiJobAdmin): GuestQuestion[] {
  const raw = (job.proposal as Record<string, unknown> | null)?.questions;
  return Array.isArray(raw) ? (raw as GuestQuestion[]) : [];
}

/**
 * The ask-back (AI_WIZARD_PLAN 8.5c). A guest list is the one submission that is
 * routinely ambiguous — "Sam's parents", "the Chens" — and the two things a model
 * can do with those on its own are both bad: invent a party, or drop the line.
 * So it asks, the couple answers in two seconds, and ONE more extraction runs.
 *
 * Answering is free (we're asking because we were unsure), and it is optional:
 * the list already on the table is applicable exactly as it stands, and anything
 * left unanswered is handed back as "add this one yourself" rather than guessed.
 */
export default function GuestQuestions({
  job,
  onJob,
  disabled,
}: {
  job: AiJobAdmin;
  onJob: (j: AiJobAdmin) => void;
  disabled?: boolean;
}) {
  const questions = questionsOf(job);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (questions.length === 0) return null;

  const filled = questions
    .map((_, i) => ({ index: i, answer: (answers[i] ?? "").trim() }))
    .filter((a) => a.answer !== "");

  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      onJob(await aiApi.answerQuestions(job.id, filled));
      setAnswers({});
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send your answers.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Paper variant="outlined" sx={{ p: 2, borderColor: "warning.main" }}>
      <Stack spacing={1.5}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <HelpOutlineIcon fontSize="small" color="warning" />
          <Typography variant="subtitle1">
            {questions.length === 1 ? "One thing I couldn't read" : "A few things I couldn't read"}
          </Typography>
        </Stack>
        <Typography variant="body2" color="text.secondary">
          {questions.length === 1
            ? "I've left this entry out rather than guess who it means."
            : "I've left these entries out rather than guess who they mean."}{" "}
          Answer what you like and I&apos;ll take one more pass — it&apos;s free, and anything you
          skip is simply left for you to add yourself.
        </Typography>

        {error && (
          <Alert severity="error" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {questions.map((q, i) => (
          <Stack key={i} spacing={0.5}>
            <Typography variant="body2">
              <strong>{q.about_line}</strong> — {q.question}
            </Typography>
            <TextField
              size="small"
              fullWidth
              placeholder="Mari and Tomas Ito"
              value={answers[i] ?? ""}
              disabled={busy || disabled}
              onChange={(e) => setAnswers({ ...answers, [i]: e.target.value.slice(0, 200) })}
            />
          </Stack>
        ))}

        <Stack direction="row">
          <Button
            variant="outlined"
            disabled={busy || disabled || filled.length === 0}
            startIcon={busy ? <CircularProgress size={16} /> : undefined}
            onClick={send}
          >
            Send {filled.length === 1 ? "answer" : "answers"}
          </Button>
        </Stack>
      </Stack>
    </Paper>
  );
}
