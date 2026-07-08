"use client";

import GoogleIcon from "@mui/icons-material/Google";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Container from "@mui/material/Container";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";

import { isDevAuth, isSupabaseConfigured, signInWithGoogle } from "@/lib/adminAuth";

/**
 * The shared sign-in gate for every authenticated page (dashboard, create,
 * wedding admin, platform console). Mirrors the backend's two auth modes: local
 * dev token (no UI needed — just a hint when it's misconfigured) or Supabase
 * Google sign-in.
 */
export default function SignInCard({
  title = "Sign in",
  subtitle = "Sign in to manage your weddings.",
  error,
}: {
  title?: string;
  subtitle?: string;
  error?: string | null;
}) {
  return (
    <Container maxWidth="sm" sx={{ py: 8 }}>
      <Paper sx={{ p: 4 }}>
        <Typography variant="h5" gutterBottom>
          {title}
        </Typography>
        <Typography color="text.secondary" gutterBottom>
          {subtitle}
        </Typography>
        {error && (
          <Alert severity="info" sx={{ my: 2 }}>
            {error}
          </Alert>
        )}
        {isDevAuth ? (
          <Alert severity="warning" sx={{ mt: 2 }}>
            Dev token is set but the backend rejected it. Make sure
            <code> NEXT_PUBLIC_DEV_ADMIN_TOKEN </code> matches the backend&apos;s
            <code> DEV_ADMIN_TOKEN</code>, and the API is running.
          </Alert>
        ) : isSupabaseConfigured ? (
          <Button
            variant="contained"
            startIcon={<GoogleIcon />}
            onClick={() => signInWithGoogle()}
            sx={{ mt: 2 }}
          >
            Sign in with Google
          </Button>
        ) : (
          <Alert severity="warning" sx={{ mt: 2 }}>
            Auth isn&apos;t configured. Set Supabase keys for production, or a dev
            token for local development.
          </Alert>
        )}
      </Paper>
    </Container>
  );
}
