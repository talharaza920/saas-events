"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import BrushIcon from "@mui/icons-material/Brush";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { aiApi, type AiArtifact, type AiJobAdmin, type AiStyleOption } from "@/lib/adminApi";

import { SteerBox, VariantStrip } from "./AiVariants";
import LikenessPhotos from "./LikenessPhotos";

interface Beat {
  text: string;
  image_prompt: string;
}
interface Arc {
  kicker?: string | null;
  heading: string;
  intro?: string | null;
  beats: Beat[];
  climax?: string | null;
  climax_image_prompt?: string | null;
}
interface Claim {
  draft_text?: string;
  reason?: string;
}

function rec(v: unknown): Record<string, unknown> {
  return typeof v === "object" && v !== null ? (v as Record<string, unknown>) : {};
}

/** The proposal's draft, in the shape the editor works with. */
function readArc(job: AiJobAdmin): Arc {
  const a = rec(rec(job.proposal).story_arc);
  const beats = Array.isArray(a.beats) ? a.beats : [];
  return {
    kicker: (a.kicker as string) ?? null,
    heading: String(a.heading ?? ""),
    intro: (a.intro as string) ?? null,
    beats: beats.map((b) => ({
      text: String(rec(b).text ?? ""),
      image_prompt: String(rec(b).image_prompt ?? ""),
    })),
    climax: (a.climax as string) ?? null,
    climax_image_prompt: (a.climax_image_prompt as string) ?? null,
  };
}

/** The panels of this draft, in illustration order: the beats, then the climax. */
function panelsOf(arc: Arc): { key: string; label: string; scene: string }[] {
  const out = arc.beats.map((b, i) => ({
    key: String(i),
    label: String(i + 1).padStart(2, "0"),
    scene: b.image_prompt,
  }));
  if (arc.climax_image_prompt) {
    out.push({ key: "climax", label: "End", scene: arc.climax_image_prompt });
  }
  return out.filter((p) => p.scene.trim());
}

/**
 * The staged story wizard (AI_WIZARD_PLAN 8.5b). The run arrives here as TEXT:
 * the couple reads it, fixes it in place (free — no model call), picks a look,
 * then spends credits on ONE image, iterates the style on that, and only then
 * illustrates the rest. Nothing here writes to the wedding; that's Apply.
 */
