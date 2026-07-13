"use client";

import { useCallback, useEffect, useState } from "react";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";

import {
  adminApi,
  aiApi,
  type AiArtifact,
  type AiCreditsInfo,
  type AiJobAdmin,
  type AiVariantAdmin,
} from "@/lib/adminApi";

import { SteerBox, VariantStrip } from "./AiVariants";
import GlyphMark from "./GlyphMark";
import GuestQuestions from "./GuestQuestions";
import StoryDraft from "./StoryDraft";

// Loose views over the proposal JSON (assembled in app/ai/jobs.py). Every
// field is optional — the review UI renders what's there and nothing else.
interface Fact {
  value?: string;
  supported_by?: string;
}
interface ProposalGlyph {
  svg_children?: string;
  concept?: string;
}
interface ProposalGuest {
  name?: string;
  invite_tier?: string;
  adult_companions?: number;
  child_companions?: number;
}

function rec(v: unknown): Record<string, unknown> {
  return typeof v === "object" && v !== null ? (v as Record<string, unknown>) : {};
}

/** The proposal sections present in this job, in apply order. */
function sectionsOf(job: AiJobAdmin): string[] {
  const p = rec(job.proposal);
  const out: string[] = [];
  if (typeof p.couple_names === "string" && p.couple_names) out.push("couple_names");
  if (Object.keys(rec(p.event_details)).length > 0) out.push("event_details");
  if (Object.keys(rec(p.story_arc)).length > 0) out.push("story_arc");
  if (Object.keys(rec(p.glyph)).length > 0) out.push("glyph");
  if (Array.isArray(p.guests) && p.guests.length > 0) out.push("guests");
  return out;
}

const SECTION_LABELS: Record<string, string> = {
  couple_names: "Your names",
  event_details: "Event details",
  story_arc: "Your story",
  glyph: "Your mark",
  guests: "Guest list",
};

// Owner-facing tier names (tiers are OWNER-facing metadata; guests never see them).
const TIER_LABELS: Record<string, string> = {
  solo: "Solo",
  plus_one: "+1",
  plus_family: "Family",
};

/**
 * The human gate: everything the AI proposed, reviewable section by section,
 * with variants side by side and one bounded steer note per regeneration.
 * Nothing on the wedding changes until Apply — and Apply writes only the
 * server's allowlisted paths (app/ai/apply.py).
 */
