"use client";

import DeleteIcon from "@mui/icons-material/DeleteOutline";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useState } from "react";

import { adminApi, type WishAdmin } from "@/lib/adminApi";

/**
 * Guestbook moderation. New wishes arrive HIDDEN (pending) — nothing shows on the
 * public wall until you approve it here. "Approve"/"Hide" flips `approved`
 * (toggling whether it's on the wall, without deleting); Delete removes it for good.
 */
export default function WishesPanel({
  wishes,
  onChanged,
}: {
  wishes: WishAdmin[];
  onChanged: () => Promise<void>;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const pending = wishes.filter((w) => !w.approved).length;

  async function run(id: string, action: () => Promise<unknown>) {
    setBusy(id);
    try {
      await action();
      await onChanged();
    } finally {
      setBusy(null);
    }
  }

  if (wishes.length === 0) {
    return <Typography color="text.secondary">No guestbook messages yet.</Typography>;
  }

  return (
    <Stack spacing={1.5}>
      <Alert severity={pending > 0 ? "warning" : "info"}>
        {pending > 0
          ? `${pending} wish${pending === 1 ? "" : "es"} waiting for your approval — only approved wishes show on the public wall.`
          : "New wishes arrive hidden — approve one here and it appears on the public wall."}
      </Alert>
      {wishes.map((w) => (
        <Paper
          key={w.id}
          variant="outlined"
          sx={{ p: 2, opacity: w.approved ? 1 : 0.75 }}
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
            <Typography sx={{ fontWeight: 600, flexGrow: 1 }}>{w.name}</Typography>
            {w.approved ? (
              <Chip size="small" color="success" label="On the wall" />
            ) : (
              <Chip size="small" color="warning" label="Pending" />
            )}
            {w.guest_name && w.guest_name !== w.name && (
              <Chip size="small" variant="outlined" label={`via ${w.guest_name}`} />
            )}
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "pre-wrap", mb: 1 }}>
            {w.message}
          </Typography>
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              variant={w.approved ? "text" : "contained"}
              startIcon={w.approved ? <VisibilityOffIcon /> : <VisibilityIcon />}
              disabled={busy === w.id}
              onClick={() => run(w.id, () => adminApi.moderateWish(w.id, !w.approved))}
            >
              {w.approved ? "Hide" : "Approve"}
            </Button>
            <Button
              size="small"
              color="error"
              startIcon={<DeleteIcon />}
              disabled={busy === w.id}
              onClick={() => {
                if (window.confirm("Delete this message permanently?")) {
                  run(w.id, () => adminApi.deleteWish(w.id));
                }
              }}
            >
              Delete
            </Button>
          </Stack>
        </Paper>
      ))}
    </Stack>
  );
}
