"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useState } from "react";

import RichText from "@/components/invite/RichText";
import Section from "@/components/invite/Section";
import type { WishesContent } from "@/lib/content";
import { type WishPublic, fetchWishes, submitWish } from "@/lib/wishes";

export type WishesProps = {
  guestSlug: string;
  defaultName: string;
  initialWishes: WishPublic[];
  /** Owner-editable section copy (content.wishes); falls back to defaults. */
  copy: WishesContent;
};

/**
 * The guestbook wall. Every guest of the wedding sees the same approved messages
 * and can leave one (name pre-filled from their invite, editable). New messages
 * are held for the couple to approve, so a just-sent wish does NOT appear on the
 * wall yet — the success note says as much (copy.success). The couple approve
 * each one from /admin before it shows.
 */
export default function Wishes(props: WishesProps) {
  return (
    <Section
      id="wishes"
      kicker={props.copy.kicker}
      heading={props.copy.heading || "Leave us a wish"}
      maxWidth="sm"
    >
      <WishesBody {...props} />
    </Section>
  );
}

/**
 * The wish form + (optionally) the approved-wishes wall, without the surrounding
 * <Section> chrome — so it can be reused inside other surfaces (e.g. the RSVP
 * confirmation screen) as well as the standalone #wishes section. Manages its own
 * submit state, so two instances on a page stay independent.
 */
export function WishesBody({
  guestSlug,
  defaultName,
  initialWishes,
  copy,
  showWall = true,
}: WishesProps & {
  /** Show the wall of approved wishes beneath the form (off when a fuller wall is nearby). */
  showWall?: boolean;
}) {
  const [wishes, setWishes] = useState<WishPublic[]>(initialWishes);
  const [name, setName] = useState(defaultName);
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justSent, setJustSent] = useState(false);

  async function handleSubmit() {
    if (!name.trim() || !message.trim()) {
      setError("Please add your name and a message.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await submitWish(guestSlug, { name: name.trim(), message: message.trim() });
      setMessage("");
      setJustSent(true);
      setWishes(await fetchWishes(guestSlug));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
      <Stack spacing={3}>
      {copy.intro && (
        <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
          <RichText text={copy.intro} />
        </Typography>
      )}

      <Stack spacing={2}>
        <TextField
          label={copy.name_label || "Your name"}
          value={name}
          onChange={(e) => setName(e.target.value)}
          fullWidth
        />
        <TextField
          label={copy.message_label || "Your message"}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          fullWidth
          multiline
          minRows={2}
          slotProps={{ htmlInput: { maxLength: 1000 } }}
        />
        {error && <Alert severity="error">{error}</Alert>}
        {justSent && !error && (
          <Alert severity="success" onClose={() => setJustSent(false)}>
            {copy.success || "Thank you! Your wish has been sent for the couple to approve."}
          </Alert>
        )}
        <Button
          variant="contained"
          color="primary"
          onClick={handleSubmit}
          disabled={submitting}
          sx={{ alignSelf: "center", px: 5 }}
        >
          {submitting ? "Sending…" : copy.button || "Add my wish"}
        </Button>
      </Stack>

      {showWall && wishes.length > 0 && (
        <Stack spacing={2} sx={{ pt: 2 }}>
          {wishes.map((w, i) => (
            <Paper
              key={i}
              elevation={0}
              sx={{
                p: 2.5,
                bgcolor: "background.paper",
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 2,
              }}
            >
              <Typography variant="body1" color="text.primary" sx={{ lineHeight: 1.8 }}>
                {w.message}
              </Typography>
              <Box sx={{ mt: 1 }}>
                <Typography variant="subtitle2" color="primary.main">
                  — {w.name}
                </Typography>
              </Box>
            </Paper>
          ))}
        </Stack>
      )}
      </Stack>
  );
}
