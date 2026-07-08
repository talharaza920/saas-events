"use client";

import { useState } from "react";

import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { adminApi, type ContentUpdate } from "@/lib/adminApi";

// ---------------------------------------------------------------------------
// Small loose-object helpers (content/event_details arrive as freeform JSON).
// Shared by DetailsPanel and RsvpPanel.
// ---------------------------------------------------------------------------
export function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}
export function s(v: unknown): string {
  return typeof v === "string" ? v : "";
}
export function strList(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}

/** A collapsible content section with its own "Save section" button that PATCHes
 * just the slice of content `build()` returns. Used across the Details & RSVP tabs. */
export function SectionCard({
  title,
  subtitle,
  defaultExpanded,
  build,
  onChanged,
  children,
}: {
  title: string;
  subtitle?: string;
  defaultExpanded?: boolean;
  build: () => ContentUpdate;
  onChanged: () => void | Promise<void>;
  children: React.ReactNode;
}) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      await adminApi.updateContent(build());
      setSaved(true);
      await onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Accordion defaultExpanded={defaultExpanded} disableGutters>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Box>
          <Typography sx={{ fontWeight: 700 }}>{title}</Typography>
          {subtitle && (
            <Typography variant="caption" color="text.secondary">
              {subtitle}
            </Typography>
          )}
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2}>
          {children}
          {error && <Alert severity="error">{error}</Alert>}
          {saved && <Alert severity="success">Saved.</Alert>}
          <Box>
            <Button variant="contained" onClick={handleSave} disabled={saving}>
              {saving ? "Saving…" : "Save section"}
            </Button>
          </Box>
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}
