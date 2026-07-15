"use client";

import { useState } from "react";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import ThemePresets from "@/components/admin/ThemePresets";
import { adminApi, type ContentAdmin, type ThemePreset } from "@/lib/adminApi";
import { defaultThemeConfig } from "@/theme/defaultThemeConfig";
import type { ThemeColors } from "@/theme/types";

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}
function s(v: unknown): string {
  return typeof v === "string" ? v : "";
}

/** The brand-meaningful colour tokens, in editor order, with friendly labels. */
const EDITABLE_COLORS: { token: keyof ThemeColors; label: string }[] = [
  { token: "primary", label: "Primary — buttons & accents" },
  { token: "primaryDeep", label: "Primary — deep (hover)" },
  { token: "secondary", label: "Secondary" },
  { token: "accentSage", label: "Accent — sage" },
  { token: "accentLav", label: "Accent — lavender" },
  { token: "yes", label: "RSVP — accept" },
  { token: "no", label: "RSVP — decline" },
  { token: "paper", label: "Page background" },
  { token: "ink", label: "Text / ink" },
];

/**
 * Heading/body font choices. Limited to faces already registered via next/font in
 * app/layout.tsx — adding a new family needs a code change there (and is recorded
 * as a follow-up). Values are the full CSS font-family stacks the tokens expect.
 */
const FONT_OPTIONS = [
  { label: "Baloo 2 — rounded & friendly", value: defaultThemeConfig.typography.display },
  { label: "Lora — warm serif", value: defaultThemeConfig.typography.story },
  { label: "Plus Jakarta Sans — clean sans", value: defaultThemeConfig.typography.body },
];

function ColorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Stack direction="row" spacing={1.5} alignItems="center">
      <Box
        component="input"
        type="color"
        value={value}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
        sx={{
          width: 44,
          height: 44,
          p: 0,
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1,
          bgcolor: "transparent",
          cursor: "pointer",
          flexShrink: 0,
        }}
      />
      <TextField
        label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        size="small"
        fullWidth
      />
    </Stack>
  );
}

