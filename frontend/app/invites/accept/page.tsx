"use client";

import { Suspense, useEffect, useState } from "react";
import NextLink from "next/link";
import { useSearchParams } from "next/navigation";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Container from "@mui/material/Container";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";

import { AdminAuthError } from "@/lib/adminApi";
import { meApi, type InviteAccepted } from "@/lib/meApi";
import SignInCard from "@/components/admin/SignInCard";

/**
 * Co-admin invite acceptance (Phase 3). The emailed link lands here with the
 * single-use token; the visitor must be signed in with the INVITED email —
 * anything else gets the same "invalid or expired" message as a bad token.
 */
function AcceptInner() {
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<
    | { phase: "working" }
    | { phase: "needs-auth"; message?: string }
    | { phase: "done"; result: InviteAccepted }
    | { phase: "error"; message: string }
  >({ phase: "working" });

  useEffect(() => {
    if (!token) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setState({ phase: "error", message: "This link is missing its invite token." });
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const result = await meApi.acceptInvite(token);
        if (!cancelled) setState({ phase: "done", result });
      } catch (e) {
        if (cancelled) return;
        if (e instanceof AdminAuthError) setState({ phase: "needs-auth", message: e.message });
        else
          setState({
            phase: "error",
            message: e instanceof Error ? e.message : "This invite link is invalid or has expired.",
          });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (state.phase === "working") {
    return (
      <Box sx={{ display: "grid", placeItems: "center", minHeight: "60vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (state.phase === "needs-auth") {
    return (
      <SignInCard
        title="Accept your invite"
        subtitle="Sign in with the email address the invite was sent to, then reload this page."
        error={state.message}
      />
    );
  }

  return (
    <Container maxWidth="sm" sx={{ py: 8 }}>
      <Paper sx={{ p: 4 }}>
        {state.phase === "done" ? (
          <>
            <Typography variant="h5" gutterBottom>
              You&apos;re in 🎉
            </Typography>
            <Typography color="text.secondary" gutterBottom>
              You&apos;re now {state.result.role === "owner" ? "an owner" : "an admin"} of{" "}
              <strong>{state.result.couple_names}</strong>.
            </Typography>
            <Button
              component={NextLink}
              href={`/${state.result.wedding_slug}/admin`}
              variant="contained"
              sx={{ mt: 2 }}
            >
              Open the dashboard
            </Button>
          </>
        ) : (
          <>
            <Typography variant="h5" gutterBottom>
              Invite not accepted
            </Typography>
            <Alert severity="error" sx={{ my: 2 }}>
              {state.message}
            </Alert>
            <Typography color="text.secondary">
              Make sure you&apos;re signed in with the email address the invite was sent to, and
              that the link hasn&apos;t expired (invites last 7 days). Ask the wedding&apos;s owner
              to send a fresh one if needed.
            </Typography>
            <Button component={NextLink} href="/dashboard" sx={{ mt: 2 }}>
              Go to my weddings
            </Button>
          </>
        )}
      </Paper>
    </Container>
  );
}

export default function AcceptInvitePage() {
  return (
    <Suspense
      fallback={
        <Box sx={{ display: "grid", placeItems: "center", minHeight: "60vh" }}>
          <CircularProgress />
        </Box>
      }
    >
      <AcceptInner />
    </Suspense>
  );
}
