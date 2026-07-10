"use client";

import { useState } from "react";

import AddIcon from "@mui/icons-material/Add";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { adminApi, type StoryArcAdmin } from "@/lib/adminApi";

import ArcEditor from "./ArcEditor";

/**
 * The "Story" tab. Manages the wedding's story arcs: add / duplicate / show-hide
 * / reorder / delete, with each arc's content edited inline via {@link ArcEditor}.
 * Guests see every *visible* arc by default; the Guests tab can override which
 * arc(s) a specific invitee sees (targeted by arc id — never the tier).
 */
export default function StoryPanel({
  arcs,
  onChanged,
}: {
  arcs: StoryArcAdmin[];
  onChanged: () => void | Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | false>(arcs.length === 1 ? arcs[0].id : false);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  function addArc() {
    const sort_order = arcs.length ? Math.max(...arcs.map((a) => a.sort_order)) + 1 : 0;
    run(() =>
      adminApi.createArc({ title: "New chapter", visible: true, sort_order, content: {} }),
    );
  }

  function duplicate(a: StoryArcAdmin) {
    const sort_order = Math.max(...arcs.map((x) => x.sort_order)) + 1;
    run(() =>
      adminApi.createArc({
        title: `${a.title} (copy)`,
        visible: false, // duplicate lands hidden so it doesn't surprise guests
        sort_order,
        content: a.content,
      }),
    );
  }

  function toggleVisible(a: StoryArcAdmin) {
    run(() => adminApi.updateArc(a.id, { visible: !a.visible }));
  }

  function move(i: number, dir: -1 | 1) {
    const j = i + dir;
    if (j < 0 || j >= arcs.length) return;
    const a = arcs[i];
    const b = arcs[j];
    // Swap sort_order on the two neighbours (backend re-sorts on read).
    run(async () => {
      await adminApi.updateArc(a.id, { sort_order: b.sort_order });
      await adminApi.updateArc(b.id, { sort_order: a.sort_order });
    });
  }

  function remove(a: StoryArcAdmin) {
    if (!window.confirm(`Delete the arc “${a.title}”? This can't be undone.`)) return;
    run(() => adminApi.deleteArc(a.id));
  }

  if (arcs.length === 0) {
    return (
      <Paper sx={{ p: 4 }}>
        <Stack spacing={2} alignItems="flex-start">
          <Typography variant="h6">Your story</Typography>
          <Typography color="text.secondary">
            Build the illustrated story shown on the invitation — a few numbered
            steps and an optional “you’re invited” finale. You can add more than
            one arc later and show a different one to specific guests.
          </Typography>
          {error && <Alert severity="error">{error}</Alert>}
          <Button variant="contained" onClick={addArc} disabled={busy}>
            {busy ? "Creating…" : "Create your story"}
          </Button>
        </Stack>
      </Paper>
    );
  }

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Box>
          <Typography variant="h6">Story arcs</Typography>
          <Typography variant="body2" color="text.secondary">
            {arcs.length > 1
              ? "Guests see every visible arc. To show specific arcs to specific people, edit a guest in the Guests tab and use its Story arc override."
              : "Guests see every visible arc. Add a second arc to unlock per-guest targeting (a Story arc override appears when editing a guest)."}
          </Typography>
        </Box>
        <Button startIcon={<AddIcon />} variant="contained" onClick={addArc} disabled={busy}>
          Add arc
        </Button>
      </Box>

      {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}

      {arcs.map((a, i) => (
        <Accordion
          key={a.id}
          expanded={expanded === a.id}
          onChange={(_, isOpen) => setExpanded(isOpen ? a.id : false)}
          disableGutters
        >
          {/* The summary holds ONLY the title (it renders a <button>, so interactive
              controls can't nest inside it — they sit beside it as siblings). */}
          <Box sx={{ display: "flex", alignItems: "center", pr: 1 }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ flexGrow: 1, minWidth: 0 }}>
              <Typography
                sx={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              >
                {a.title || "Untitled arc"}
              </Typography>
            </AccordionSummary>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ flex: "none" }}>
              {!a.visible && <Chip size="small" label="Hidden" />}
              <FormControlLabel
                sx={{ mr: 0 }}
                control={
                  <Switch
                    size="small"
                    checked={a.visible}
                    onChange={() => toggleVisible(a)}
                    disabled={busy}
                  />
                }
                label={<Typography variant="caption">Visible</Typography>}
              />
              <Tooltip title="Move up">
                <span>
                  <IconButton size="small" onClick={() => move(i, -1)} disabled={busy || i === 0}>
                    <ArrowUpwardIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
              <Tooltip title="Move down">
                <span>
                  <IconButton
                    size="small"
                    onClick={() => move(i, 1)}
                    disabled={busy || i === arcs.length - 1}
                  >
                    <ArrowDownwardIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
              <Tooltip title="Duplicate">
                <IconButton size="small" onClick={() => duplicate(a)} disabled={busy}>
                  <ContentCopyIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title="Delete arc">
                <IconButton size="small" color="error" onClick={() => remove(a)} disabled={busy}>
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
          </Box>
          <AccordionDetails sx={{ p: { xs: 1.5, sm: 2.5 } }}>
            <ArcEditor key={a.id} arc={a} onSaved={onChanged} />
          </AccordionDetails>
        </Accordion>
      ))}
    </Stack>
  );
}
