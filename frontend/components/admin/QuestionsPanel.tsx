"use client";

import { useMemo, useState } from "react";

import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import AddIcon from "@mui/icons-material/Add";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { adminApi, type QuestionAdmin } from "@/lib/adminApi";

interface FormValues {
  prompt: string;
  qtype: string;
  optionsText: string; // newline/comma separated
  required: boolean;
  scope: string;
  applies_to: string;
  visibility: string;
  tiers: string[];
}

const QTYPES = [
  { value: "text", label: "Free text" },
  { value: "number", label: "Number" },
  { value: "choice", label: "Single choice (pick one)" },
  { value: "multi_choice", label: "Multiple choice (pick any)" },
  { value: "yesno", label: "Yes / No" },
];
const SCOPES = [
  { value: "invitee", label: "Per invitee (asked once)" },
  { value: "person", label: "Per person (each attendee)" },
];
const APPLIES = [
  { value: "everyone", label: "Everyone" },
  { value: "adults", label: "Adults only" },
  { value: "children", label: "Children only" },
];
// qtypes that use the options editor.
const HAS_OPTIONS = new Set(["choice", "multi_choice"]);
const ALL_TIERS = ["solo", "plus_one", "plus_family"];

function fromQuestion(q?: QuestionAdmin | null): FormValues {
  return {
    prompt: q?.prompt ?? "",
    qtype: q?.qtype ?? "text",
    optionsText: (q?.options ?? []).join("\n"),
    required: q?.required ?? false,
    scope: q?.scope ?? "invitee",
    applies_to: q?.applies_to ?? "everyone",
    visibility: q?.visibility ?? "all",
    tiers: q?.visibility === "tier" ? (q?.visibility_ref as string[]) : [],
  };
}