export default function StoryDraft({
  job,
  onJob,
  onSpend,
  disabled,
  imagesAvailable,
  likenessAvailable,
  maxLikenessReferences = 0,
}: {
  job: AiJobAdmin;
  onJob: (j: AiJobAdmin) => void;
  /** Called after anything that may have moved the credit balance. */
  onSpend?: () => void;
  disabled?: boolean;
  /** False when this deployment can't illustrate — then we say so rather than
   *  offering a button that can only fail (server: settings.ai_images_available). */
  imagesAvailable?: boolean;
  /** 8.5d: may this wedding put the COUPLE in the illustrations? Needs the
   *  plan's opt-in as well as image generation (server: likeness_available). */
  likenessAvailable?: boolean;
  maxLikenessReferences?: number;
}) {
  const proposal = rec(job.proposal);
  const serverArc = useMemo(() => readArc(job), [job]);
  const images = rec(proposal.beat_images) as Record<string, string>;
  const refused = rec(proposal.images_refused) as Record<string, string>;
  const userEdited: string[] = Array.isArray(proposal.user_edited)
    ? proposal.user_edited.map(String)
    : [];
  const style = rec(proposal.style);
  // With photos of the couple attached, the photographic look is refused
  // server-side — so the chip is disabled rather than offered and rejected.
  const hasLikeness = Number(rec(proposal.likeness).references ?? 0) > 0;
  const grounding = rec(proposal.grounding);
  const claims: Claim[] = (Array.isArray(grounding.unsupported) ? grounding.unsupported : []).map(
    (c) => rec(c) as Claim,
  );
  const flagged = new Set(claims.map((c) => String(c.draft_text ?? "")));

  const [arc, setArc] = useState<Arc>(serverArc);
  const [styles, setStyles] = useState<AiStyleOption[]>([]);
  const [note, setNote] = useState(String(style.note ?? ""));
  const [steer, setSteer] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The server's draft is the source of truth: adopt it whenever it changes (a
  // saved edit, a selected variant, a fresh regeneration), and keep the
  // couple's in-progress keystrokes in between. Adjusting state during render
  // rather than in an effect is React's own recommendation for exactly this
  // "reset local state when a prop changes" case — an effect would render the
  // stale draft once first.
  const [baseline, setBaseline] = useState<Arc>(serverArc);
  if (baseline !== serverArc) {
    setBaseline(serverArc);
    setArc(serverArc);
  }

  useEffect(() => {
    aiApi.styles().then(setStyles).catch(() => setStyles([]));
  }, []);

  const dirty = JSON.stringify(arc) !== JSON.stringify(serverArc);
  const panels = panelsOf(serverArc);
  const pending = panels.filter((p) => !images[p.key] && !refused[p.key]);
  const illustrated = panels.filter((p) => images[p.key]);

  const run = useCallback(async (tag: string, fn: () => Promise<void>) => {
    setBusy(tag);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(null);
    }
  }, []);

  const saveEdits = () =>
    run("save", async () => {
      onJob(await aiApi.editProposal(job.id, { story_arc: arc as unknown as Record<string, unknown> }));
    });

  const pickStyle = (preset: string) =>
    run(`style:${preset}`, async () => {
      onJob(await aiApi.editProposal(job.id, { style_preset: preset, style_note: note }));
    });

  const saveNote = () =>
    run("note", async () => {
      onJob(await aiApi.editProposal(job.id, { style_note: note }));
    });

  // One image at a time is the point: the first one is where they discover
  // whether the style is right, and they shouldn't pay for six to find out.
  const illustrate = (targets?: string[]) =>
    run(targets ? `img:${targets[0]}` : "img:rest", async () => {
      let next = await aiApi.illustrate(job.id, targets);
      // "Illustrate the rest" is a client-driven loop — the server renders a
      // couple per call so no single request runs long.
      if (!targets) {
        for (let guard = 0; guard < 8; guard++) {
          const p = rec(next.proposal);
          const done = { ...(rec(p.beat_images) as object), ...(rec(p.images_refused) as object) };
          if (panelsOf(readArc(next)).every((panel) => panel.key in done)) break;
          next = await aiApi.illustrate(job.id);
        }
      }
      onJob(next);
      onSpend?.();
    });

  const redo = (key: string) =>
    run(`redo:${key}`, async () => {
      const artifact = `arc.beat.${key}` as AiArtifact;
      const variant = await aiApi.regenerate(job.id, artifact, steer[key]);
      // A fresh image is what they just asked to see — select it (the previous
      // one stays one click away in the strip).
      await aiApi.selectVariant(job.id, artifact, variant.id);
      setSteer((s) => ({ ...s, [key]: "" }));
      onJob(await aiApi.getJob(job.id));
      onSpend?.();
    });

  const regenerateText = () =>
    run("regen:text", async () => {
      await aiApi.regenerate(job.id, "arc.text", steer["arc.text"]);
      setSteer((s) => ({ ...s, "arc.text": "" }));
      onJob(await aiApi.getJob(job.id));
      onSpend?.();
    });

  const selectVariant = (artifact: AiArtifact, id: string) =>
    run(`select:${id}`, async () => {
      onJob(await aiApi.selectVariant(job.id, artifact, id));
    });

  const locked = disabled || busy !== null;
  const edited = (path: string) => userEdited.includes(path);

  const line = (
    label: string,
    value: string,
    onChange: (v: string) => void,
    opts: { multiline?: boolean; path?: string; max?: number } = {},
  ) => (
    <TextField
      size="small"
      fullWidth
      label={label}
      value={value}
      multiline={opts.multiline}
      onChange={(e) => onChange(e.target.value.slice(0, opts.max ?? 400))}
      helperText={opts.path && edited(opts.path) ? "Your words — not fact-checked" : undefined}
      slotProps={{ formHelperText: { sx: { color: "text.secondary" } } }}
    />
  );

  const panelImage = (key: string) => {
    const url = images[key];
    const why = refused[key];
    const variants = job.variants.filter((v) => v.artifact === `arc.beat.${key}`);
    // Nothing to show and nothing to offer: the first image goes through the
    // one deliberate button below, not a row of them.
    if (!url && !why && (!illustrated.length || !imagesAvailable)) return null;
    return (
      <Stack spacing={0.75}>
        {url && (
          <Box
            component="img"
            src={url}
            alt={`Illustration for panel ${key}`}
            sx={{ width: 180, borderRadius: 1, display: "block" }}
          />
        )}
        {why && (
          <Typography variant="caption" color="text.secondary">
            This one couldn&apos;t be illustrated ({why}) — it will show as a text panel.
          </Typography>
        )}
        {url ? (
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ alignItems: { sm: "center" } }}>
            <TextField
              size="small"
              label="Change this image"
              placeholder="e.g. brighter, fewer people"
              value={steer[key] ?? ""}
              onChange={(e) => setSteer({ ...steer, [key]: e.target.value.slice(0, 500) })}
              sx={{ maxWidth: 320 }}
            />
            <Button
              size="small"
              disabled={locked}
              startIcon={
                busy === `redo:${key}` ? <CircularProgress size={14} /> : <AutoAwesomeIcon sx={{ fontSize: 16 }} />
              }
              onClick={() => redo(key)}
            >
              Redo this image
            </Button>
          </Stack>
        ) : (
          <Box>
            <Button
              size="small"
              disabled={locked || dirty}
              startIcon={
                busy === `img:${key}` ? <CircularProgress size={14} /> : <BrushIcon sx={{ fontSize: 16 }} />
              }
              onClick={() => illustrate([key])}
            >
              Illustrate this one (1 credit)
            </Button>
          </Box>
        )}
        <VariantStrip
          variants={variants}
          busyId={busy?.startsWith("select:") ? busy.slice(7) : null}
          disabled={locked}
          onSelect={(v) => selectVariant(`arc.beat.${key}` as AiArtifact, v.id)}
        />
      </Stack>
    );
  };

  return (
    <Stack spacing={2}>
      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Typography variant="caption" color="text.secondary">
        Read it, change any word — editing is free. Pictures come after, one at a time, when
        you ask for them.
      </Typography>

      {line("Heading", arc.heading, (v) => setArc({ ...arc, heading: v }), {
        path: "heading",
        max: 120,
      })}
      {line("Intro", arc.intro ?? "", (v) => setArc({ ...arc, intro: v || null }), {
        multiline: true,
        path: "intro",
      })}

      {arc.beats.map((b, i) => (
        <Stack key={i} direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
          <Chip size="small" label={String(i + 1).padStart(2, "0")} variant="outlined" sx={{ mt: 1 }} />
          <Stack spacing={1} sx={{ flexGrow: 1, minWidth: 0 }}>
            <Stack direction="row" spacing={0.5} sx={{ alignItems: "flex-start" }}>
              <Box sx={{ flexGrow: 1 }}>
                {line(
                  `Beat ${i + 1}`,
                  b.text,
                  (v) => {
                    const beats = [...arc.beats];
                    beats[i] = { ...beats[i], text: v };
                    setArc({ ...arc, beats });
                  },
                  { multiline: true, path: `beats.${i}.text` },
                )}
              </Box>
              {flagged.has(b.text) && (
                <WarningAmberIcon color="warning" sx={{ fontSize: 18, mt: 1.5 }} titleAccess="Not traceable to what you told us" />
              )}
            </Stack>
            {line(
              "Illustration",
              b.image_prompt,
              (v) => {
                const beats = [...arc.beats];
                beats[i] = { ...beats[i], image_prompt: v };
                setArc({ ...arc, beats });
              },
              { multiline: true, path: `beats.${i}.image_prompt`, max: 600 },
            )}
            {panelImage(String(i))}
          </Stack>
        </Stack>
      ))}

      <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
        <Chip size="small" label="End" variant="outlined" sx={{ mt: 1 }} />
        <Stack spacing={1} sx={{ flexGrow: 1, minWidth: 0 }}>
          {line("The invitation line", arc.climax ?? "", (v) => setArc({ ...arc, climax: v || null }), {
            multiline: true,
            path: "climax",
          })}
          {line(
            "Illustration",
            arc.climax_image_prompt ?? "",
            (v) => setArc({ ...arc, climax_image_prompt: v || null }),
            { multiline: true, path: "climax_image_prompt", max: 600 },
          )}
          {panelImage("climax")}
        </Stack>
      </Stack>

      {dirty && (
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
          <Button
            variant="contained"
            size="small"
            disabled={locked}
            startIcon={busy === "save" ? <CircularProgress size={14} /> : undefined}
            onClick={saveEdits}
          >
            Save your changes
          </Button>
          <Button size="small" color="inherit" disabled={locked} onClick={() => setArc(serverArc)}>
            Undo
          </Button>
          <Typography variant="caption" color="text.secondary">
            Save before illustrating — pictures follow the words.
          </Typography>
        </Stack>
      )}

      {claims.length > 0 && (
        <Alert severity="warning" icon={<WarningAmberIcon />}>
          <Typography variant="body2" sx={{ mb: 0.5 }}>
            A fact-check pass couldn&apos;t trace {claims.length === 1 ? "this line" : "these lines"}{" "}
            back to what you told us — fix or delete{" "}
            {claims.length === 1 ? "it" : "them"} before applying:
          </Typography>
          {claims.map((c, i) => (
            <Typography key={i} variant="caption" sx={{ display: "block" }}>
              “{String(c.draft_text ?? "")}” — {String(c.reason ?? "")}
            </Typography>
          ))}
        </Alert>
      )}

      <Divider flexItem />

      {/* --- The look, and the money ------------------------------------- */}
      <Stack spacing={1.5}>
        <Typography variant="subtitle2">Illustrations</Typography>
        {!imagesAvailable && (
          <Alert severity="info">
            Illustrations aren&apos;t available on this site right now — your chapter will apply
            as text, and you can add your own pictures from the Story tab.
          </Alert>
        )}
        {likenessAvailable && imagesAvailable && (
          <LikenessPhotos
            job={job}
            onJob={onJob}
            disabled={locked}
            max={maxLikenessReferences}
          />
        )}
        <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
          {styles.map((s) => {
            const blocked = hasLikeness && s.likeness_blocked;
            return (
              <Chip
                key={s.key}
                label={s.label}
                size="small"
                color={style.preset === s.key ? "primary" : "default"}
                variant={style.preset === s.key ? "filled" : "outlined"}
                disabled={locked || blocked}
                title={
                  blocked
                    ? "Not available for pictures of real people — remove your photos to use it"
                    : undefined
                }
                onClick={() => !blocked && pickStyle(s.key)}
              />
            );
          })}
        </Stack>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ alignItems: { sm: "center" } }}>
          <TextField
            size="small"
            fullWidth
            label="Anything else about the look? (optional)"
            placeholder="e.g. lots of green, no flowers"
            value={note}
            onChange={(e) => setNote(e.target.value.slice(0, 200))}
            onBlur={() => note !== (style.note ?? "") && saveNote()}
          />
        </Stack>

        {!imagesAvailable ? null : illustrated.length === 0 ? (
          <Box>
            <Button
              variant="contained"
              disabled={locked || dirty || pending.length === 0}
              startIcon={
                busy?.startsWith("img:") ? <CircularProgress size={16} /> : <BrushIcon />
              }
              onClick={() => illustrate([pending[0]?.key ?? "0"])}
            >
              Illustrate the first scene (1 credit)
            </Button>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
              Start with one. If the look isn&apos;t right, change the style and redo it — then do
              the rest.
            </Typography>
          </Box>
        ) : pending.length > 0 ? (
          <Box>
            <Button
              variant="contained"
              disabled={locked || dirty}
              startIcon={busy === "img:rest" ? <CircularProgress size={16} /> : <BrushIcon />}
              onClick={() => illustrate()}
            >
              Illustrate the rest ({pending.length}{" "}
              {pending.length === 1 ? "panel" : "panels"} · {pending.length}{" "}
              {pending.length === 1 ? "credit" : "credits"})
            </Button>
          </Box>
        ) : (
          <Typography variant="caption" color="text.secondary">
            Every panel is illustrated. Redo any of them above, or apply it below.
          </Typography>
        )}
      </Stack>

      <Divider flexItem />

      {/* Whole-draft regeneration stays available — but it's a NEW version,
          and the couple's own edits live on in the one they have now. */}
      {userEdited.length > 0 && job.variants.some((v) => v.artifact === "arc.text") && (
        <Alert severity="info">
          You&apos;ve edited this draft. Regenerating writes a new version — your edited one stays
          in the list, one click away.
        </Alert>
      )}
      <VariantStrip
        variants={job.variants.filter((v) => v.artifact === "arc.text")}
        busyId={busy?.startsWith("select:") ? busy.slice(7) : null}
        disabled={locked}
        onSelect={(v) => selectVariant("arc.text", v.id)}
      />
      <SteerBox
        value={steer["arc.text"] ?? ""}
        onChange={(v) => setSteer({ ...steer, "arc.text": v })}
        onRegenerate={regenerateText}
        busy={busy === "regen:text"}
        disabled={locked}
        label="Want a different story? Tell it how"
      />
    </Stack>
  );
}
