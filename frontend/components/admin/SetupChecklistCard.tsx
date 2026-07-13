"use client";

import { useState } from "react";
import NextLink from "next/link";

import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { adminApi, type AdminMe } from "@/lib/adminApi";

/**
 * The first-time setup checklist (AI_WIZARD_PLAN 8.5a). What's DONE is derived
 * from the wedding itself — no per-step state to drift out of sync with reality
 * — so the only thing stored is the owner's dismissal. It re-enters the same
 * /setup flow, which is itself just the Details/Story/Guests entry points.
 */
export default function SetupChecklistCard({
  me,
  hasDetails,
  hasStory,
  hasGuests,
  onDismissed,
}: {
  me: AdminMe;
  hasDetails: boolean;
  hasStory: boolean;
  hasGuests: boolean;
  onDismissed: () => Promise<void> | void;
}) {
  const [busy, setBusy] = useState(false);

  const items = [
    { label: "Key details — venue, date, time", done: hasDetails },
    { label: "Your story", done: hasStory },
    { label: "Guest list", done: hasGuests },
  ];
  const remaining = items.filter((i) => !i.done).length;

  // Nothing left to nag about, or the owner said they're done being nagged.
  if (me.setup_dismissed || remaining === 0) return null;

  const dismiss = async () => {
    setBusy(true);
    try {
      await adminApi.updateWeddingSettings({ setup_dismissed: true });
      await onDismissed();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Paper variant="outlined" sx={{ p: 2.5, mb: 2 }}>
      <Stack spacing={1.5}>
        <Typography variant="subtitle1">Finish setting up your wedding</Typography>
        <Stack spacing={0.5}>
          {items.map((item) => (
            <Stack key={item.label} direction="row" spacing={1} sx={{ alignItems: "center" }}>
              {item.done ? (
                <CheckCircleIcon fontSize="small" color="success" />
              ) : (
                <RadioButtonUncheckedIcon fontSize="small" color="disabled" />
              )}
              <Typography
                variant="body2"
                color={item.done ? "text.secondary" : "text.primary"}
                sx={{ textDecoration: item.done ? "line-through" : "none" }}
              >
                {item.label}
              </Typography>
            </Stack>
          ))}
        </Stack>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
          <Button
            variant="contained"
            size="small"
            component={NextLink}
            href={`/${me.wedding_slug}/setup`}
          >
            {remaining === 3 ? "Start setup" : "Pick up where you left off"}
          </Button>
          {/* Owner-only: the settings PATCH behind it is owner-scoped. */}
          {(me.role === "owner" || me.role === "platform") && (
            <Button size="small" color="inherit" onClick={dismiss} disabled={busy}>
              Dismiss
            </Button>
          )}
          <Box sx={{ flexGrow: 1 }} />
          <Typography variant="caption" color="text.secondary">
            Every step is optional and editable later.
          </Typography>
        </Stack>
      </Stack>
    </Paper>
  );
}
