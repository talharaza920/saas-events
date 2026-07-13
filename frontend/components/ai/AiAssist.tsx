"use client";

import { useCallback, useEffect, useState } from "react";

import AttachFileIcon from "@mui/icons-material/AttachFile";
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
  type AiJobAdmin,
  type AiJobKind,
  type AiStyleOption,
} from "@/lib/adminApi";
import AiReviewPanel from "@/components/ai/AiReviewPanel";
import AiRunProgress from "@/components/ai/AiRunProgress";

const ACTIVE = new Set(["queued", "running", "awaiting_review"]);

// Mirrors backend storage.ALLOWED_AI_MEDIA_TYPES / MAX_AI_MEDIA_BYTES.
const MEDIA_ACCEPT = "audio/*,image/png,image/jpeg,image/webp,application/pdf";
const MAX_MEDIA_BYTES = 10 * 1024 * 1024;

const KIND_LABELS: Record<string, string> = {
  details: "Key details",
  story_arc: "Story chapter",
  glyph: "Mark",
  guests: "Guest list",
};

/**
 * One AI entry point, embedded wherever the thing it produces already lives
 * (AI_WIZARD_PLAN 8.5a): the Details tab starts a `details` run, the Story tab a
 * `story_arc` run, the Guests tab a `guests` run — and the first-time setup flow
 * reuses the same three. Submit → watch → review → apply, all in place; nothing
 * reaches the wedding until Apply, which writes only the server's allowlist.
 *
 * One run per wedding is a DB-level invariant, so an active run of ANOTHER kind
 * is surfaced here rather than papered over with a 409 the couple can't act on.
 */
