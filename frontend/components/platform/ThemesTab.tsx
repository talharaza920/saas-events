"use client";

import { useCallback, useEffect, useState } from "react";

import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { platformApi, type ThemePreset } from "@/lib/platformApi";

/**
 * The theme catalogue (AI_WIZARD_PLAN 8.5e) — the ~10 looks a couple can start
 * from, as data rather than code, so curating them never needs a deploy.
 *
 * The whole list saves at once: that is what makes reorder, disable and delete
 * one audited action instead of four endpoints. Weddings that already applied a
 * preset are NOT affected by anything here — apply copies the tokens onto the
 * wedding, so an edit has nothing to reach into. The server validates every
 * preset (hex colours, only fonts the app actually loads) and refuses the save
 * with a reason; nothing half-valid is ever stored.
 */
type Draft = ThemePreset & { tokensText: string; tokensError: string | null };

const BLANK_TOKENS = `{
  "colors": {
    "primary": "#D98C6A",
    "paper": "#F3EEE3",
    "ink": "#1A1714"
  }
}`;

function toDraft(preset: ThemePreset): Draft {
  return {
    ...preset,
    tokensText: JSON.stringify(preset.tokens, null, 2),
    tokensError: null,
  };
}

/** The colours the couple's picker will show if the preset names no swatches. */
const SWATCH_ORDER = ["primary", "secondary", "accentSage", "accentLav", "paper", "ink"] as const;

function swatchesOf(draft: Draft): string[] {
  if (draft.swatches.length) return draft.swatches;
  const colors = (draft.tokens.colors ?? {}) as Record<string, string>;
  return SWATCH_ORDER.filter((k) => colors[k]).map((k) => colors[k]).slice(0, 6);
}

