"use client";

import { useCallback, useEffect, useState } from "react";

import GoogleIcon from "@mui/icons-material/Google";
import LogoutIcon from "@mui/icons-material/Logout";
import Alert from "@mui/material/Alert";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Container from "@mui/material/Container";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";

import {
  adminApi,
  AdminAuthError,
  type AdminMe,
  type AdminSummary,
  type ContentAdmin,
  type GuestAdmin,
  type QuestionAdmin,
  type ResponseAdmin,
  type StoryArcAdmin,
  type WishAdmin,
} from "@/lib/adminApi";
import {
  isDevAuth,
  isSupabaseConfigured,
  signInWithGoogle,
  signOut,
  supabase,
} from "@/lib/adminAuth";

import DetailsPanel from "@/components/admin/DetailsPanel";
import GuestsPanel from "@/components/admin/GuestsPanel";
import ResponsesPanel from "@/components/admin/ResponsesPanel";
import RsvpPanel from "@/components/admin/RsvpPanel";
import StoryPanel from "@/components/admin/StoryPanel";
import SummaryPanel from "@/components/admin/SummaryPanel";
import ThemePanel from "@/components/admin/ThemePanel";
import WishesPanel from "@/components/admin/WishesPanel";

interface Data {
  me: AdminMe;
  summary: AdminSummary;
  guests: GuestAdmin[];
  questions: QuestionAdmin[];
  responses: ResponseAdmin[];
  wishes: WishAdmin[];
  arcs: StoryArcAdmin[];
  content: ContentAdmin;
}

export default function AdminPage() {
  const [data, setData] = useState<Data | null>(null);
  const [loading, setLoading] = useState(true);
  const [needsAuth, setNeedsAuth] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState(0);

  // No synchronous setState here — all updates happen after the first await,
  // so calling load() from an effect doesn't trigger cascading renders.
  const load = useCallback(async () => {
    try {
      const [me, summary, guests, questions, responses, wishes, arcs, content] = await Promise.all([
        adminApi.me(),
        adminApi.summary(),
        adminApi.listGuests(),
        adminApi.listQuestions(),
        adminApi.listResponses(),
        adminApi.listWishes(),
        adminApi.listArcs(),
        adminApi.getContent(),
      ]);
      setData({ me, summary, guests, questions, responses, wishes, arcs, content });
      setNeedsAuth(false);
      setError(null);
    } catch (e) {
      if (e instanceof AdminAuthError) {
        setNeedsAuth(true);
        setError(e.message);
      } else {
        setError(e instanceof Error ? e.message : "Could not load the dashboard.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Fetch-on-mount: load() only calls setState after its first await, so this
    // doesn't cause the cascading renders the rule guards against.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    // Reload once the Supabase OAuth redirect lands and a session appears.
    if (isSupabaseConfigured) {
      const { data: sub } = supabase().auth.onAuthStateChange((event) => {
        if (event === "SIGNED_IN") load();
      });
      return () => sub.subscription.unsubscribe();
    }
  }, [load]);

  // Refresh only the data that changes after a mutation (keep `me` as-is).
  const refresh = useCallback(async () => {
    const [summary, guests, questions, responses, wishes, arcs, content] = await Promise.all([
      adminApi.summary(),
      adminApi.listGuests(),
      adminApi.listQuestions(),
      adminApi.listResponses(),
      adminApi.listWishes(),
      adminApi.listArcs(),
      adminApi.getContent(),
    ]);
    setData((prev) =>
      prev ? { ...prev, summary, guests, questions, responses, wishes, arcs, content } : prev,
    );
  }, []);

  if (loading) {
    return (
      <Box sx={{ display: "grid", placeItems: "center", minHeight: "60vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (needsAuth || !data) {
    return (
      <Container maxWidth="sm" sx={{ py: 8 }}>
        <Paper sx={{ p: 4 }}>
          <Typography variant="h5" gutterBottom>
            Wedding admin
          </Typography>
          <Typography color="text.secondary" gutterBottom>
            Sign in to manage guests, questions and RSVPs.
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

  return (
    <Box>
      <AppBar position="static" color="default" elevation={0} sx={{ borderBottom: 1, borderColor: "divider" }}>
        <Toolbar sx={{ gap: 2, flexWrap: "wrap" }}>
          <Box sx={{ flexGrow: 1 }}>
            <Typography variant="h6">{data.me.couple_names}</Typography>
            <Typography variant="caption" color="text.secondary">
              Admin · {data.me.email}
            </Typography>
          </Box>
          {!isDevAuth && isSupabaseConfigured && (
            <Button
              startIcon={<LogoutIcon />}
              color="inherit"
              onClick={async () => {
                await signOut();
                setData(null);
                setNeedsAuth(true);
              }}
            >
              Sign out
            </Button>
          )}
        </Toolbar>
      </AppBar>

      <Container maxWidth="lg" sx={{ py: 3 }}>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
        <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto" sx={{ mb: 3 }}>
          <Tab label="Overview" />
          <Tab label="Story" />
          <Tab label="Details" />
          <Tab label="RSVP" />
          <Tab label="Theme" />
          <Tab label={`Guests (${data.guests.length})`} />
          <Tab label={`Responses (${data.responses.length})`} />
          <Tab label={`Wishes (${data.wishes.length})`} />
        </Tabs>

        <Stack>
          {tab === 0 && <SummaryPanel summary={data.summary} />}
          {tab === 1 && <StoryPanel arcs={data.arcs} onChanged={refresh} />}
          {tab === 2 && (
            <DetailsPanel
              content={data.content}
              sides={Array.from(
                new Set(
                  data.guests
                    .map((g) => (g.side ?? "").trim())
                    .filter((sideName) => sideName !== ""),
                ),
              ).sort()}
              onChanged={refresh}
            />
          )}
          {tab === 3 && (
            <RsvpPanel content={data.content} questions={data.questions} onChanged={refresh} />
          )}
          {tab === 4 && <ThemePanel content={data.content} onChanged={refresh} />}
          {tab === 5 && (
            <GuestsPanel
              guests={data.guests}
              arcs={data.arcs}
              questions={data.questions}
              content={data.content}
              onChanged={refresh}
            />
          )}
          {tab === 6 && <ResponsesPanel responses={data.responses} />}
          {tab === 7 && <WishesPanel wishes={data.wishes} onChanged={refresh} />}
        </Stack>
      </Container>
    </Box>
  );
}
