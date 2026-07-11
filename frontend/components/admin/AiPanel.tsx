"use client";

import { useCallback, useEffect, useState } from "react";

import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import {
  aiApi,
  type AdminMe,
  type AiCreditsInfo,
  type AiJobAdmin,
  type AiJobKind,
} from "@/lib/adminApi";
import AiReviewPanel from "@/components/ai/AiReviewPanel";
import AiRunProgress from "@/components/ai/AiRunProgress";

const ACTIVE = new Set(["queued", "running", "awaiting_review"]);

const KIND_LABELS: Record<string, string> = {
  wizard: "Full draft",
  story_arc: "Story chapter",
  glyph: "Mark",
};

const STATUS_COLORS: Record<string, "default" | "info" | "success" | "warning" | "error"> = {
  queued: "info",
  running: "info",
  awaiting_review: "warning",
  applied: "success",
  failed: "error",
  cancelled: "default",
  expired: "default",
};

/**
 * The wedding's AI assistant (AI_WIZARD_PLAN 8.4b): start a story-chapter or
 * mark run, watch it advance, review/steer/apply the result. Post-onboarding
 * regeneration is deliberately "just a new job" — same pipeline, same
 * metering, same review gate as the /create wizard.
 */
export default function AiPanel({
  me,
  onChanged,
}: {
  me: AdminMe;
  onChanged: () => Promise<void> | void;
}) {
  const enabled = me.entitlements?.ai_enabled === true;
  const [jobs, setJobs] = useState<AiJobAdmin[] | null>(null);
  const [job, setJob] = useState<AiJobAdmin | null>(null); // the run in focus (with variants)
  const [credits, setCredits] = useState<AiCreditsInfo | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [list, cr] = await Promise.all([aiApi.listJobs(), aiApi.credits()]);
      setJobs(list);
      setCredits(cr);
      // Revive an in-flight or reviewable run (e.g. after a reload). The list
      // omits variants, so fetch the full job.
      const active = list.find((j) => ACTIVE.has(j.status));
      setJob(active ? await aiApi.getJob(active.id) : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load AI runs.");
      setJobs([]);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    // Fetch-on-mount: setState happens after load()'s first await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [enabled, load]);

  if (!enabled) {
    return (
      <Alert severity="info">
        AI assistance isn&apos;t available on this wedding&apos;s plan — contact us to upgrade.
      </Alert>
    );
  }

  const start = async (kind: AiJobKind) => {
    setBusy(true);
    setError(null);
    try {
      const t = text.trim();
      const inputIds: string[] = [];
      if (t) inputIds.push((await aiApi.createInput(t)).id);
      const created = await aiApi.createJob(kind, inputIds, {}, crypto.randomUUID());
      setText("");
      setJob(created);
      setJobs((js) => [created, ...(js ?? [])]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the run.");
    } finally {
      setBusy(false);
    }
  };

  // After an apply: refresh the dashboard + the list/credits, but do NOT
  // re-derive `job` from the list — that would unmount the review panel's
  // success state (and the "use as cover icon" switch) mid-interaction.
  const jobDone = async () => {
    await onChanged();
    try {
      const [list, cr] = await Promise.all([aiApi.listJobs(), aiApi.credits()]);
      setJobs(list);
      setCredits(cr);
    } catch {
      /* the panel's own state is already correct; the list can refresh later */
    }
  };

  return (
    <Stack spacing={3}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
        <Typography variant="h6" sx={{ flexGrow: 1 }}>
          AI assistant
        </Typography>
        {credits && (
          <Chip size="small" variant="outlined" label={`Credits: ${credits.remaining}`} />
        )}
        {credits && (
          <Chip
            size="small"
            variant="outlined"
            label={`Included story drafts used: ${credits.arc_generations_used}/${credits.arc_generations_included}`}
          />
        )}
      </Stack>

      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {job && ACTIVE.has(job.status) ? (
        <Paper variant="outlined" sx={{ p: 2.5 }}>
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <Typography variant="subtitle1" sx={{ flexGrow: 1 }}>
                {KIND_LABELS[job.kind] ?? job.kind}
              </Typography>
              <Chip size="small" label={job.status.replace(/_/g, " ")} color={STATUS_COLORS[job.status]} />
            </Stack>
            <AiRunProgress job={job} onJob={setJob} />
            {job.status === "awaiting_review" && (
              <AiReviewPanel job={job} onJob={setJob} onApplied={jobDone} />
            )}
          </Stack>
        </Paper>
      ) : (
        <Paper variant="outlined" sx={{ p: 2.5 }}>
          <Stack spacing={2}>
            <Typography variant="subtitle1">Start a run</Typography>
            <Typography variant="body2" color="text.secondary">
              Paste anything — how you met, the proposal, a voice-note transcript — and the AI
              drafts a story chapter from it. Or have it design a simple monochrome mark for your
              cover. You review everything before it touches your site.
            </Typography>
            <TextField
              multiline
              minRows={3}
              fullWidth
              label="What should it work from?"
              placeholder="Required for a story chapter; optional inspiration for a mark."
              value={text}
              onChange={(e) => setText(e.target.value.slice(0, 20000))}
            />
            <Stack direction="row" spacing={1.5} sx={{ flexWrap: "wrap" }}>
              <Button
                variant="contained"
                startIcon={busy ? <CircularProgress size={16} /> : <AutoAwesomeIcon />}
                disabled={busy || !text.trim()}
                onClick={() => start("story_arc")}
              >
                Draft a story chapter
              </Button>
              <Button
                variant="outlined"
                startIcon={<AutoAwesomeIcon />}
                disabled={busy}
                onClick={() => start("glyph")}
              >
                Design a mark
              </Button>
            </Stack>
          </Stack>
        </Paper>
      )}

      {job && !ACTIVE.has(job.status) && (
        <Paper variant="outlined" sx={{ p: 2.5 }}>
          <AiReviewPanel job={job} onJob={setJob} onApplied={jobDone} />
        </Paper>
      )}

      {jobs !== null && jobs.length > 0 && (
        <Stack spacing={1}>
          <Typography variant="subtitle2" color="text.secondary">
            Recent runs
          </Typography>
          {jobs.slice(0, 8).map((j) => (
            <Stack key={j.id} direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
              <Chip size="small" variant="outlined" label={KIND_LABELS[j.kind] ?? j.kind} />
              <Chip size="small" label={j.status.replace(/_/g, " ")} color={STATUS_COLORS[j.status]} />
              <Typography variant="caption" color="text.secondary">
                {new Date(j.created_at).toLocaleString()}
              </Typography>
            </Stack>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
