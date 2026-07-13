"use client";

import { useCallback, useEffect, useState } from "react";
import NextLink from "next/link";
import { useParams, useRouter } from "next/navigation";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Container from "@mui/material/Container";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import Stepper from "@mui/material/Stepper";
import Typography from "@mui/material/Typography";

import { adminApi, setAdminWedding, AdminAuthError, type AdminMe } from "@/lib/adminApi";
import AiAssist from "@/components/ai/AiAssist";
import GuestsIntake from "@/components/admin/GuestsIntake";
import SignInCard from "@/components/admin/SignInCard";

const STEPS = ["Key details", "Your story", "Guest list"] as const;

/**
 * First-time setup (AI_WIZARD_PLAN 8.5a): three steps, every one skippable,
 * each an AI entry point over the thing it fills in — the SAME `AiAssist` the
 * Details / Story / Guests tabs use, so nothing here is a parallel code path.
 *
 * The wedding already exists (created by /create), so this runs entirely under
 * the membership-checked admin API. Leaving early costs nothing: what's done is
 * derived from the wedding, and the dashboard re-offers the rest.
 */
export default function SetupPage() {
  const params = useParams<{ weddingSlug: string }>();
  const router = useRouter();
  setAdminWedding(params.weddingSlug);

  const [me, setMe] = useState<AdminMe | null>(null);
  const [needsAuth, setNeedsAuth] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState(0);
  const [finishing, setFinishing] = useState(false);

  const adminPath = `/${params.weddingSlug}/admin`;

  const load = useCallback(async () => {
    try {
      setMe(await adminApi.me());
      setNeedsAuth(false);
    } catch (e) {
      if (e instanceof AdminAuthError) setNeedsAuth(true);
      else setError(e instanceof Error ? e.message : "Could not load this wedding.");
    }
  }, []);

  useEffect(() => {
    // Fetch-on-mount: setState only happens after load()'s first await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  if (needsAuth) {
    return <SignInCard title="Set up your wedding" subtitle="Sign in to pick up where you left off." />;
  }
  if (!me) {
    return (
      <Box sx={{ display: "grid", placeItems: "center", minHeight: "60vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  /** Dismiss the checklist and land on the dashboard. Owner-only server-side;
   *  for a co-admin the dismissal simply doesn't stick, which is harmless. */
  const finish = async () => {
    setFinishing(true);
    try {
      await adminApi.updateWeddingSettings({ setup_dismissed: true });
    } catch {
      /* the card reappearing is a nuisance, not an error worth blocking on */
    }
    router.push(adminPath);
  };

  const aiOff = me.entitlements?.ai_enabled !== true;

  return (
    <Container maxWidth="md" sx={{ py: 6 }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Let&apos;s set up {me.couple_names}
          </Typography>
          <Typography color="text.secondary">
            Three steps, all optional — skip any of them and do it later. Everything you add here is
            editable afterwards from the dashboard tabs, and nothing goes live until you publish.
          </Typography>
        </Box>

        {error && (
          <Alert severity="error" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        <Stepper activeStep={step} alternativeLabel>
          {STEPS.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>

        <Paper sx={{ p: { xs: 2, sm: 3 } }}>
          <Stack spacing={2}>
            {aiOff && (
              <Alert severity="info">
                AI assistance isn&apos;t part of this wedding&apos;s plan — you can still write
                every part of the site by hand from the dashboard.
              </Alert>
            )}

            {step === 0 && (
              <>
                <Typography variant="h6">Key details</Typography>
                <Typography variant="body2" color="text.secondary">
                  The venue, the date, the time. Paste the message you&apos;ve been sending people,
                  or record a voice note — it pulls the facts out, looks the venue up for a real
                  address, and shows you everything before saving.
                </Typography>
                <AiAssist
                  me={me}
                  kind="details"
                  blurb="Anything works: a paragraph, a forwarded message, a photo of the venue quote."
                  placeholder="We're getting married at Fern Hall on May 1st, 2027 at 3pm…"
                  cta="Fill in my details"
                />
              </>
            )}

            {step === 1 && (
              <>
                <Typography variant="h6">Your story</Typography>
                <Typography variant="body2" color="text.secondary">
                  The illustrated part of the invitation — how you met, what happened next, the
                  proposal. Attaching photos and material about the two of you helps it match your
                  actual story rather than a generic one.
                </Typography>
                <AiAssist
                  me={me}
                  kind="story_arc"
                  blurb="Tell it in your own words, or attach a voice note and whatever photos you have."
                  placeholder="We met at a bus stop in the rain…"
                  cta="Draft my story"
                />
              </>
            )}

            {step === 2 && (
              <>
                <Typography variant="h6">Guest list</Typography>
                <Typography variant="body2" color="text.secondary">
                  However the list exists today — a spreadsheet, a WhatsApp thread, a note, a photo
                  of a page. A spreadsheet is read straight through, no AI involved; anything else
                  goes to the assistant. Who gets a +1 comes from your own markers, and you check
                  every row before it&apos;s added.
                </Typography>
                <GuestsIntake me={me} onChanged={() => {}} />
              </>
            )}
          </Stack>
        </Paper>

        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", flexWrap: "wrap" }}>
          <Button disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
            Back
          </Button>
          <Box sx={{ flexGrow: 1 }} />
          {step < STEPS.length - 1 ? (
            <>
              <Button onClick={() => setStep((s) => s + 1)}>Skip this step</Button>
              <Button variant="contained" onClick={() => setStep((s) => s + 1)}>
                Next
              </Button>
            </>
          ) : (
            <Button variant="contained" onClick={finish} disabled={finishing}>
              {finishing ? <CircularProgress size={22} /> : "Finish — go to my dashboard"}
            </Button>
          )}
        </Stack>

        <Box>
          <Button component={NextLink} href={adminPath} size="small">
            I&apos;ll do this later — take me to the dashboard
          </Button>
        </Box>
      </Stack>
    </Container>
  );
}
