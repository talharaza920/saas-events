"use client";

import { useCallback, useEffect, useState } from "react";

import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
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
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import {
  adminApi,
  aiApi,
  type AiArtifact,
  type AiCreditsInfo,
  type AiJobAdmin,
  type AiVariantAdmin,
} from "@/lib/adminApi";

import GlyphMark from "./GlyphMark";

// Loose views over the proposal JSON (assembled in app/ai/jobs.py). Every
// field is optional — the review UI renders what's there and nothing else.
interface Fact {
  value?: string;
  supported_by?: string;
}
interface ProposalArcBeat {
  text?: string;
  image_prompt?: string;
}
interface ProposalArc {
  kicker?: string | null;
  heading?: string;
  intro?: string | null;
  beats?: ProposalArcBeat[];
  climax?: string | null;
}
interface ProposalGlyph {
  svg_children?: string;
  concept?: string;
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
  return out;
}

const SECTION_LABELS: Record<string, string> = {
  couple_names: "Your names",
  event_details: "Event details",
  story_arc: "Your story",
  glyph: "Your mark",
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
  const grounding = rec(proposal.grounding);
  const unsupported = (Array.isArray(grounding.unsupported) ? grounding.unsupported : [])
    .map((u) => rec(u))
    .filter((u) => u.draft_text || u.reason);
  const flaggedTexts = new Set(unsupported.map((u) => String(u.draft_text ?? "")));

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

  const arc = rec(proposal.story_arc) as ProposalArc;
  const glyph = rec(proposal.glyph) as ProposalGlyph;
  const details = rec(proposal.event_details);
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

  const steerBox = (artifact: AiArtifact) => (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ alignItems: { sm: "center" } }}>
      <TextField
        size="small"
        fullWidth
        label="Want it different? Tell it how"
        placeholder="e.g. less flowery — and don't mention the rain"
        value={steer[artifact] ?? ""}
        onChange={(e) => setSteer({ ...steer, [artifact]: e.target.value.slice(0, 500) })}
      />
      <Button
        variant="outlined"
        startIcon={busy === `regen:${artifact}` ? <CircularProgress size={16} /> : <AutoAwesomeIcon />}
        disabled={busy !== null}
        onClick={() => regenerate(artifact)}
        sx={{ whiteSpace: "nowrap" }}
      >
        Regenerate
      </Button>
    </Stack>
  );

  const variantStrip = (artifact: AiArtifact) => {
    const variants = job.variants.filter((v) => v.artifact === artifact);
    if (variants.length < 2) return null;
    return (
      <Stack direction="row" spacing={1.5} sx={{ overflowX: "auto", pb: 1 }}>
        {variants.map((v, i) => {
          const c = rec(v.content);
          return (
            <Paper
              key={v.id}
              variant="outlined"
              onClick={() => !v.selected && busy === null && select(artifact, v)}
              sx={{
                p: 1.5,
                minWidth: 180,
                maxWidth: 240,
                cursor: v.selected ? "default" : "pointer",
                borderColor: v.selected ? "primary.main" : "divider",
                borderWidth: v.selected ? 2 : 1,
                flexShrink: 0,
              }}
            >
              <Stack spacing={1}>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                  <Chip
                    size="small"
                    label={v.selected ? "Selected" : `Version ${i + 1}`}
                    color={v.selected ? "primary" : "default"}
                    variant={v.selected ? "filled" : "outlined"}
                  />
                  {busy === `select:${v.id}` && <CircularProgress size={14} />}
                </Stack>
                {artifact === "glyph" ? (
                  <>
                    <GlyphMark svg={String(c.svg_children ?? "")} size={56} />
                    <Typography variant="caption" color="text.secondary">
                      {String(c.concept ?? "")}
                    </Typography>
                  </>
                ) : (
                  <Typography variant="caption" sx={{ display: "-webkit-box", WebkitLineClamp: 4, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                    {String(c.intro ?? (Array.isArray(c.beats) ? rec(c.beats[0]).text ?? "" : ""))}
                  </Typography>
                )}
                {v.steer && (
                  <Typography variant="caption" color="text.secondary" sx={{ fontStyle: "italic" }}>
                    “{v.steer}”
                  </Typography>
                )}
              </Stack>
            </Paper>
          );
        })}
      </Stack>
    );
  };

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
            <Box sx={{ pl: 5.5 }}>
              {arc.kicker && (
                <Typography variant="overline" color="text.secondary">
                  {arc.kicker}
                </Typography>
              )}
              <Typography variant="h6">{arc.heading}</Typography>
              {arc.intro && <Typography color="text.secondary">{arc.intro}</Typography>}
              <Stack spacing={1} sx={{ my: 1.5 }}>
                {(arc.beats ?? []).map((b, i) => {
                  const flagged = flaggedTexts.has(String(b.text ?? ""));
                  return (
                    <Stack key={i} direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
                      <Chip size="small" label={String(i + 1).padStart(2, "0")} variant="outlined" />
                      <Typography variant="body2" sx={{ pt: 0.25 }}>
                        {b.text}
                        {flagged && (
                          <WarningAmberIcon
                            color="warning"
                            sx={{ fontSize: 16, verticalAlign: "text-bottom", ml: 0.5 }}
                          />
                        )}
                      </Typography>
                    </Stack>
                  );
                })}
              </Stack>
              {arc.climax && <Typography variant="body2">{arc.climax}</Typography>}
            </Box>
            {unsupported.length > 0 && (
              <Alert severity="warning" icon={<WarningAmberIcon />}>
                <Typography variant="body2" sx={{ mb: 0.5 }}>
                  A fact-check pass couldn&apos;t trace {unsupported.length === 1 ? "this line" : "these lines"} back to what you told us — read
                  {unsupported.length === 1 ? " it" : " them"} before applying:
                </Typography>
                {unsupported.map((u, i) => (
                  <Typography key={i} variant="caption" sx={{ display: "block" }}>
                    “{String(u.draft_text ?? "")}” — {String(u.reason ?? "")}
                  </Typography>
                ))}
              </Alert>
            )}
            <Divider flexItem />
            {variantStrip("arc.text")}
            {steerBox("arc.text")}
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
            {variantStrip("glyph")}
            {steerBox("glyph")}
          </Stack>
        </Paper>
      )}

      <Typography variant="caption" color="text.secondary">
        The first regeneration of each piece is free; after that each costs 1 credit. Nothing
        goes on your site until you press Apply.
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
