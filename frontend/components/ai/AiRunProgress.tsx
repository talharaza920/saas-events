"use client";

import { useEffect, useRef, useState } from "react";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { aiApi, type AiJobAdmin } from "@/lib/adminApi";

/** Owner-facing labels for the pipeline's fixed step names (app/ai/jobs.py). */
const STEP_LABELS: Record<string, string> = {
  transcribe: "Reading your submissions",
  extract: "Pulling out the facts",
  resolve: "Checking venue details",
  draft: "Writing your story",
  images: "Illustrating the beats",
  ground: "Fact-checking the draft",
  glyph: "Designing your mark",
  guests: "Reading the guest list",
};

const STEPS_BY_KIND: Record<string, string[]> = {
  details: ["transcribe", "extract", "resolve"],
  story_arc: ["transcribe", "extract", "draft", "images", "ground"],
  glyph: ["transcribe", "glyph"],
  guests: ["transcribe", "guests"],
};

/**
 * Drives a queued/running job one step at a time (POST /advance) and reports
 * every update upward. `expected_step` makes each advance replay-safe, so a
 * duplicate request (React StrictMode re-runs effects in dev) is a server-side
 * no-op rather than a double step. A 503 (kill switch / daily cost ceiling)
 * leaves the job queued — we surface the message and offer a manual retry.
 */
export default function AiRunProgress({
  job,
  onJob,
}: {
  job: AiJobAdmin;
  onJob: (j: AiJobAdmin) => void;
}) {
  const [paused, setPaused] = useState<string | null>(null);
  const advancing = useRef(false);

  const active = job.status === "queued" || job.status === "running";

  useEffect(() => {
    if (!active || paused || advancing.current) return;
    advancing.current = true;
    aiApi
      .advanceJob(job.id, job.step)
      .then((next) => onJob(next))
      .catch((e) => setPaused(e instanceof Error ? e.message : "The run hit a snag."))
      .finally(() => {
        advancing.current = false;
      });
    // Depend on the job OBJECT, not just its step: the images fan-out step
    // legitimately returns the same step number while it works through beats,
    // and each server response (a fresh object) must trigger the next pass.
  }, [active, paused, job, onJob]);

  if (!active && !paused) return null;

  const stepName = STEPS_BY_KIND[job.kind]?.[job.step];
  const label = (stepName && STEP_LABELS[stepName]) || "Working…";

  return (
    <Stack spacing={1.5}>
      {paused ? (
        <Alert
          severity="warning"
          action={
            <Button color="inherit" size="small" onClick={() => setPaused(null)}>
              Try again
            </Button>
          }
        >
          {paused}
        </Alert>
      ) : (
        <>
          <Typography color="text.secondary">{label}…</Typography>
          <Box>
            <LinearProgress
              variant="determinate"
              value={(job.step / Math.max(job.steps_total, 1)) * 100}
            />
            <Typography variant="caption" color="text.secondary">
              Step {Math.min(job.step + 1, job.steps_total)} of {job.steps_total}
            </Typography>
          </Box>
        </>
      )}
    </Stack>
  );
}