export default function AiAssist({
  me,
  kind,
  blurb,
  placeholder,
  cta,
  requiresInput = true,
  onApplied,
}: {
  me: AdminMe;
  kind: AiJobKind;
  /** What this run does, in the couple's language. */
  blurb: string;
  placeholder: string;
  cta: string;
  /** False for `glyph`, which can draft from nothing at all. */
  requiresInput?: boolean;
  /** Fired after a successful apply so the surrounding tab can refresh. */
  onApplied?: () => Promise<void> | void;
}) {
  const enabled = me.entitlements?.ai_enabled === true;
  const [job, setJob] = useState<AiJobAdmin | null>(null);
  const [otherKind, setOtherKind] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [styles, setStyles] = useState<AiStyleOption[]>([]);
  const [style, setStyle] = useState("storybook");

  const load = useCallback(async () => {
    try {
      const active = (await aiApi.listJobs()).find((j) => ACTIVE.has(j.status));
      if (!active) {
        setJob(null);
        setOtherKind(null);
      } else if (active.kind === kind) {
        // The list omits variants — the review panel needs the full job.
        setJob(await aiApi.getJob(active.id));
        setOtherKind(null);
      } else {
        setJob(null);
        setOtherKind(active.kind);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load AI runs.");
    }
  }, [kind]);

  useEffect(() => {
    if (!enabled) return;
    // Fetch-on-mount: setState only happens after load()'s first await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    if (kind === "story_arc") aiApi.styles().then(setStyles).catch(() => setStyles([]));
  }, [enabled, kind, load]);

  if (!enabled) return null; // no AI on this plan — the tab's own tools still work

  const addFiles = (picked: FileList | null) => {
    if (!picked) return;
    const next = [...files];
    for (const f of Array.from(picked)) {
      if (f.size > MAX_MEDIA_BYTES) {
        setError(`"${f.name}" is over 10 MB — trim it down and try again.`);
        continue;
      }
      next.push(f);
    }
    setFiles(next.slice(0, 12));
  };

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const inputIds: string[] = [];
      const t = text.trim();
      if (t) inputIds.push((await aiApi.createInput(t)).id);
      for (const f of files) inputIds.push((await aiApi.uploadInput(f)).id);
      // The style only ever reaches an image prompt — it's picked here because
      // it's the couple's first question ("what will it look like?"), but the
      // story run itself is text, and they can change it again at review.
      const options = kind === "story_arc" && style ? { style_preset: style } : {};
      const created = await aiApi.createJob(kind, inputIds, options, crypto.randomUUID());
      setText("");
      setFiles([]);
      setJob(created);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the run.");
    } finally {
      setBusy(false);
    }
  };

  // After an apply: refresh the surrounding tab, but do NOT re-derive `job`
  // from the server — `applied` is terminal, so a reload would drop the run out
  // of the active list and unmount the review panel's success state (and the
  // glyph's "use as cover icon" switch) the instant the couple applied it.
  // They dismiss it themselves with "Start another".
  const applied = async () => {
    await onApplied?.();
  };

  if (otherKind) {
    return (
      <Alert severity="info" icon={<AutoAwesomeIcon fontSize="inherit" />}>
        An AI run is already going for this wedding ({KIND_LABELS[otherKind] ?? otherKind}) — finish
        or cancel it on the AI tab, then come back.
      </Alert>
    );
  }

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Stack spacing={2}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <AutoAwesomeIcon fontSize="small" color="primary" />
          <Typography variant="subtitle1" sx={{ flexGrow: 1 }}>
            {KIND_LABELS[kind]} with AI
          </Typography>
        </Stack>

        {error && (
          <Alert severity="error" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {job ? (
          <>
            {ACTIVE.has(job.status) && <AiRunProgress job={job} onJob={setJob} />}
            {job.status !== "queued" && job.status !== "running" && (
              <AiReviewPanel job={job} onJob={setJob} onApplied={applied} />
            )}
            {!ACTIVE.has(job.status) && (
              <Stack direction="row">
                <Button size="small" onClick={() => setJob(null)}>
                  Start another
                </Button>
              </Stack>
            )}
          </>
        ) : (
          <>
            <Typography variant="body2" color="text.secondary">
              {blurb}
            </Typography>
            <TextField
              multiline
              minRows={3}
              fullWidth
              label="What should it work from?"
              placeholder={placeholder}
              value={text}
              onChange={(e) => setText(e.target.value.slice(0, 20000))}
            />
            {styles.length > 0 && (
              <Stack spacing={0.75}>
                <Typography variant="caption" color="text.secondary">
                  Illustration style — pick one now or change it later; the story itself is
                  written first, and you decide when to spend credits on pictures.
                </Typography>
                <Stack direction="row" sx={{ flexWrap: "wrap", gap: 1 }}>
                  {styles.map((s) => (
                    <Chip
                      key={s.key}
                      size="small"
                      label={s.label}
                      color={style === s.key ? "primary" : "default"}
                      variant={style === s.key ? "filled" : "outlined"}
                      onClick={() => setStyle(s.key)}
                    />
                  ))}
                </Stack>
              </Stack>
            )}
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
              <Button component="label" size="small" startIcon={<AttachFileIcon />} disabled={busy}>
                Attach files
                <input
                  hidden
                  multiple
                  type="file"
                  accept={MEDIA_ACCEPT}
                  onChange={(e) => {
                    addFiles(e.target.files);
                    e.target.value = "";
                  }}
                />
              </Button>
              {files.map((f, i) => (
                <Chip
                  key={`${f.name}-${i}`}
                  size="small"
                  label={f.name}
                  onDelete={() => setFiles(files.filter((_, j) => j !== i))}
                />
              ))}
            </Stack>
            <Stack direction="row">
              <Button
                variant="contained"
                startIcon={busy ? <CircularProgress size={16} /> : <AutoAwesomeIcon />}
                disabled={busy || (requiresInput && !text.trim() && files.length === 0)}
                onClick={start}
              >
                {cta}
              </Button>
            </Stack>
          </>
        )}
      </Stack>
    </Paper>
  );
}
