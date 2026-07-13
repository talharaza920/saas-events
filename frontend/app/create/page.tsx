"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import NextLink from "next/link";
import { useRouter } from "next/navigation";

import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Container from "@mui/material/Container";
import InputAdornment from "@mui/material/InputAdornment";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { AdminAuthError } from "@/lib/adminApi";
import { meApi } from "@/lib/meApi";
import SignInCard from "@/components/admin/SignInCard";

/** Mirror of the backend's suggest_slug ('Alex & Sam' → 'alex-and-sam'). */
function suggestSlug(coupleNames: string): string {
  return coupleNames
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 63);
}

/**
 * Create a wedding (SAAS_PLAN 2.1 + AI_WIZARD_PLAN 8.5a): names and a web
 * address, nothing more — the wedding exists immediately, and everything else
 * (details, story, guests) is filled in by the setup flow this hands off to, or
 * later from the dashboard tabs. Asking for the whole world here was the old
 * wizard's mistake: it made a form out of what should be a conversation.
 */
export default function CreateWeddingPage() {
  const router = useRouter();
  const [coupleNames, setCoupleNames] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [slugState, setSlugState] = useState<{ ok: boolean; msg: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [needsAuth, setNeedsAuth] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const checkTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const effectiveSlug = slugTouched ? slug : suggestSlug(coupleNames);

  // Debounced live availability check. All setState happens inside the timer
  // callback (never synchronously in the effect body).
  const checkSlug = useCallback((value: string) => {
    if (checkTimer.current) clearTimeout(checkTimer.current);
    checkTimer.current = setTimeout(async () => {
      if (!value) {
        setSlugState(null);
        return;
      }
      try {
        const res = await meApi.slugCheck(value);
        setSlugState(
          res.available
            ? { ok: true, msg: "Available" }
            : { ok: false, msg: res.reason + (res.suggestion ? ` — try "${res.suggestion}"` : "") },
        );
      } catch (e) {
        if (e instanceof AdminAuthError) setNeedsAuth(true);
        else setSlugState(null); // network hiccup: the backend still validates on submit
      }
    }, 350);
  }, []);

  useEffect(() => {
    checkSlug(effectiveSlug);
  }, [effectiveSlug, checkSlug]);

  if (needsAuth) {
    return <SignInCard title="Create a wedding" subtitle="Sign in first — it takes a minute." />;
  }

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await meApi.createWedding({
        couple_names: coupleNames.trim(),
        slug: effectiveSlug,
      });
      router.push(`/${created.slug}/setup`);
    } catch (e) {
      if (e instanceof AdminAuthError) setNeedsAuth(true);
      else setError(e instanceof Error ? e.message : "Could not create the wedding.");
      setBusy(false);
    }
  };

  const canSubmit =
    coupleNames.trim().length >= 3 && effectiveSlug.length >= 3 && slugState?.ok !== false && !busy;

  return (
    <Container maxWidth="sm" sx={{ py: 6 }}>
      <Button component={NextLink} href="/dashboard" startIcon={<ArrowBackIcon />} sx={{ mb: 2 }}>
        My weddings
      </Button>
      <Paper sx={{ p: 4 }}>
        <Typography variant="h5" gutterBottom>
          Create your wedding
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 3 }}>
          Just the names for now. We&apos;ll help you fill in the rest next — and every word, image
          and colour stays editable afterwards.
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        <Stack spacing={3}>
          <TextField
            label="Couple names"
            placeholder="Alex & Sam"
            value={coupleNames}
            onChange={(e) => setCoupleNames(e.target.value)}
            fullWidth
            autoFocus
          />
          <TextField
            label="Web address"
            value={effectiveSlug}
            onChange={(e) => {
              setSlugTouched(true);
              setSlug(suggestSlug(e.target.value) || e.target.value.toLowerCase());
            }}
            fullWidth
            slotProps={{
              input: {
                startAdornment: <InputAdornment position="start">/</InputAdornment>,
              },
            }}
            helperText={
              slugState
                ? slugState.msg
                : "Lowercase letters, numbers and hyphens — this becomes your links"
            }
            error={slugState?.ok === false}
            color={slugState?.ok ? "success" : undefined}
          />

          <Box>
            <Button variant="contained" size="large" disabled={!canSubmit} onClick={submit}>
              {busy ? <CircularProgress size={22} /> : "Create wedding"}
            </Button>
          </Box>
        </Stack>
      </Paper>
    </Container>
  );
}