export default function ThemePanel({
  content,
  onChanged,
}: {
  content: ContentAdmin;
  onChanged: () => void | Promise<void>;
}) {
  const tokens = rec(content.theme_tokens);
  const colors0 = rec(tokens.colors);
  const typo0 = rec(tokens.typography);

  // Each editable colour: stored override, else the template default.
  const [colors, setColors] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      EDITABLE_COLORS.map(({ token }) => [
        token,
        s(colors0[token]) || defaultThemeConfig.colors[token],
      ]),
    ),
  );
  const [heading, setHeading] = useState(s(typo0.display) || defaultThemeConfig.typography.display);
  const [body, setBody] = useState(s(typo0.body) || defaultThemeConfig.typography.body);

  // A preset the couple is trying on: its colours/fonts are already showing in
  // the fields below, but it isn't theirs until they save.
  const [pending, setPending] = useState<ThemePreset | null>(null);
  // "Reset to defaults" pressed: the save must CLEAR the stored theme, not just
  // repaint the nine fields on top of it (see handleSave).
  const [clearing, setClearing] = useState(false);

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Try a preset on: load the tokens this editor exposes into the fields. */
  function previewPreset(preset: ThemePreset) {
    const presetColors = preset.tokens.colors ?? {};
    const presetTypo = preset.tokens.typography ?? {};
    setPending(preset);
    setClearing(false);
    setColors((current) =>
      Object.fromEntries(
        EDITABLE_COLORS.map(({ token }) => [
          token,
          presetColors[token] ?? current[token],
        ]),
      ),
    );
    setHeading(presetTypo.display ?? defaultThemeConfig.typography.display);
    setBody(presetTypo.body ?? defaultThemeConfig.typography.body);
  }

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      // A theme carries tokens this editor doesn't show (the hero wash, the
      // paper tints, the radii), and a content PATCH deep-merges. So set the
      // BASE first — apply the preset whole, or clear back to the template —
      // otherwise the nine fields below would land on top of the previous look
      // and leave a half-and-half theme. Hand edits then go on the new base.
      if (pending) {
        await adminApi.applyThemePreset(pending.id);
        setPending(null);
      } else if (clearing) {
        await adminApi.updateContent({ theme_tokens: null });
      }
      setClearing(false);
      await adminApi.updateContent({
        theme_tokens: {
          colors,
          // The wordmark (logo) follows the heading face for a consistent brand.
          typography: { display: heading, logo: heading, body },
        },
      });
      setSaved(true);
      await onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the theme.");
    } finally {
      setSaving(false);
    }
  }

  function resetDefaults() {
    setPending(null);
    setClearing(true);
    setColors(
      Object.fromEntries(EDITABLE_COLORS.map(({ token }) => [token, defaultThemeConfig.colors[token]])),
    );
    setHeading(defaultThemeConfig.typography.display);
    setBody(defaultThemeConfig.typography.body);
  }

  return (
    <Paper sx={{ p: { xs: 2, sm: 3 } }}>
      <Typography variant="h6" sx={{ mb: 0.5 }}>
        Brand &amp; styling
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Colours and fonts for the invitation. Changes show on the guest invite (the
        admin keeps its own look).
      </Typography>

      <ThemePresets
        selectedId={pending?.id ?? null}
        onSelect={previewPreset}
        disabled={saving}
      />

      <Stack direction={{ xs: "column", md: "row" }} spacing={3}>
        {/* Editor ---------------------------------------------------------- */}
        <Stack spacing={2} sx={{ flex: 1 }}>
          <Typography variant="subtitle2" color="text.secondary">Colours</Typography>
          {EDITABLE_COLORS.map(({ token, label }) => (
            <ColorField
              key={token}
              label={label}
              value={colors[token]}
              onChange={(v) => setColors((c) => ({ ...c, [token]: v }))}
            />
          ))}
          <Divider flexItem />
          <Typography variant="subtitle2" color="text.secondary">Fonts</Typography>
          <TextField select label="Heading font" value={heading}
            onChange={(e) => setHeading(e.target.value)} fullWidth>
            {FONT_OPTIONS.map((f) => (
              <MenuItem key={f.value} value={f.value}>{f.label}</MenuItem>
            ))}
          </TextField>
          <TextField select label="Body font" value={body}
            onChange={(e) => setBody(e.target.value)} fullWidth>
            {FONT_OPTIONS.map((f) => (
              <MenuItem key={f.value} value={f.value}>{f.label}</MenuItem>
            ))}
          </TextField>
        </Stack>

        {/* Live preview ---------------------------------------------------- */}
        <Box sx={{ flex: 1 }}>
          <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
            Preview
          </Typography>
          <Box
            sx={{
              p: 3,
              borderRadius: 2,
              border: "1px solid",
              borderColor: "divider",
              bgcolor: colors.paper,
              color: colors.ink,
              position: "sticky",
              top: 16,
            }}
          >
            <Typography sx={{ fontFamily: heading, fontWeight: 800, fontSize: 28, color: colors.ink }}>
              Ever after
            </Typography>
            <Typography sx={{ fontFamily: body, mt: 1, color: colors.ink, opacity: 0.85 }}>
              A preview of your invitation&apos;s colours and fonts.
            </Typography>
            <Stack direction="row" spacing={1.5} sx={{ mt: 2, flexWrap: "wrap", rowGap: 1.5 }}>
              {EDITABLE_COLORS.map(({ token }) => (
                <Box
                  key={token}
                  sx={{
                    width: 32,
                    height: 32,
                    borderRadius: "50%",
                    bgcolor: colors[token],
                    border: "2px solid",
                    borderColor: colors.ink,
                  }}
                />
              ))}
            </Stack>
            <Stack direction="row" spacing={1.5} sx={{ mt: 2.5 }}>
              <Box component="span" sx={{
                px: 2.5, py: 1, borderRadius: 999, fontFamily: heading, fontWeight: 700,
                bgcolor: colors.primary, color: "#fff", fontSize: 14,
              }}>
                Will you be there?
              </Box>
              <Box component="span" sx={{
                px: 2.5, py: 1, borderRadius: 999, fontFamily: heading, fontWeight: 700,
                bgcolor: colors.yes, color: "#fff", fontSize: 14,
              }}>
                Joyfully accepts
              </Box>
            </Stack>
          </Box>
        </Box>
      </Stack>

      {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      {saved && <Alert severity="success" sx={{ mt: 2 }}>Theme saved.</Alert>}

      <Stack direction="row" spacing={2} sx={{ mt: 3 }}>
        <Button variant="contained" onClick={handleSave} disabled={saving}>
          {saving ? "Saving…" : "Save theme"}
        </Button>
        <Button onClick={resetDefaults} disabled={saving}>
          Reset to defaults
        </Button>
      </Stack>
    </Paper>
  );
}
