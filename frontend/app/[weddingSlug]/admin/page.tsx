"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import NextLink from "next/link";

import LogoutIcon from "@mui/icons-material/Logout";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import Alert from "@mui/material/Alert";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";

import {
  adminApi,
  AdminAuthError,
  setAdminWedding,
  type AdminMe,
  type AdminSummary,
  type ContentAdmin,
  type GuestAdmin,
  type MemberAdmin,
  type QuestionAdmin,
  type ResponseAdmin,
  type StoryArcAdmin,
  type WishAdmin,
} from "@/lib/adminApi";
import { isDevAuth, isSupabaseConfigured, signOut, supabase } from "@/lib/adminAuth";

import DetailsPanel from "@/components/admin/DetailsPanel";
import GuestsPanel from "@/components/admin/GuestsPanel";
import LifecycleBanner from "@/components/admin/LifecycleBanner";
import MembersPanel from "@/components/admin/MembersPanel";
import ResponsesPanel from "@/components/admin/ResponsesPanel";
import RsvpPanel from "@/components/admin/RsvpPanel";
import SignInCard from "@/components/admin/SignInCard";
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
  members: MemberAdmin[];
}

export default function AdminPage() {
  const params = useParams<{ weddingSlug: string }>();
  // Bind the module-level admin client to this wedding BEFORE any panel fetches.
  // Safe as a render-time side effect: it's idempotent and only one dashboard is
  // mounted at a time.
  setAdminWedding(params.weddingSlug);

  const [data, setData] = useState<Data | null>(null);
  const [loading, setLoading] = useState(true);
  const [needsAuth, setNeedsAuth] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState(0);

  // No synchronous setState here — all updates happen after the first await,
  // so calling load() from an effect doesn't trigger cascading renders.
  const load = useCallback(async () => {
    try {
      const [me, summary, guests, questions, responses, wishes, arcs, content, members] =
        await Promise.all([
          adminApi.me(),
          adminApi.summary(),
          adminApi.listGuests(),
          adminApi.listQuestions(),
          adminApi.listResponses(),
          adminApi.listWishes(),
          adminApi.listArcs(),
          adminApi.getContent(),
          adminApi.listMembers(),
        ]);
      setData({ me, summary, guests, questions, responses, wishes, arcs, content, members });
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

  // Refresh everything that changes after a mutation. `me` is included now —
  // lifecycle actions (submit/publish/archive) change it.
  const refresh = useCallback(async () => {
    await load();
  }, [load]);

  if (loading) {
    return (
      <Box sx={{ display: "grid", placeItems: "center", minHeight: "60vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (needsAuth || !data) {
    return (
      <SignInCard
        title="Wedding admin"
        subtitle="Sign in to manage guests, questions and RSVPs."
        error={error}
      />
    );
  }

  return (
    <Box>
      <AppBar position="static" color="default" elevation={0} sx={{ borderBottom: 1, borderColor: "divider" }}>
        <Toolbar sx={{ gap: 2, flexWrap: "wrap" }}>
          <Button component={NextLink} href="/dashboard" startIcon={<ArrowBackIcon />} color="inherit">
            My weddings
          </Button>
          <Box sx={{ flexGrow: 1 }}>
            <Typography variant="h6">{data.me.couple_names}</Typography>
            <Typography variant="caption" color="text.secondary">
              {data.me.role === "platform" ? "Platform admin" : data.me.role === "owner" ? "Owner" : "Admin"} · {data.me.email}
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

        <LifecycleBanner me={data.me} onChanged={refresh} />

        <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto" sx={{ mb: 3 }}>
          <Tab label="Overview" />
          <Tab label="Story" />
          <Tab label="Details" />
          <Tab label="RSVP" />
          <Tab label="Theme" />
          <Tab label={`Guests (${data.guests.length})`} />
          <Tab label={`Responses (${data.responses.length})`} />
          <Tab label={`Wishes (${data.wishes.length})`} />
          <Tab label={`Team (${data.members.filter((m) => m.status !== "revoked").length})`} />
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
          {tab === 8 && <MembersPanel me={data.me} members={data.members} onChanged={refresh} />}
        </Stack>
      </Container>
    </Box>
  );
}
