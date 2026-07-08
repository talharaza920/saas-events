"use client";

import { useCallback, useEffect, useState } from "react";
import NextLink from "next/link";

import AddIcon from "@mui/icons-material/Add";
import LogoutIcon from "@mui/icons-material/Logout";
import Alert from "@mui/material/Alert";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";

import { AdminAuthError } from "@/lib/adminApi";
import { isDevAuth, isSupabaseConfigured, signOut, supabase } from "@/lib/adminAuth";
import { meApi, type MeResponse, type MyWedding } from "@/lib/meApi";
import SignInCard from "@/components/admin/SignInCard";

const STATUS_COLOR: Record<string, "default" | "info" | "success" | "warning" | "error"> = {
  draft: "default",
  pending_approval: "info",
  active: "success",
  suspended: "warning",
  archived: "error",
};

/**
 * Post-login home (SAAS_PLAN 1.4): every wedding you belong to with your role,
 * plus entry points to create a wedding and (for platform admins) the console.
 */
export default function DashboardPage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [weddings, setWeddings] = useState<MyWedding[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [needsAuth, setNeedsAuth] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [meRes, list] = await Promise.all([meApi.me(), meApi.myWeddings()]);
      setMe(meRes);
      setWeddings(list);
      setNeedsAuth(false);
      setError(null);
    } catch (e) {
      if (e instanceof AdminAuthError) {
        setNeedsAuth(true);
        setError(e.message);
      } else {
        setError(e instanceof Error ? e.message : "Could not load your weddings.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    if (isSupabaseConfigured) {
      const { data: sub } = supabase().auth.onAuthStateChange((event) => {
        if (event === "SIGNED_IN") load();
      });
      return () => sub.subscription.unsubscribe();
    }
  }, [load]);

  if (loading) {
    return (
      <Box sx={{ display: "grid", placeItems: "center", minHeight: "60vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (needsAuth || !me) {
    return (
      <SignInCard
        title="Your weddings"
        subtitle="Sign in to manage your weddings or create a new one."
        error={error}
      />
    );
  }

  return (
    <Box>
      <AppBar position="static" color="default" elevation={0} sx={{ borderBottom: 1, borderColor: "divider" }}>
        <Toolbar sx={{ gap: 2 }}>
          <Box sx={{ flexGrow: 1 }}>
            <Typography variant="h6">Your weddings</Typography>
            <Typography variant="caption" color="text.secondary">
              {me.email}
            </Typography>
          </Box>
          {me.is_platform_admin && (
            <Button component={NextLink} href="/platform" color="inherit">
              Platform console
            </Button>
          )}
          {!isDevAuth && isSupabaseConfigured && (
            <Button
              startIcon={<LogoutIcon />}
              color="inherit"
              onClick={async () => {
                await signOut();
                setMe(null);
                setNeedsAuth(true);
              }}
            >
              Sign out
            </Button>
          )}
        </Toolbar>
      </AppBar>

      <Container maxWidth="md" sx={{ py: 4 }}>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        <Stack spacing={2}>
          {(weddings ?? []).map((w) => (
            <Card key={w.slug} variant="outlined">
              <CardActionArea component={NextLink} href={`/${w.slug}/admin`}>
                <CardContent>
                  <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Typography variant="h6" sx={{ flexGrow: 1 }}>
                      {w.couple_names}
                    </Typography>
                    <Chip size="small" label={w.role} color={w.role === "owner" ? "primary" : "default"} />
                    <Chip
                      size="small"
                      variant="outlined"
                      label={w.status.replace("_", " ")}
                      color={STATUS_COLOR[w.status] ?? "default"}
                    />
                    {w.status === "active" && (
                      <Chip
                        size="small"
                        variant="outlined"
                        label={w.published ? "published" : "not published"}
                        color={w.published ? "success" : "default"}
                      />
                    )}
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    /{w.slug} · {w.guest_count} guest{w.guest_count === 1 ? "" : "s"}
                  </Typography>
                </CardContent>
              </CardActionArea>
            </Card>
          ))}

          {(weddings ?? []).length === 0 && (
            <Alert severity="info">
              You don&apos;t belong to any weddings yet — create one, or accept an invite from a
              wedding&apos;s owner.
            </Alert>
          )}

          <Box>
            <Button component={NextLink} href="/create" variant="contained" startIcon={<AddIcon />}>
              Create a wedding
            </Button>
          </Box>
        </Stack>
      </Container>
    </Box>
  );
}