export default function AiReviewPanel({
  job,
  onJob,
  onApplied,
}: {
  job: AiJobAdmin;
  /** Every server-updated job (select/regenerate/apply/cancel) flows up here. */
  onJob: (j: AiJobAdmin) => void;
  /** Fired after a successful apply so the surrounding page can refresh. */
  onApplied?: (applied: string[]) => void;
}) {
  const sections = sectionsOf(job);
  const [checked, setChecked] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(sections.map((s) => [s, true])),
  );
  const [steer, setSteer] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [credits, setCredits] = useState<AiCreditsInfo | null>(null);
  const [appliedSections, setAppliedSections] = useState<string[] | null>(null);
  const [iconOn, setIconOn] = useState(false);

  const loadCredits = useCallback(() => {
    aiApi.credits().then(setCredits).catch(() => setCredits(null));
  }, []);
  useEffect(() => {
    // Fetch-on-mount; setState only fires inside the promise callbacks.
    loadCredits();
  }, [loadCredits]);

  const reviewing = job.status === "awaiting_review";
  const proposal = rec(job.proposal);

  const run = async (tag: string, fn: () => Promise<void>) => {
    setBusy(tag);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(null);
    }
  };

  // The glyph's compare-then-pick flow. (The story's own regenerations live in
  // StoryDraft, which owns the staged text→image wizard.)
  const regenerate = (artifact: AiArtifact) =>
    run(`regen:${artifact}`, async () => {
      await aiApi.regenerate(job.id, artifact, steer[artifact]);
      setSteer((s) => ({ ...s, [artifact]: "" }));
      onJob(await aiApi.getJob(job.id));
      loadCredits();
    });

  const select = (artifact: AiArtifact, v: AiVariantAdmin) =>
    run(`select:${v.id}`, async () => {
      onJob(await aiApi.selectVariant(job.id, artifact, v.id));
    });

  const apply = () =>
    run("apply", async () => {
      const picked = sections.filter((s) => checked[s]);
      const result = await aiApi.applyJob(job.id, picked);
      setAppliedSections(result.applied);
      onJob(await aiApi.getJob(job.id));
      loadCredits();
      onApplied?.(result.applied);
    });

  const cancel = () =>
    run("cancel", async () => {
      onJob(await aiApi.cancelJob(job.id));
    });

  // --- Post-apply state ------------------------------------------------------
  if (job.status === "applied" || appliedSections) {
    const applied = appliedSections ?? sections;
    return (
      <Stack spacing={2}>
        <Alert severity="success">
          Applied to your wedding: {applied.map((s) => SECTION_LABELS[s] ?? s).join(", ")}. You
          can edit every word of it from the dashboard.
        </Alert>
        {applied.includes("glyph") && (
          <FormControlLabel
            control={
              <Switch
                checked={iconOn}
                disabled={busy === "icon"}
                onChange={(e) => {
                  const on = e.target.checked;
                  setIconOn(on);
                  run("icon", async () => {
                    await adminApi.updateContent({
                      content: { brand: { icon_mode: on ? "svg" : "default" } },
                    });
                    onApplied?.([]);
                  });
                }}
              />
            }
            label="Use it as your cover icon"
          />
        )}
        {error && <Alert severity="error">{error}</Alert>}
      </Stack>
    );
  }

  if (!reviewing) {
    return job.status === "failed" ? (
      <Alert severity="error">
        {job.error || "The run failed."} Your credits were refunded — start a fresh run whenever
        you like.
      </Alert>
    ) : (
      <Alert severity="info">This run is {job.status.replace(/_/g, " ")}.</Alert>
    );
  }

  const glyph = rec(proposal.glyph) as ProposalGlyph;
  const details = rec(proposal.event_details);
  const guests = (Array.isArray(proposal.guests) ? proposal.guests : []).map(
    (g) => rec(g) as ProposalGuest,
  );
  const guestsUnresolved = Array.isArray(proposal.guests_unresolved)
    ? proposal.guests_unresolved.map(String)
    : [];
  const pickedCount = sections.filter((s) => checked[s]).length;

  const sectionHeader = (key: string, subtitle: string) => (
    <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
      <Checkbox
        checked={Boolean(checked[key])}
        onChange={(e) => setChecked({ ...checked, [key]: e.target.checked })}
        slotProps={{ input: { "aria-label": `Apply ${SECTION_LABELS[key]}` } }}
      />
      <Box>
        <Typography variant="subtitle1">{SECTION_LABELS[key]}</Typography>
        <Typography variant="caption" color="text.secondary">
          {subtitle}
        </Typography>
      </Box>
    </Stack>
  );

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
        <Typography variant="h6" sx={{ flexGrow: 1 }}>
          Here&apos;s what it made — you decide what sticks
        </Typography>
        {credits && (
          <Chip size="small" variant="outlined" label={`AI credits: ${credits.remaining}`} />
        )}
      </Stack>

      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {sections.includes("couple_names") && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1}>
            {sectionHeader("couple_names", "Becomes the site title and cover wordmark")}
            <Typography variant="h6" sx={{ pl: 5.5 }}>
              {String(proposal.couple_names)}
            </Typography>
          </Stack>
        </Paper>
      )}

      {sections.includes("event_details") && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1}>
            {sectionHeader("event_details", "Only what your submissions actually said — blanks stay blank")}
            <Stack spacing={0.5} sx={{ pl: 5.5 }}>
              {(() => {
                const venue = rec(details.venue);
                const date = details.date as Fact | undefined;
                const time = details.time as Fact | undefined;
                const row = (label: string, value: string, from?: string) => (
                  <Box key={label}>
                    <Typography variant="body2">
                      <strong>{label}:</strong> {value}
                    </Typography>
                    {from && (
                      <Typography variant="caption" color="text.secondary">
                        from “{from}”
                      </Typography>
                    )}
                  </Box>
                );
                const rows = [];
                if (venue.name) rows.push(row("Venue", String(venue.name)));
                if (venue.address) rows.push(row("Address", String(venue.address)));
                if (date?.value) rows.push(row("Date", date.value, date.supported_by));
                if (time?.value) rows.push(row("Time", time.value, time.supported_by));
                return rows;
              })()}
            </Stack>
          </Stack>
        </Paper>
      )}

      {sections.includes("story_arc") && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5}>
            {sectionHeader("story_arc", "Added as a new story chapter — it won't touch existing ones")}
            <Box sx={{ pl: { xs: 0, sm: 5.5 } }}>
              {/* 8.5b: the story is a staged wizard of its own — text you can
                  edit for free, then images one deliberate click at a time. */}
              <StoryDraft
                job={job}
                onJob={onJob}
                onSpend={loadCredits}
                disabled={busy !== null}
                imagesAvailable={credits?.images_available ?? false}
                likenessAvailable={credits?.likeness_available ?? false}
                maxLikenessReferences={credits?.max_likeness_references ?? 0}
              />
            </Box>
          </Stack>
        </Paper>
      )}

      {sections.includes("glyph") && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5}>
            {sectionHeader("glyph", "A simple monochrome mark for your cover — using it is a separate switch")}
            <Stack direction="row" spacing={2} sx={{ pl: 5.5, alignItems: "center" }}>
              <GlyphMark svg={String(glyph.svg_children ?? "")} size={72} />
              <Typography color="text.secondary">{glyph.concept}</Typography>
            </Stack>
            <Divider flexItem />
            <VariantStrip
              variants={job.variants.filter((v) => v.artifact === "glyph")}
              busyId={busy?.startsWith("select:") ? busy.slice(7) : null}
              disabled={busy !== null}
              onSelect={(v) => select("glyph", v)}
            />
            <SteerBox
              value={steer["glyph"] ?? ""}
              onChange={(v) => setSteer({ ...steer, glyph: v })}
              onRegenerate={() => regenerate("glyph")}
              busy={busy === "regen:glyph"}
              disabled={busy !== null}
            />
          </Stack>
        </Paper>
      )}

      {/* 8.5c: the ask-back sits ABOVE the list, and outside the section
          checkboxes — it isn't something to apply, it's something to answer.
          It shows even when nothing legible was found (all questions, no rows). */}
      <GuestQuestions job={job} onJob={onJob} disabled={busy !== null} />

      {sections.includes("guests") && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5}>
            {sectionHeader(
              "guests",
              "New guest rows with invite links — +1 and kids allowances come from your own markers, never guessed",
            )}
            <Stack spacing={0.75} sx={{ pl: 5.5 }}>
              {guests.map((g, i) => (
                <Stack key={i} direction="row" spacing={1} sx={{ alignItems: "center" }}>
                  <Typography variant="body2" sx={{ minWidth: 160 }}>
                    {g.name}
                  </Typography>
                  <Chip
                    size="small"
                    variant="outlined"
                    label={TIER_LABELS[g.invite_tier ?? ""] ?? g.invite_tier}
                  />
                  {(g.child_companions ?? 0) > 0 && (
                    <Typography variant="caption" color="text.secondary">
                      {g.adult_companions} adult{(g.adult_companions ?? 0) === 1 ? "" : "s"} +{" "}
                      {g.child_companions} kid{(g.child_companions ?? 0) === 1 ? "" : "s"}
                    </Typography>
                  )}
                </Stack>
              ))}
            </Stack>
            {guestsUnresolved.length > 0 && (
              <Alert severity="info">
                Left {guestsUnresolved.length === 1 ? "this entry" : "these entries"} out rather
                than guess who {guestsUnresolved.length === 1 ? "it means" : "they mean"}:{" "}
                {guestsUnresolved.join(", ")}. Add them from the Guests tab if you need them.
              </Alert>
            )}
          </Stack>
        </Paper>
      )}

      <Typography variant="caption" color="text.secondary">
        Editing anything yourself is free. The first regeneration of each piece is free too;
        after that each costs 1 credit, as does each illustration. Nothing goes on your site
        until you press Apply.
      </Typography>

      <Stack direction="row" spacing={1.5}>
        <Button
          variant="contained"
          disabled={busy !== null || pickedCount === 0}
          onClick={apply}
          startIcon={busy === "apply" ? <CircularProgress size={16} /> : undefined}
        >
          Apply {pickedCount} of {sections.length}
        </Button>
        <Button color="inherit" disabled={busy !== null} onClick={cancel}>
          Discard this run
        </Button>
      </Stack>
    </Stack>
  );
}
