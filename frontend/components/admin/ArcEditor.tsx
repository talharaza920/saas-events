"use client";

import { useState } from "react";

import AddIcon from "@mui/icons-material/Add";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import DeleteIcon from "@mui/icons-material/Delete";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { adminApi, type StoryArcAdmin } from "@/lib/adminApi";

import ImageUpload from "./ImageUpload";
import RichTextField from "./RichTextField";

const MAX_BEATS = 10;

/** One editable journey beat. `wide` is preserved but not edited here. */
interface EditBeat {
  image?: string;
  text?: string;
  wide?: boolean;
}
interface EditClimax {
  label?: string;
  image?: string;
  text?: string;
  cta?: string;
}

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : {};
}
function s(v: unknown): string {
  return typeof v === "string" ? v : "";
}

function parseBeats(v: unknown): EditBeat[] {
  return Array.isArray(v)
    ? v.map((x) => {
        const o = rec(x);
        return { image: s(o.image), text: s(o.text), wide: Boolean(o.wide) };
      })
    : [];
}

/**
 * Edit a single story arc: head (title/kicker/heading/intro), 1–10 numbered
 * journey beats (text + uploaded image, reorderable), and an optional unnumbered
 * "you're invited" finale. Saves the assembled content via PATCH /story-arcs/{id}.
 */
export default function ArcEditor({ arc, onSaved }: { arc: StoryArcAdmin; onSaved?: () => void }) {
  const content = rec(arc.content);
  const climax0 = content.climax ? (rec(content.climax) as EditClimax) : null;

  const [title, setTitle] = useState(arc.title);
  const [kicker, setKicker] = useState(s(content.kicker));
  const [heading, setHeading] = useState(s(content.heading));
  const [intro, setIntro] = useState(s(content.intro));
  const [beats, setBeats] = useState<EditBeat[]>(parseBeats(content.beats));
  const [includeFinale, setIncludeFinale] = useState(Boolean(climax0));
  const [climax, setClimax] = useState<EditClimax>(
    climax0 ?? { label: "Chapter Two", text: "", cta: "Will you be there?" },
  );

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const setBeat = (i: number, patch: Partial<EditBeat>) =>
    setBeats((prev) => prev.map((b, j) => (j === i ? { ...b, ...patch } : b)));
  const addBeat = () =>
    setBeats((prev) => (prev.length >= MAX_BEATS ? prev : [...prev, { text: "", image: "" }]));
  const removeBeat = (i: number) => setBeats((prev) => prev.filter((_, j) => j !== i));
  const moveBeat = (i: number, dir: -1 | 1) =>
    setBeats((prev) => {
      const j = i + dir;
      if (j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await adminApi.updateArc(arc.id, {
        title: title.trim() || "Our story",
        content: {
          kicker,
          heading,
          intro,
          beats,
          climax: includeFinale ? climax : null,
        },
      });
      setSaved(true);
      onSaved?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the story.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Stack spacing={3}>
      <Stack spacing={2}>
        <Typography variant="subtitle2" color="text.secondary">
          Story heading
        </Typography>
        <TextField
          label="Arc name (private — only you see this)"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          fullWidth
        />
        <RichTextField label="Kicker (small label above the title)" value={kicker}
          onChange={setKicker} variant="inline" />
        <RichTextField label="Heading" value={heading}
          onChange={setHeading} variant="inline" />
        <RichTextField label="Intro" value={intro} onChange={setIntro} />
      </Stack>

      <Divider />

      <Stack spacing={2}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Typography variant="subtitle2" color="text.secondary">
            Journey ({beats.length}/{MAX_BEATS}) — numbered automatically
          </Typography>
          <Button size="small" startIcon={<AddIcon />} onClick={addBeat}
            disabled={beats.length >= MAX_BEATS}>
            Add step
          </Button>
        </Stack>

        {beats.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            No steps yet — add the first beat of your story.
          </Typography>
        )}

        {beats.map((beat, i) => (
          <Paper key={i} variant="outlined" sx={{ p: 2 }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <Box sx={{ width: { xs: "100%", sm: 200 }, flexShrink: 0 }}>
                <Typography variant="overline" color="primary">
                  {String(i + 1).padStart(2, "0")}
                </Typography>
                <ImageUpload value={beat.image} onChange={(url) => setBeat(i, { image: url })} />
              </Box>
              <RichTextField
                label={`Step ${i + 1} text`}
                value={beat.text ?? ""}
                onChange={(v) => setBeat(i, { text: v })}
              />
              <Stack>
                <Tooltip title="Move up">
                  <span>
                    <IconButton size="small" onClick={() => moveBeat(i, -1)} disabled={i === 0}>
                      <ArrowUpwardIcon fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
                <Tooltip title="Move down">
                  <span>
                    <IconButton size="small" onClick={() => moveBeat(i, 1)}
                      disabled={i === beats.length - 1}>
                      <ArrowDownwardIcon fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
                <Tooltip title="Remove step">
                  <IconButton size="small" color="error" onClick={() => removeBeat(i)}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>
            </Stack>
          </Paper>
        ))}
      </Stack>

      <Divider />

      <Stack spacing={2}>
        <FormControlLabel
          control={<Switch checked={includeFinale}
            onChange={(e) => setIncludeFinale(e.target.checked)} />}
          label="Include the final invite step (unnumbered)"
        />
        {includeFinale && (
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <Box sx={{ width: { xs: "100%", sm: 200 }, flexShrink: 0 }}>
                <ImageUpload value={climax.image}
                  onChange={(url) => setClimax((c) => ({ ...c, image: url }))} />
              </Box>
              <Stack spacing={2} sx={{ flexGrow: 1 }}>
                <TextField label="Label" value={climax.label ?? ""}
                  onChange={(e) => setClimax((c) => ({ ...c, label: e.target.value }))} fullWidth />
                <RichTextField label="Invite text" value={climax.text ?? ""}
                  onChange={(v) => setClimax((c) => ({ ...c, text: v }))} />
                <TextField label="Button text" value={climax.cta ?? ""}
                  onChange={(e) => setClimax((c) => ({ ...c, cta: e.target.value }))} fullWidth />
              </Stack>
            </Stack>
          </Paper>
        )}
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}
      {saved && <Alert severity="success">Story saved.</Alert>}

      <Box>
        <Button variant="contained" onClick={handleSave} disabled={saving}>
          {saving ? "Saving…" : "Save story"}
        </Button>
      </Box>
    </Stack>
  );
}
