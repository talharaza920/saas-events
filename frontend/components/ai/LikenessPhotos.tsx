"use client";

import { useState } from "react";

import AddPhotoAlternateIcon from "@mui/icons-material/AddPhotoAlternate";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { aiApi, type AiJobAdmin } from "@/lib/adminApi";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = "image/png,image/jpeg,image/webp";

/**
 * "Put us in the pictures" (AI_WIZARD_PLAN 8.5d).
 *
 * The consent box is not decoration and it is not a dark pattern in reverse:
 * the upload button is disabled until it is ticked, because the server will
 * refuse the file anyway and a rejected upload is a worse way to learn the
 * rule. What the couple agree to is stated in full, here, in the sentence next
 * to the box — not behind a link.
 *
 * Photos live only as long as the run does (they're deleted when it's applied
 * or cancelled), the illustrations stay stylised, and both facts are said out
 * loud rather than being true-but-unmentioned.
 */
export default function LikenessPhotos({
  job,
  onJob,
  disabled,
  max,
}: {
  job: AiJobAdmin;
  onJob: (j: AiJobAdmin) => void;
  disabled?: boolean;
  /** Plan cap on reference photos (server: ai_max_likeness_references). */
  max: number;
}) {
  const proposal = (job.proposal ?? {}) as Record<string, unknown>;
  const likeness = (proposal.likeness ?? {}) as { references?: number };
  const attached = likeness.references ?? 0;

  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const add = async (picked: FileList | null) => {
    if (!picked?.length) return;
    // The consent this sends must be consent that was actually GIVEN. A
    // disabled MUI Button rendered as a <label> only stops pointer events —
    // the input inside it still accepts a programmatic file — so the assertion
    // is gated here as well as in the DOM. Never claim consent nobody ticked.
    if (!consent) {
      setError("Tick the box first — we can't use photos of you without your say-so.");
      return;
    }
    const files = Array.from(picked).slice(0, Math.max(max - attached, 0));
    setBusy(true);
    setError(null);
    try {
      const ids: string[] = [];
      for (const f of files) {
        if (f.size > MAX_BYTES) throw new Error(`"${f.name}" is over 10 MB.`);
        // Consent rides the upload itself — the server records who and when.
        ids.push((await aiApi.uploadInput(f, { role: "reference", consent: true })).id);
      }
      onJob(await aiApi.setReferences(job.id, ids));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add those photos.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      onJob(await aiApi.setReferences(job.id, []));
      setConsent(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove those photos.");
    } finally {
      setBusy(false);
    }
  };

  const locked = disabled || busy;

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={1.25}>
        <Typography variant="subtitle2">Put the two of you in the pictures</Typography>
        <Typography variant="body2" color="text.secondary">
          Optional. Add a photo or two of you both and the illustrations will be drawn to look
          like you — still illustrations, never photographs of you.
        </Typography>

        {error && (
          <Alert severity="error" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {attached > 0 ? (
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
            <Chip
              size="small"
              color="primary"
              label={`${attached} photo${attached === 1 ? "" : "s"} of you attached`}
            />
            <Button size="small" color="inherit" disabled={locked} onClick={remove}>
              Remove them
            </Button>
            <Typography variant="caption" color="text.secondary">
              The photographic style is unavailable while these are attached.
            </Typography>
          </Stack>
        ) : (
          <>
            <FormControlLabel
              control={
                <Checkbox
                  size="small"
                  checked={consent}
                  disabled={locked}
                  onChange={(e) => setConsent(e.target.checked)}
                />
              }
              label={
                <Typography variant="body2">
                  These are photos of us, and we agree that they can be stored and processed to
                  create stylised illustrations of us for this story. They&apos;re deleted when
                  this run is applied or cancelled.
                </Typography>
              }
              sx={{ alignItems: "flex-start", m: 0, "& .MuiCheckbox-root": { pt: 0 } }}
            />
            <Box>
              <Button
                component="label"
                size="small"
                variant="outlined"
                disabled={locked || !consent}
                startIcon={
                  busy ? <CircularProgress size={14} /> : <AddPhotoAlternateIcon />
                }
              >
                Add photos of us (up to {max})
                <input
                  hidden
                  multiple
                  type="file"
                  accept={ACCEPT}
                  disabled={locked || !consent}
                  onChange={(e) => {
                    add(e.target.files);
                    e.target.value = "";
                  }}
                />
              </Button>
            </Box>
          </>
        )}

        <Typography variant="caption" color="text.secondary">
          Generated images carry Google&apos;s invisible SynthID watermark.
        </Typography>
      </Stack>
    </Paper>
  );
}