export default function QuestionsPanel({
  questions,
  onChanged,
  scope,
}: {
  questions: QuestionAdmin[];
  onChanged: () => void;
  /** When set, show & add only this scope's questions (per-person under Step 3,
   * per-invitee under Step 5). Omit to show both groups together. */
  scope?: "person" | "invitee";
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<QuestionAdmin | null>(null);
  const [values, setValues] = useState<FormValues>(fromQuestion(null));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reordering, setReordering] = useState(false);

  // Questions split by scope. The RSVP flow is fixed (confirm → contact →
  // per-person → per-invitee); reordering only rearranges within a group.
  const personQs = useMemo(
    () => questions.filter((q) => q.scope === "person").sort((a, b) => a.sort_order - b.sort_order),
    [questions],
  );
  const inviteeQs = useMemo(
    () => questions.filter((q) => q.scope === "invitee").sort((a, b) => a.sort_order - b.sort_order),
    [questions],
  );

  /** Move a question up/down within its own group, then renumber sort_order across
   * all questions (per-person first, then per-invitee — matching the RSVP flow). */
  async function reorder(scope: "person" | "invitee", index: number, dir: -1 | 1) {
    const group = scope === "person" ? personQs : inviteeQs;
    const target = index + dir;
    if (target < 0 || target >= group.length) return;
    const ng = [...group];
    [ng[index], ng[target]] = [ng[target], ng[index]];
    const combined = scope === "person" ? [...ng, ...inviteeQs] : [...personQs, ...ng];
    const updates = combined.flatMap((q, i) =>
      q.sort_order === i ? [] : [adminApi.updateQuestion(q.id, { sort_order: i })],
    );
    if (updates.length === 0) return;
    setReordering(true);
    try {
      await Promise.all(updates);
      onChanged();
    } finally {
      setReordering(false);
    }
  }

  function openAdd() {
    setEditing(null);
    // Default a new question to this section's scope (Step 3 = person, Step 5 = invitee).
    setValues({ ...fromQuestion(null), scope: scope ?? "invitee" });
    setError(null);
    setOpen(true);
  }
  function openEdit(q: QuestionAdmin) {
    setEditing(q);
    setValues(fromQuestion(q));
    setError(null);
    setOpen(true);
  }

  async function save() {
    if (!values.prompt.trim()) {
      setError("A prompt is required.");
      return;
    }
    const usesOptions = HAS_OPTIONS.has(values.qtype);
    const options = usesOptions
      ? values.optionsText
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean)
      : [];
    if (usesOptions && options.length < 2) {
      setError("Add at least two choices (one per line).");
      return;
    }
    const visibility = values.visibility;
    const payload = {
      prompt: values.prompt.trim(),
      qtype: values.qtype,
      options,
      required: values.required,
      scope: values.scope,
      // applies_to only matters for per-person questions; default for invitee scope.
      applies_to: values.scope === "person" ? values.applies_to : "everyone",
      visibility,
      visibility_ref: visibility === "tier" ? values.tiers : [],
      sort_order: editing?.sort_order ?? questions.length,
    };
    setSaving(true);
    setError(null);
    try {
      if (editing) await adminApi.updateQuestion(editing.id, payload);
      else await adminApi.createQuestion(payload);
      setOpen(false);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(q: QuestionAdmin) {
    if (!window.confirm(`Delete the question “${q.prompt}”?`)) return;
    await adminApi.deleteQuestion(q.id);
    onChanged();
  }

  const set = <K extends keyof FormValues>(k: K, v: FormValues[K]) =>
    setValues((p) => ({ ...p, [k]: v }));

  // What this instance shows: a single scope when filtered, otherwise everything.
  const shown = scope === "person" ? personQs : scope === "invitee" ? inviteeQs : questions;
  const noun =
    scope === "person" ? "per-person" : scope === "invitee" ? "per-invitee" : "custom";

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Typography variant="h6">
          {shown.length} {noun} question{shown.length === 1 ? "" : "s"}
        </Typography>
        <Button startIcon={<AddIcon />} variant="contained" onClick={openAdd}>
          Add question
        </Button>
      </Box>

      {shown.length === 0 && (
        <Typography color="text.secondary">
          {scope === "person"
            ? "No per-person questions yet. Add one — it's asked of each attendee (e.g. dietary, a child's age)."
            : scope === "invitee"
              ? "No per-invitee questions yet. Add one — it's asked once for the party (e.g. how they know the couple, a song request)."
              : "No custom questions yet. Add one — it becomes a per-person or per-invitee field on the RSVP (e.g. dietary, a song request, a child's age)."}
        </Typography>
      )}

      {scope !== "invitee" && (
        <QuestionGroup
          title="Per person — asked of each attendee"
          subtitle="e.g. dietary, a child's age. Reorder within this group."
          group={personQs}
          scope="person"
          reorder={reorder}
          reordering={reordering}
          onEdit={openEdit}
          onRemove={remove}
        />
      )}
      {scope !== "person" && (
        <QuestionGroup
          title="Per invitee — asked once for the party"
          subtitle="e.g. how they know the couple, a song request. Reorder within this group."
          group={inviteeQs}
          scope="invitee"
          reorder={reorder}
          reordering={reordering}
          onEdit={openEdit}
          onRemove={remove}
        />
      )}

      <Dialog open={open} onClose={saving ? undefined : () => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editing ? "Edit question" : "Add question"}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Question prompt"
              value={values.prompt}
              onChange={(e) => set("prompt", e.target.value)}
              fullWidth
              autoFocus
            />
            <TextField
              label="Answer type"
              value={values.qtype}
              onChange={(e) => set("qtype", e.target.value)}
              select
              fullWidth
            >
              {QTYPES.map((t) => (
                <MenuItem key={t.value} value={t.value}>
                  {t.label}
                </MenuItem>
              ))}
            </TextField>
            {HAS_OPTIONS.has(values.qtype) && (
              <TextField
                label="Choices (one per line)"
                value={values.optionsText}
                onChange={(e) => set("optionsText", e.target.value)}
                multiline
                minRows={3}
                fullWidth
              />
            )}
            <TextField
              label="Asked how often?"
              value={values.scope}
              onChange={(e) => set("scope", e.target.value)}
              select
              fullWidth
              helperText="Per invitee = once for the party. Per person = for each attendee."
            >
              {SCOPES.map((sc) => (
                <MenuItem key={sc.value} value={sc.value}>
                  {sc.label}
                </MenuItem>
              ))}
            </TextField>
            {values.scope === "person" && (
              <TextField
                label="Applies to"
                value={values.applies_to}
                onChange={(e) => set("applies_to", e.target.value)}
                select
                fullWidth
                helperText="e.g. set an Age question to “Children only” + Required."
              >
                {APPLIES.map((a) => (
                  <MenuItem key={a.value} value={a.value}>
                    {a.label}
                  </MenuItem>
                ))}
              </TextField>
            )}
            <TextField
              label="Who sees this?"
              value={values.visibility}
              onChange={(e) => set("visibility", e.target.value)}
              select
              fullWidth
            >
              <MenuItem value="all">Everyone</MenuItem>
              <MenuItem value="tier">Only certain tiers</MenuItem>
            </TextField>
            {values.visibility === "tier" && (
              <TextField
                label="Tiers"
                value={values.tiers}
                onChange={(e) =>
                  set("tiers", (e.target.value as unknown as string[]) ?? [])
                }
                select
                SelectProps={{ multiple: true }}
                fullWidth
                helperText="Guests never see which tier they're in — this only filters who's asked."
              >
                {ALL_TIERS.map((t) => (
                  <MenuItem key={t} value={t}>
                    {t}
                  </MenuItem>
                ))}
              </TextField>
            )}
            <FormControlLabel
              control={
                <Checkbox
                  checked={values.required}
                  onChange={(e) => set("required", e.target.checked)}
                />
              }
              label="Required to submit RSVP"
            />
            {error && <Alert severity="error">{error}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={save} variant="contained" disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}

/** One scope group (per-person or per-invitee) with reorder-within-group controls. */
function QuestionGroup({
  title,
  subtitle,
  group,
  scope,
  reorder,
  reordering,
  onEdit,
  onRemove,
}: {
  title: string;
  subtitle: string;
  group: QuestionAdmin[];
  scope: "person" | "invitee";
  reorder: (scope: "person" | "invitee", index: number, dir: -1 | 1) => void;
  reordering: boolean;
  onEdit: (q: QuestionAdmin) => void;
  onRemove: (q: QuestionAdmin) => void;
}) {
  if (group.length === 0) return null;
  return (
    <Box>
      <Typography
        variant="overline"
        color="text.secondary"
        sx={{ display: "block", letterSpacing: "0.08em" }}
      >
        {title}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
        {subtitle}
      </Typography>
      <Stack spacing={1}>
        {group.map((q, i) => (
          <Card key={q.id} variant="outlined">
            <CardContent sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
              <Stack sx={{ pt: 0.25 }}>
                <IconButton
                  size="small"
                  disabled={i === 0 || reordering}
                  onClick={() => reorder(scope, i, -1)}
                  aria-label="Move up"
                >
                  <ArrowUpwardIcon fontSize="small" />
                </IconButton>
                <IconButton
                  size="small"
                  disabled={i === group.length - 1 || reordering}
                  onClick={() => reorder(scope, i, 1)}
                  aria-label="Move down"
                >
                  <ArrowDownwardIcon fontSize="small" />
                </IconButton>
              </Stack>
              <Box sx={{ flexGrow: 1 }}>
                <Typography fontWeight={600}>{q.prompt}</Typography>
                <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: "wrap" }} useFlexGap>
                  <Chip size="small" label={QTYPES.find((t) => t.value === q.qtype)?.label ?? q.qtype} />
                  {q.scope === "person" && q.applies_to !== "everyone" && (
                    <Chip size="small" color="secondary" label={q.applies_to} />
                  )}
                  {q.required && <Chip size="small" color="primary" label="Required" />}
                  {q.visibility !== "all" && (
                    <Chip size="small" variant="outlined" label={`Visibility: ${q.visibility}`} />
                  )}
                  {HAS_OPTIONS.has(q.qtype) && (
                    <Chip size="small" variant="outlined" label={`${q.options.length} options`} />
                  )}
                </Stack>
              </Box>
              <IconButton size="small" onClick={() => onEdit(q)}>
                <EditOutlinedIcon fontSize="small" />
              </IconButton>
              <IconButton size="small" onClick={() => onRemove(q)}>
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </CardContent>
          </Card>
        ))}
      </Stack>
    </Box>
  );
}