export default function ThemesTab() {
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const { presets } = await platformApi.themePresets();
      setDrafts(presets.map(toDraft));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the themes.");
      setDrafts([]);
    }
  }, []);

  useEffect(() => {
    // Fetch-on-mount: setState happens after load()'s first await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  function patch(index: number, changes: Partial<Draft>) {
    setSaved(false);
    setDrafts((current) =>
      (current ?? []).map((d, i) => (i === index ? { ...d, ...changes } : d)),
    );
  }

  /** The tokens box is free JSON — parse as they type so a typo is visible here
   * rather than as a 422 on save, and so the swatch preview keeps up. */
  function editTokens(index: number, text: string) {
    let tokens = drafts?.[index].tokens ?? {};
    let tokensError: string | null = null;
    try {
      const parsed = JSON.parse(text);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("tokens must be an object");
      }
      tokens = parsed;
    } catch (e) {
      tokensError = e instanceof Error ? e.message : "invalid JSON";
    }
    patch(index, { tokensText: text, tokens, tokensError });
  }

  function move(index: number, by: number) {
    setSaved(false);
    setDrafts((current) => {
      const next = [...(current ?? [])];
      const target = index + by;
      if (target < 0 || target >= next.length) return next;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function add() {
    setSaved(false);
    setDrafts((current) => [
      ...(current ?? []),
      toDraft({
        id: "",
        name: "",
        description: "",
        swatches: [],
        enabled: true,
        tokens: JSON.parse(BLANK_TOKENS),
      }),
    ]);
  }

  async function save() {
    if (!drafts) return;
    const broken = drafts.find((d) => d.tokensError);
    if (broken) {
      setError(`“${broken.name || broken.id || "new preset"}”: ${broken.tokensError}`);
      return;
    }
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const { presets } = await platformApi.putThemePresets(
        drafts.map(({ id, name, description, swatches, enabled, tokens }) => ({
          id,
          name,
          description,
          swatches,
          enabled,
          tokens,
        })),
      );
      setDrafts(presets.map(toDraft));
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the themes.");
    } finally {
      setBusy(false);
    }
  }

  if (drafts === null) return <CircularProgress />;

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: 2 }}>
        <Typography variant="h6">Theme catalogue</Typography>
        <Typography variant="body2" color="text.secondary">
          The looks couples can start from, in this order. Disabled themes stay
          here but aren&apos;t offered. Applying a theme copies it onto a wedding —
          editing or deleting one here never changes a wedding that already took it.
        </Typography>
      </Paper>

      {drafts.map((draft, i) => (
        <Accordion key={`${draft.id}-${i}`} disableGutters>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ width: "100%", pr: 1 }}>
              <Stack direction="row" spacing={0.5}>
                {swatchesOf(draft).map((hex, s) => (
                  <Box
                    key={s}
                    sx={{
                      width: 18,
                      height: 18,
                      borderRadius: "50%",
                      bgcolor: hex,
                      border: "1px solid",
                      borderColor: "divider",
                    }}
                  />
                ))}
              </Stack>
              <Typography sx={{ fontWeight: 600 }}>{draft.name || "(unnamed)"}</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
                {draft.id}
              </Typography>
              {!draft.enabled && <Chip size="small" label="disabled" />}
              {draft.tokensError && <Chip size="small" color="error" label="bad JSON" />}
            </Stack>
          </AccordionSummary>
          <AccordionDetails>
            <Stack spacing={2}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField
                  label="Name"
                  value={draft.name}
                  onChange={(e) => patch(i, { name: e.target.value })}
                  size="small"
                  sx={{ flex: 1 }}
                />
                <TextField
                  label="Id (slug)"
                  value={draft.id}
                  onChange={(e) => patch(i, { id: e.target.value })}
                  size="small"
                  helperText="Stable — a wedding's copy doesn't depend on it"
                  sx={{ flex: 1 }}
                />
              </Stack>
              <TextField
                label="Description"
                value={draft.description}
                onChange={(e) => patch(i, { description: e.target.value })}
                size="small"
                fullWidth
              />
              <TextField
                label="Preview swatches (hex, comma-separated — blank = from the colours)"
                value={draft.swatches.join(", ")}
                onChange={(e) =>
                  patch(i, {
                    swatches: e.target.value
                      .split(",")
                      .map((v) => v.trim())
                      .filter(Boolean),
                  })
                }
                size="small"
                fullWidth
              />
              <TextField
                label="theme_tokens patch"
                value={draft.tokensText}
                onChange={(e) => editTokens(i, e.target.value)}
                error={Boolean(draft.tokensError)}
                helperText={
                  draft.tokensError ??
                  "Colours (hex), fonts the app loads, radius / radiusLg / spacingUnit / storyFeather"
                }
                multiline
                minRows={6}
                fullWidth
                slotProps={{ input: { sx: { fontFamily: "monospace", fontSize: 13 } } }}
              />
              <Stack direction="row" spacing={1} alignItems="center">
                <Switch
                  checked={draft.enabled}
                  onChange={(e) => patch(i, { enabled: e.target.checked })}
                />
                <Typography variant="body2">
                  {draft.enabled ? "Offered to couples" : "Hidden from couples"}
                </Typography>
                <Box sx={{ flex: 1 }} />
                <IconButton onClick={() => move(i, -1)} disabled={i === 0} aria-label="Move up">
                  <ArrowUpwardIcon fontSize="small" />
                </IconButton>
                <IconButton
                  onClick={() => move(i, 1)}
                  disabled={i === drafts.length - 1}
                  aria-label="Move down"
                >
                  <ArrowDownwardIcon fontSize="small" />
                </IconButton>
                <IconButton
                  color="error"
                  aria-label="Delete"
                  onClick={() => {
                    setSaved(false);
                    setDrafts((c) => (c ?? []).filter((_, j) => j !== i));
                  }}
                >
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </Stack>
            </Stack>
          </AccordionDetails>
        </Accordion>
      ))}

      {error && <Alert severity="error">{error}</Alert>}
      {saved && <Alert severity="success">Theme catalogue saved.</Alert>}

      <Stack direction="row" spacing={2}>
        <Button variant="contained" onClick={save} disabled={busy} data-testid="save-themes">
          {busy ? "Saving…" : "Save catalogue"}
        </Button>
        <Button onClick={add} disabled={busy}>
          Add a theme
        </Button>
        <Button onClick={() => void load()} disabled={busy}>
          Discard changes
        </Button>
      </Stack>
    </Stack>
  );
}
