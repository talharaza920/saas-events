"use client";

import { useMemo, useState } from "react";

import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import EventAvailableIcon from "@mui/icons-material/EventAvailable";
import LinkIcon from "@mui/icons-material/Link";
import MarkEmailReadOutlinedIcon from "@mui/icons-material/MarkEmailReadOutlined";
import PersonAddAlt1Icon from "@mui/icons-material/PersonAddAlt1";
import SendOutlinedIcon from "@mui/icons-material/SendOutlined";
import TuneIcon from "@mui/icons-material/Tune";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import ListItemText from "@mui/material/ListItemText";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import OutlinedInput from "@mui/material/OutlinedInput";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import type { Theme } from "@mui/material/styles";
import {
  DataGrid,
  GridToolbarContainer,
  GridToolbarDensitySelector,
  GridToolbarExport,
  type GridColDef,
  type GridRenderCellParams,
  type GridRowSelectionModel,
} from "@mui/x-data-grid";

import {
  adminApi,
  formatAnswer,
  inviteUrl,
  type AnswerAdmin,
  type AnswerValue,
  type CompanionAdmin,
  type AdminMe,
  type CompanionUpdate,
  type ContentAdmin,
  type GuestAdmin,
  type QuestionAdmin,
  type StoryArcAdmin,
} from "@/lib/adminApi";
import { DEFAULT_INVITE_MESSAGE } from "@/lib/content";

import { isAnswered } from "./AnswerField";
import { applyMultiSort, ColumnSettings, SortBar, useColumnPrefs, useMultiSort } from "./columnPrefs";
import CompanionFormDialog from "./CompanionFormDialog";
import GuestFormDialog, { personIncluded, type GuestFormValues } from "./GuestFormDialog";
import GuestsIntake from "./GuestsIntake";
import SheetPanel from "./SheetPanel";

/** Context for substituting the invite-message template (couple + venue/date/time). */
type MessageContext = {
  template: string;
  couple: string;
  venue: string;
  date: string;
  time: string;
};

/** Fill the message template's placeholders for one guest. */
function buildInviteMessage(g: GuestAdmin, ctx: MessageContext): string {
  const greeting = g.greeting_name || g.name || "there";
  return ctx.template
    .replaceAll("{greeting}", greeting)
    .replaceAll("{name}", g.name || greeting)
    .replaceAll("{link}", inviteUrl(g.invite_path))
    .replaceAll("{couple}", ctx.couple)
    .replaceAll("{venue}", ctx.venue)
    .replaceAll("{date}", ctx.date)
    .replaceAll("{time}", ctx.time);
}

const byOrder = (a: QuestionAdmin, b: QuestionAdmin) => a.sort_order - b.sort_order;

/** Person-scope questions asked of an adult — i.e. the primary AND the +1
 * (everyone / adults). */
function primaryQuestionsOf(questions: QuestionAdmin[]): QuestionAdmin[] {
  return questions
    .filter((q) => q.scope === "person" && (q.applies_to === "everyone" || q.applies_to === "adults"))
    .sort(byOrder);
}

/** Invitee-scope questions, asked once for the whole party. */
function inviteeQuestionsOf(questions: QuestionAdmin[]): QuestionAdmin[] {
  return questions.filter((q) => q.scope === "invitee").sort(byOrder);
}

/** Person-scope questions asked of a child (everyone / children). */
function childQuestionsOf(questions: QuestionAdmin[]): QuestionAdmin[] {
  return questions
    .filter((q) => q.scope === "person" && (q.applies_to === "everyone" || q.applies_to === "children"))
    .sort(byOrder);
}

const TIER_LABEL: Record<string, string> = {
  solo: "Solo",
  plus_one: "+1",
  plus_family: "+Family",
};

const STATUS_COLOR: Record<string, "success" | "error" | "warning" | "info" | "default"> = {
  attending: "success",
  declined: "error",
  invited: "info",
  pending: "warning",
};

const STATUS_LABEL: Record<string, string> = {
  attending: "Attending",
  declined: "Declined",
  invited: "Invited",
  pending: "Pending",
};

type Grouping = "invitee" | "person";
type Layout = "table" | "cards";

/** One person within a party (primary + each companion) — powers the split view.
 * `companion` is null for the primary (edited via GuestFormDialog) and the
 * underlying companion otherwise (so its row can be edited/removed directly).
 * `answers` are that person's answers (the primary's row carries the party
 * answers — invitee-scope + the primary's own). */
type PersonRow = {
  role: "Primary" | "Guest" | "Child";
  name: string;
  answers: AnswerAdmin[];
  companion: CompanionAdmin | null;
};

function personRows(g: GuestAdmin): PersonRow[] {
  const rows: PersonRow[] = [
    { role: "Primary", name: g.name, answers: g.answers ?? [], companion: null },
  ];
  if ((g.companions ?? []).length > 0) {
    // The guest has responded — show their actual RSVP party (each is editable).
    for (const c of g.companions ?? []) {
      const isChild = c.kind === "child";
      rows.push({
        role: isChild ? "Child" : "Guest",
        name: c.name ?? (isChild ? "Child" : "Guest"),
        answers: c.answers ?? [],
        companion: c,
      });
    }
  } else {
    // No RSVP yet — show the admin's pre-filled party (the +1/kids) so an imported or
    // seeded family is visible here too. `companion: null` (these aren't RSVP rows yet).
    for (const m of g.party_members ?? []) {
      const isChild = m.kind === "child";
      rows.push({
        role: isChild ? "Child" : "Guest",
        name: m.name || (isChild ? "Child" : "Guest"),
        answers: [],
        companion: null,
      });
    }
  }
  return rows;
}

/** A short one-line summary of the party by name, e.g. "May · Leo". Falls back to the
 * pre-filled party (admin/import seed) when the guest hasn't RSVP'd yet. */
function companionSummary(g: GuestAdmin): string {
  const src =
    (g.companions ?? []).length > 0
      ? (g.companions ?? []).map((c) => ({ kind: c.kind, name: c.name }))
      : g.party_members ?? [];
  return src.map((c) => c.name || (c.kind === "child" ? "Child" : "Guest")).join(" · ");
}

/** Compact "Prompt: value · Prompt: value" summary of a person's answers. */
function answersText(answers: AnswerAdmin[]): string {
  return answers
    .map((a) => ({ prompt: a.prompt, value: formatAnswer(a.value) }))
    .filter((a) => a.value)
    .map((a) => `${a.prompt}: ${a.value}`)
    .join(" · ");
}

function contactLine(g: GuestAdmin): string {
  return [g.email, g.phone].filter(Boolean).join(" · ");
}

// --- Multi-field filtering -------------------------------------------------
// MUI X DataGrid Community caps its built-in filter panel at a single rule, so
// we filter the guest list ourselves before it reaches any view. Each field is
// AND-combined with the others; values *within* a field are OR-combined (e.g.
// Side=Alex AND Status in {attending, pending}). Categorical fields are
// multi-select dropdowns; `q` is a free-text match over name/email/phone.
type GuestFilter = {
  q: string;
  side: string[];
  relationship: string[];
  group: string[];
  batch: string[];
  tier: string[];
  status: string[];
};

const EMPTY_FILTER: GuestFilter = {
  q: "",
  side: [],
  relationship: [],
  group: [],
  batch: [],
  tier: [],
  status: [],
};

const TIER_FILTER_OPTIONS = [
  { value: "solo", label: "Solo" },
  { value: "plus_one", label: "+1" },
  { value: "plus_family", label: "+Family" },
];
const STATUS_FILTER_OPTIONS = [
  { value: "attending", label: "Attending" },
  { value: "declined", label: "Declined" },
  { value: "invited", label: "Invited" },
  { value: "pending", label: "Pending" },
];

// Which filter controls appear in the bar — chosen via the gear menu (session
// state; resets on reload). Persisting this choice per owner is future scope.
type FilterField = "q" | "side" | "relationship" | "group" | "batch" | "tier" | "status";

const FILTER_FIELDS: { key: FilterField; label: string }[] = [
  { key: "q", label: "Search" },
  { key: "side", label: "Side" },
  { key: "relationship", label: "Relationship" },
  { key: "group", label: "Group" },
  { key: "batch", label: "Batch" },
  { key: "tier", label: "Tier" },
  { key: "status", label: "Status" },
];

const DEFAULT_VISIBLE_FIELDS: FilterField[] = FILTER_FIELDS.map((f) => f.key);

function activeFilterCount(f: GuestFilter): number {
  return (
    (f.q.trim() ? 1 : 0) +
    f.side.length +
    f.relationship.length +
    f.group.length +
    f.batch.length +
    f.tier.length +
    f.status.length
  );
}

function matchesFilter(g: GuestAdmin, f: GuestFilter): boolean {
  const q = f.q.trim().toLowerCase();
  if (q) {
    // Name, contacts, and companion (+1 / family / kids) names — so searching a
    // partner's name finds the invitee whose party they belong to.
    const companionNames = (g.companions ?? []).map((c) => c.name);
    const hay = [g.name, g.email, g.phone, ...companionNames]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    if (!hay.includes(q)) return false;
  }
  if (f.side.length && !f.side.includes(g.side ?? "")) return false;
  if (f.relationship.length && !f.relationship.includes(g.relationship ?? "")) return false;
  if (f.group.length && !f.group.includes(g.group_name ?? "")) return false;
  if (f.batch.length && !f.batch.includes(g.batch ?? "")) return false;
  if (f.tier.length && !f.tier.includes(g.invite_tier)) return false;
  if (f.status.length && !f.status.includes(g.rsvp_status)) return false;
  return true;
}

/** Sorted distinct non-empty values of a field across the guest list. */
function distinctValues(guests: GuestAdmin[], pick: (g: GuestAdmin) => string | null | undefined) {
  const set = new Set<string>();
  for (const g of guests) {
    const v = pick(g)?.trim();
    if (v) set.add(v);
  }
  return [...set].sort((a, b) => a.localeCompare(b)).map((v) => ({ value: v, label: v }));
}

export default function GuestsPanel({
  me,
  guests,
  arcs = [],
  questions = [],
  content,
  onChanged,
}: {
  me: AdminMe;
  guests: GuestAdmin[];
  arcs?: StoryArcAdmin[];
  questions?: QuestionAdmin[];
  content?: ContentAdmin;
  onChanged: () => void;
}) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<GuestAdmin | null>(null);
  const [editingCompanion, setEditingCompanion] = useState<{
    invitee: string;
    companion: CompanionAdmin;
  } | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [copiedMsg, setCopiedMsg] = useState<string | null>(null);

  // The per-guest invite message (template + wedding details for substitution).
  const messageCtx = useMemo<MessageContext>(() => {
    const cc = (content?.content ?? {}) as Record<string, unknown>;
    const ev = (content?.event_details ?? {}) as Record<string, unknown>;
    const str = (v: unknown) => (typeof v === "string" ? v : "");
    return {
      template: str(cc.invite_message) || DEFAULT_INVITE_MESSAGE,
      couple: content?.couple_names ?? "",
      venue: str(ev.venue),
      date: str(ev.date_display),
      time: str(ev.time_display),
    };
  }, [content]);
  const [grouping, setGrouping] = useState<Grouping>("invitee");
  // The wide List grid needs horizontal scrolling on a phone, so default to the
  // stacked Cards view there. `null` = "follow the screen" until the owner picks a
  // layout themselves, after which their choice sticks regardless of width.
  const isPhone = useMediaQuery((t: Theme) => t.breakpoints.down("sm"), { noSsr: true });
  const [layout, setLayout] = useState<Layout | null>(null);
  const effectiveLayout: Layout = layout ?? (isPhone ? "cards" : "table");
  const [filter, setFilter] = useState<GuestFilter>(EMPTY_FILTER);
  const [visibleFields, setVisibleFields] = useState<FilterField[]>(DEFAULT_VISIBLE_FIELDS);
  const primaryQuestions = useMemo(() => primaryQuestionsOf(questions), [questions]);
  const inviteeQuestions = useMemo(() => inviteeQuestionsOf(questions), [questions]);
  const childQuestions = useMemo(() => childQuestionsOf(questions), [questions]);

  // plus_family companion caps from content.rsvp.party (a disabled group → 0).
  const partyCaps = useMemo(() => {
    const cc = (content?.content ?? {}) as Record<string, unknown>;
    const rsvp = (cc.rsvp ?? {}) as Record<string, unknown>;
    const p = (rsvp.party ?? {}) as Record<string, unknown>;
    const num = (v: unknown, d: number) => (typeof v === "number" ? Math.max(0, Math.floor(v)) : d);
    const adultsOn = typeof p.adults_enabled === "boolean" ? p.adults_enabled : true;
    const kidsOn = typeof p.kids_enabled === "boolean" ? p.kids_enabled : true;
    return {
      maxAdults: adultsOn ? num(p.max_adults, 4) : 0,
      maxKids: kidsOn ? num(p.max_kids, 4) : 0,
    };
  }, [content]);

  const filteredGuests = useMemo(
    () => guests.filter((g) => matchesFilter(g, filter)),
    [guests, filter],
  );

  function openAdd() {
    setEditing(null);
    setDialogOpen(true);
  }
  function openEdit(g: GuestAdmin) {
    setEditing(g);
    setDialogOpen(true);
  }
  function openEditCompanion(invitee: string, companion: CompanionAdmin) {
    setEditingCompanion({ invitee, companion });
  }

  async function handleSubmit(values: GuestFormValues) {
    const tier = values.invite_tier;
    const allowAdult = tier !== "solo";
    const allowKids = tier === "plus_family";

    // Prefill party (the adults'/kids' names). Drop blank rows; backend clamps to tier.
    const party_members = [
      ...(allowAdult
        ? values.adults
            .filter((a) => a.name.trim())
            .map((a) => ({ kind: "adult", name: a.name.trim() }))
        : []),
      ...(allowKids
        ? values.children
            .filter((c) => c.name.trim())
            .map((c) => ({ kind: "child", name: c.name.trim() }))
        : []),
    ];
    const payload = {
      name: values.name.trim(),
      greeting_name: values.greeting_name.trim(),
      party_members,
      email: values.email.trim() || null,
      phone: values.phone.trim() || null,
      invite_tier: tier,
      side: values.side.trim() || null,
      relationship: values.relationship.trim() || null,
      group_name: values.group_name.trim() || null,
      batch: values.batch.trim() || null,
      expected_party_size:
        values.expected_party_size.trim() === "" ? null : Number(values.expected_party_size),
      invited: values.invited,
      // Tri-state override: null = default (all visible arcs), [] = hide the
      // story for this guest, non-empty = only those arcs.
      story_arc_ids:
        values.story_mode === "all"
          ? null
          : values.story_mode === "none"
            ? []
            : values.story_arc_ids,
    };
    if (!editing) {
      await adminApi.createGuest(payload);
      onChanged();
      return;
    }
    await adminApi.updateGuest(editing.id, payload);

    // Persist the RSVP. When attending, send the WHOLE party — the primary's own +
    // invitee-scope answers, plus each companion with its name and own answers.
    const pick = (qs: QuestionAdmin[], src: Record<string, AnswerValue>) =>
      qs.filter((q) => isAnswered(q, src[q.id])).map((q) => ({ question_id: q.id, value: src[q.id] }));
    if (values.rsvp_status === "attending") {
      const companions: { kind: string; name: string | null; answers: { question_id: string; value: AnswerValue }[] }[] = [];
      if (allowAdult) {
        for (const a of values.adults) {
          if (!personIncluded(a, primaryQuestions)) continue;
          companions.push({
            kind: "adult",
            name: a.name.trim() || null,
            answers: pick(primaryQuestions, a.answers),
          });
        }
      }
      if (allowKids) {
        for (const c of values.children) {
          if (!personIncluded(c, childQuestions)) continue;
          companions.push({ kind: "child", name: c.name.trim() || null, answers: pick(childQuestions, c.answers) });
        }
      }
      await adminApi.updateGuestRsvp(editing.id, {
        status: "attending",
        answers: pick([...primaryQuestions, ...inviteeQuestions], values.partyAnswers),
        companions,
      });
    } else {
      // Pending / declined: status only (declined clears the party server-side).
      await adminApi.updateGuestRsvp(editing.id, { status: values.rsvp_status });
    }
    onChanged();
  }

  async function handleDelete(g: GuestAdmin) {
    if (!window.confirm(`Remove ${g.name}? This also deletes their RSVP.`)) return;
    await adminApi.deleteGuest(g.id);
    onChanged();
  }

  // Bulk ops act on the current selection (invitee grid only). Status + delete are
  // the only bulk-editable attributes; everything else stays per-guest.
  async function handleBulkStatus(ids: string[], status: "attending" | "declined" | "invited" | "pending") {
    await adminApi.bulkSetRsvp(ids, status);
    onChanged();
  }

  // One-click Pending↔Invited flip for a single guest (the fast "I've sent it" toggle).
  async function handleToggleInvited(g: GuestAdmin) {
    const next = g.rsvp_status === "invited" ? "pending" : "invited";
    await adminApi.updateGuestRsvp(g.id, { status: next });
    onChanged();
  }

  async function handleBulkDelete(ids: string[]) {
    const n = ids.length;
    if (!window.confirm(`Remove ${n} guest${n === 1 ? "" : "s"}? This also deletes their RSVPs.`))
      return false;
    await adminApi.bulkDeleteGuests(ids);
    onChanged();
    return true;
  }

  async function handleCompanionSubmit(values: CompanionUpdate) {
    if (!editingCompanion) return;
    await adminApi.updateCompanion(editingCompanion.companion.id, values);
    onChanged();
  }

  async function handleCompanionDelete(invitee: string, companion: CompanionAdmin) {
    const who = companion.name || (companion.kind === "child" ? "this child" : "this guest");
    if (!window.confirm(`Remove ${who} from ${invitee}'s party?`)) return;
    await adminApi.deleteCompanion(companion.id);
    onChanged();
  }

  async function copyLink(path: string) {
    const url = inviteUrl(path);
    try {
      await navigator.clipboard.writeText(url);
      setCopied(path);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      window.prompt("Copy this invite link:", url);
    }
  }

  async function copyMessage(g: GuestAdmin) {
    const msg = buildInviteMessage(g, messageCtx);
    try {
      await navigator.clipboard.writeText(msg);
      setCopiedMsg(g.invite_path);
      setTimeout(() => setCopiedMsg(null), 1500);
    } catch {
      window.prompt("Copy this message:", msg);
    }
  }

  const copyBtn = (g: GuestAdmin) => (
    <Tooltip title={copied === g.invite_path ? "Copied!" : "Copy invite link"}>
      <IconButton size="small" onClick={() => copyLink(g.invite_path)}>
        <LinkIcon fontSize="small" />
      </IconButton>
    </Tooltip>
  );
  const copyMsgBtn = (g: GuestAdmin) => (
    <Tooltip title={copiedMsg === g.invite_path ? "Message copied!" : "Copy invite message"}>
      <IconButton size="small" onClick={() => copyMessage(g)}>
        <ChatBubbleOutlineIcon fontSize="small" />
      </IconButton>
    </Tooltip>
  );
  // Fast Pending↔Invited flip — shown only before a reply (pending/invited). Once a
  // guest has replied (attending/declined) the toggle is irrelevant, so it's hidden.
  const invitedToggleBtn = (g: GuestAdmin) => {
    if (g.rsvp_status !== "pending" && g.rsvp_status !== "invited") return null;
    const isInvited = g.rsvp_status === "invited";
    return (
      <Tooltip title={isInvited ? "Sent — mark as not sent" : "Mark invite as sent"}>
        <IconButton size="small" color={isInvited ? "info" : "default"} onClick={() => handleToggleInvited(g)}>
          {isInvited ? <MarkEmailReadOutlinedIcon fontSize="small" /> : <SendOutlinedIcon fontSize="small" />}
        </IconButton>
      </Tooltip>
    );
  };
  const editDeleteBtns = (g: GuestAdmin) => (
    <>
      <IconButton size="small" onClick={() => openEdit(g)}>
        <EditOutlinedIcon fontSize="small" />
      </IconButton>
      <IconButton size="small" onClick={() => handleDelete(g)}>
        <DeleteOutlineIcon fontSize="small" />
      </IconButton>
    </>
  );
  // Two-line action stack for a primary invitee: edit/delete on top, then copy
  // link + copy message below. Used in the By-invitee and By-person grids.
  // `display:flex` on each row stops the DataGrid cell's tall line-height from
  // inflating the rows (which would push the 2nd line out of the clipped cell).
  const primaryActions = (g: GuestAdmin) => (
    <Stack spacing={0} sx={{ height: "100%", justifyContent: "center" }}>
      <Box sx={{ display: "flex" }}>
        {editDeleteBtns(g)}
        {invitedToggleBtn(g)}
      </Box>
      <Box sx={{ display: "flex" }}>
        {copyBtn(g)}
        {copyMsgBtn(g)}
      </Box>
    </Stack>
  );
  // Edit/remove a companion person row (no link — only the primary carries one).
  const companionBtns = (invitee: string, c: CompanionAdmin) => (
    <>
      <IconButton size="small" onClick={() => openEditCompanion(invitee, c)}>
        <EditOutlinedIcon fontSize="small" />
      </IconButton>
      <IconButton size="small" onClick={() => handleCompanionDelete(invitee, c)}>
        <DeleteOutlineIcon fontSize="small" />
      </IconButton>
    </>
  );

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 2 }}>
        <Typography variant="h6">
          {activeFilterCount(filter) > 0
            ? `${filteredGuests.length} of ${guests.length} guests`
            : `${guests.length} guests`}
        </Typography>
        <Stack direction="row" spacing={2} alignItems="center" useFlexGap flexWrap="wrap">
          <ToggleButtonGroup
            size="small"
            exclusive
            value={grouping}
            onChange={(_, v: Grouping | null) => v && setGrouping(v)}
          >
            <ToggleButton value="invitee">By invitee</ToggleButton>
            <ToggleButton value="person">By person</ToggleButton>
          </ToggleButtonGroup>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={effectiveLayout}
            onChange={(_, v: Layout | null) => v && setLayout(v)}
          >
            <ToggleButton value="table">List</ToggleButton>
            <ToggleButton value="cards">Cards</ToggleButton>
          </ToggleButtonGroup>
          <Button startIcon={<PersonAddAlt1Icon />} variant="contained" onClick={openAdd}>
            Add guest
          </Button>
        </Stack>
      </Box>

      {/* 8.5c: ONE way in for a list, whatever shape it's in. GuestsIntake sends
          a real spreadsheet to the deterministic importer (a parser — no model,
          no credits) and everything else to the assistant. */}
      <GuestsIntake me={me} onChanged={onChanged} />

      <SheetPanel />

      {guests.length > 0 && (
        <GuestFilterBar
          guests={guests}
          filter={filter}
          onChange={setFilter}
          visibleFields={visibleFields}
          onVisibleChange={setVisibleFields}
        />
      )}

      {guests.length === 0 ? (
        <Typography color="text.secondary" sx={{ py: 2 }}>
          No guests yet. Add your first guest to generate an invite link.
        </Typography>
      ) : filteredGuests.length === 0 ? (
        <Typography color="text.secondary" sx={{ py: 2 }}>
          No guests match the current filters.
        </Typography>
      ) : effectiveLayout === "cards" ? (
        <GuestCards
          guests={filteredGuests}
          copyBtn={copyBtn}
          copyMsgBtn={copyMsgBtn}
          editDeleteBtns={editDeleteBtns}
          invitedToggleBtn={invitedToggleBtn}
          companionBtns={companionBtns}
        />
      ) : grouping === "invitee" ? (
        <InviteeGrid
          guests={filteredGuests}
          primaryActions={primaryActions}
          onBulkStatus={handleBulkStatus}
          onBulkDelete={handleBulkDelete}
        />
      ) : (
        <PersonGrid
          guests={filteredGuests}
          questions={questions}
          primaryActions={primaryActions}
          companionBtns={companionBtns}
        />
      )}

      {dialogOpen && (
        <GuestFormDialog
          key={editing?.id ?? "new"}
          guest={editing}
          arcs={arcs}
          primaryQuestions={primaryQuestions}
          inviteeQuestions={inviteeQuestions}
          childQuestions={childQuestions}
          maxAdults={partyCaps.maxAdults}
          maxKids={partyCaps.maxKids}
          onClose={() => setDialogOpen(false)}
          onSubmit={handleSubmit}
        />
      )}
      {editingCompanion && (
        <CompanionFormDialog
          key={editingCompanion.companion.id}
          companion={editingCompanion.companion}
          invitee={editingCompanion.invitee}
          questions={questions}
          onClose={() => setEditingCompanion(null)}
          onSubmit={handleCompanionSubmit}
        />
      )}
    </Stack>
  );
}

// --- Filter bar: one dropdown per field, AND-combined across fields ---------
// A multi-select where the selected values OR together. Empty selection = no
// constraint on that field.
function MultiSelectFilter({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string[];
  options: { value: string; label: string }[];
  onChange: (next: string[]) => void;
}) {
  const labelOf = (v: string) => options.find((o) => o.value === v)?.label ?? v;
  return (
    <FormControl size="small" sx={{ minWidth: 150 }}>
      <InputLabel>{label}</InputLabel>
      <Select
        multiple
        value={value}
        onChange={(e) =>
          onChange(typeof e.target.value === "string" ? e.target.value.split(",") : e.target.value)
        }
        input={<OutlinedInput label={label} />}
        renderValue={(sel) => (sel as string[]).map(labelOf).join(", ")}
      >
        {options.map((o) => (
          <MenuItem key={o.value} value={o.value}>
            <Checkbox size="small" checked={value.includes(o.value)} sx={{ py: 0 }} />
            <ListItemText primary={o.label} />
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}

function GuestFilterBar({
  guests,
  filter,
  onChange,
  visibleFields,
  onVisibleChange,
}: {
  guests: GuestAdmin[];
  filter: GuestFilter;
  onChange: (f: GuestFilter) => void;
  visibleFields: FilterField[];
  onVisibleChange: (fields: FilterField[]) => void;
}) {
  const sideOptions = useMemo(() => distinctValues(guests, (g) => g.side), [guests]);
  const relOptions = useMemo(() => distinctValues(guests, (g) => g.relationship), [guests]);
  const groupOptions = useMemo(() => distinctValues(guests, (g) => g.group_name), [guests]);
  const batchOptions = useMemo(() => distinctValues(guests, (g) => g.batch), [guests]);
  const active = activeFilterCount(filter);
  const set = (patch: Partial<GuestFilter>) => onChange({ ...filter, ...patch });

  const [gearAnchor, setGearAnchor] = useState<HTMLElement | null>(null);
  const isVisible = (key: FilterField) => visibleFields.includes(key);

  // Toggle a field on/off in the bar. Hiding a field also clears its active
  // value so a now-invisible filter can't keep silently narrowing the list.
  function toggleField(key: FilterField) {
    if (isVisible(key)) {
      onVisibleChange(visibleFields.filter((k) => k !== key));
      if (key === "q") set({ q: "" });
      else set({ [key]: [] });
    } else {
      // Keep the canonical FILTER_FIELDS order regardless of click order.
      const next = FILTER_FIELDS.map((f) => f.key).filter(
        (k) => k === key || visibleFields.includes(k),
      );
      onVisibleChange(next);
    }
  }

  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack direction="row" spacing={1.5} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
        {isVisible("q") && (
          <TextField
            size="small"
            label="Search"
            placeholder="Name, email, phone"
            value={filter.q}
            onChange={(e) => set({ q: e.target.value })}
            sx={{ minWidth: 200 }}
          />
        )}
        {isVisible("side") && sideOptions.length > 0 && (
          <MultiSelectFilter
            label="Side"
            value={filter.side}
            options={sideOptions}
            onChange={(v) => set({ side: v })}
          />
        )}
        {isVisible("relationship") && relOptions.length > 0 && (
          <MultiSelectFilter
            label="Relationship"
            value={filter.relationship}
            options={relOptions}
            onChange={(v) => set({ relationship: v })}
          />
        )}
        {isVisible("group") && groupOptions.length > 0 && (
          <MultiSelectFilter
            label="Group"
            value={filter.group}
            options={groupOptions}
            onChange={(v) => set({ group: v })}
          />
        )}
        {isVisible("batch") && batchOptions.length > 0 && (
          <MultiSelectFilter
            label="Batch"
            value={filter.batch}
            options={batchOptions}
            onChange={(v) => set({ batch: v })}
          />
        )}
        {isVisible("tier") && (
          <MultiSelectFilter
            label="Tier"
            value={filter.tier}
            options={TIER_FILTER_OPTIONS}
            onChange={(v) => set({ tier: v })}
          />
        )}
        {isVisible("status") && (
          <MultiSelectFilter
            label="Status"
            value={filter.status}
            options={STATUS_FILTER_OPTIONS}
            onChange={(v) => set({ status: v })}
          />
        )}

        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ ml: "auto" }}>
          {active > 0 && (
            <Button size="small" color="inherit" onClick={() => onChange(EMPTY_FILTER)}>
              Clear filters
            </Button>
          )}
          <Tooltip title="Choose filters">
            <IconButton size="small" onClick={(e) => setGearAnchor(e.currentTarget)}>
              <TuneIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>

        <Menu anchorEl={gearAnchor} open={Boolean(gearAnchor)} onClose={() => setGearAnchor(null)}>
          <Typography variant="caption" color="text.secondary" sx={{ px: 2, py: 0.5, display: "block" }}>
            Show filters
          </Typography>
          {FILTER_FIELDS.map((f) => (
            <MenuItem key={f.key} dense onClick={() => toggleField(f.key)}>
              <Checkbox size="small" checked={isVisible(f.key)} sx={{ py: 0 }} />
              <ListItemText primary={f.label} />
            </MenuItem>
          ))}
        </Menu>
      </Stack>
    </Paper>
  );
}

// Grid toolbar without the built-in quick-filter search (our filter bar owns
// search) and without the built-in Columns button — our own ColumnSettings
// control owns column order + show/hide. Keeps Density / Export.
function GridToolbarNoSearch() {
  return (
    <GridToolbarContainer>
      <GridToolbarDensitySelector />
      <GridToolbarExport />
    </GridToolbarContainer>
  );
}

// --- Combined view: one row per invitee (party), as a sortable/filterable grid -
// Built on MUI X DataGrid (Community): every column sorts on click and filters via
// the toolbar's filter panel; the checkbox column drives the bulk-action bar.
type BulkStatus = "attending" | "declined" | "invited" | "pending";
const STATUS_OPTIONS: { value: BulkStatus; label: string }[] = [
  { value: "attending", label: "Attending" },
  { value: "declined", label: "Declined" },
  { value: "invited", label: "Invited (sent)" },
  { value: "pending", label: "Pending" },
];

function InviteeGrid({
  guests,
  primaryActions,
  onBulkStatus,
  onBulkDelete,
}: {
  guests: GuestAdmin[];
  primaryActions: (g: GuestAdmin) => React.ReactNode;
  onBulkStatus: (ids: string[], status: BulkStatus) => Promise<void>;
  onBulkDelete: (ids: string[]) => Promise<boolean>;
}) {
  const [selection, setSelection] = useState<GridRowSelectionModel>({
    type: "include",
    ids: new Set(),
  });
  const [statusAnchor, setStatusAnchor] = useState<HTMLElement | null>(null);
  const [busy, setBusy] = useState(false);

  const allIds = useMemo(() => guests.map((g) => g.id), [guests]);
  // DataGrid's "select all" yields an `exclude` model (everything except `ids`);
  // resolve either shape to the concrete list of selected guest ids.
  const selectedIds = useMemo(() => {
    if (selection.type === "include") return [...selection.ids].map(String);
    const ex = new Set([...selection.ids].map(String));
    return allIds.filter((id) => !ex.has(id));
  }, [selection, allIds]);

  const clearSelection = () => setSelection({ type: "include", ids: new Set() });

  async function runBulkStatus(status: BulkStatus) {
    setStatusAnchor(null);
    setBusy(true);
    try {
      await onBulkStatus(selectedIds, status);
      clearSelection();
    } finally {
      setBusy(false);
    }
  }

  async function runBulkDelete() {
    setBusy(true);
    try {
      if (await onBulkDelete(selectedIds)) clearSelection();
    } finally {
      setBusy(false);
    }
  }

  const rows = useMemo(
    () =>
      guests.map((g) => ({
        id: g.id,
        name: g.name,
        greeting: g.greeting_name ?? "",
        contact: contactLine(g),
        side: g.side ?? "",
        relationship: g.relationship ?? "",
        group: g.group_name ?? "",
        batch: g.batch ?? "",
        tier: TIER_LABEL[g.invite_tier] ?? g.invite_tier,
        status: g.rsvp_status,
        expected: g.expected_party_size,
        party: g.party_size,
        companions: companionSummary(g),
        answers: answersText(g.answers ?? []),
        _g: g,
      })),
    [guests],
  );

  const columns: GridColDef<(typeof rows)[number]>[] = [
    {
      field: "actions",
      headerName: "Actions",
      width: 124,
      sortable: false,
      filterable: false,
      disableColumnMenu: true,
      renderCell: (p: GridRenderCellParams<(typeof rows)[number]>) => primaryActions(p.row._g),
    },
    { field: "name", headerName: "Invitee", flex: 1.2, minWidth: 140 },
    { field: "greeting", headerName: "Greeting", flex: 1, minWidth: 130 },
    { field: "contact", headerName: "Contact", flex: 1.2, minWidth: 160 },
    { field: "side", headerName: "Side", width: 110 },
    { field: "relationship", headerName: "Relationship", width: 140 },
    { field: "group", headerName: "Group", width: 140 },
    { field: "batch", headerName: "Batch", width: 110 },
    { field: "tier", headerName: "Tier", width: 100, renderCell: (p) => <Chip size="small" label={p.value} /> },
    {
      field: "status",
      headerName: "Status",
      width: 120,
      renderCell: (p) => (
        <Chip
          size="small"
          color={STATUS_COLOR[p.value as string] ?? "default"}
          label={STATUS_LABEL[p.value as string] ?? p.value}
        />
      ),
    },
    { field: "expected", headerName: "Expected", type: "number", width: 95 },
    { field: "party", headerName: "Actual", type: "number", width: 80 },
    { field: "companions", headerName: "Coming with", flex: 1, minWidth: 130 },
    { field: "answers", headerName: "Answers", flex: 1.5, minWidth: 160 },
  ];

  const prefs = useColumnPrefs("guestcols:invitee", columns);
  const sort = useMultiSort("guestcols:invitee");
  const sortedRows = useMemo(() => applyMultiSort(rows, sort.model), [rows, sort.model]);

  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 2, mb: 0.5 }}>
        <SortBar sort={sort} columns={columns} />
        <ColumnSettings prefs={prefs} />
      </Box>
      {selectedIds.length > 0 && (
        <Paper
          variant="outlined"
          sx={{ p: 1, mb: 1, display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}
        >
          <Typography variant="body2" sx={{ fontWeight: 600, mx: 1 }}>
            {selectedIds.length} selected
          </Typography>
          <Button
            size="small"
            startIcon={<EventAvailableIcon />}
            disabled={busy}
            onClick={(e) => setStatusAnchor(e.currentTarget)}
          >
            Set status
          </Button>
          <Menu anchorEl={statusAnchor} open={Boolean(statusAnchor)} onClose={() => setStatusAnchor(null)}>
            {STATUS_OPTIONS.map((o) => (
              <MenuItem key={o.value} onClick={() => runBulkStatus(o.value)}>
                {o.label}
              </MenuItem>
            ))}
          </Menu>
          <Button
            size="small"
            color="error"
            startIcon={<DeleteOutlineIcon />}
            disabled={busy}
            onClick={runBulkDelete}
          >
            Delete
          </Button>
          <Button size="small" color="inherit" disabled={busy} onClick={clearSelection}>
            Clear
          </Button>
        </Paper>
      )}
      <DataGrid
        rows={sortedRows}
        columns={prefs.orderedColumns}
        columnVisibilityModel={prefs.visibilityModel}
        onColumnVisibilityModelChange={prefs.setVisibilityModel}
        // Custom multi-sort: the grid's own (single-column-only in Community) sort is
        // disabled; clicking a header drives our JS multi-sort (Shift-click = add level).
        disableColumnSorting
        onColumnHeaderClick={(p, e) => {
          if (p.field === "actions" || p.field === "__check__") return;
          sort.toggle(p.field, e.shiftKey);
        }}
        checkboxSelection
        disableRowSelectionOnClick
        rowSelectionModel={selection}
        onRowSelectionModelChange={(m) => setSelection(m)}
        showToolbar
        slots={{ toolbar: GridToolbarNoSearch }}
        density="compact"
        // Taller rows so the two-line action stack (edit/delete · link/message) fits.
        // getRowHeight is authoritative (the rowHeight prop is overridden by density).
        getRowHeight={() => 64}
        pageSizeOptions={[25, 50, 100]}
        initialState={{
          pagination: { paginationModel: { pageSize: 25, page: 0 } },
        }}
        // Cap the height so the grid scrolls internally — its column header row
        // then stays pinned (sticky) while the rows scroll under it.
        sx={{
          border: 0,
          maxHeight: "calc(100vh - 220px)",
          // Native sort is off (we drive a custom multi-sort), so cue clickable headers.
          "& .MuiDataGrid-columnHeader--sortable, & .MuiDataGrid-columnHeaderTitleContainer": { cursor: "pointer" },
        }}
      />
    </Box>
  );
}

// --- Split view: one row per person (primary + each companion) -------------
// Same DataGrid as the invitee view (sort / filter / column show-hide / sticky
// header). No checkbox selection here: the bulk actions are party-level, which
// don't map onto a mix of primary + companion rows. Party-level fields
// (Contact/Side/Relationship/Group/Batch/Tier/Link) show on the primary row only.
function PersonGrid({
  guests,
  questions,
  primaryActions,
  companionBtns,
}: {
  guests: GuestAdmin[];
  questions: QuestionAdmin[];
  primaryActions: (g: GuestAdmin) => React.ReactNode;
  companionBtns: (invitee: string, c: CompanionAdmin) => React.ReactNode;
}) {
  // One column per question (Dietary, Age, song…), each in question order, so a
  // person's own answer reads as its own cell instead of the lumped "Details".
  const orderedQuestions = useMemo(() => [...questions].sort(byOrder), [questions]);

  const rows = useMemo(
    () =>
      guests.flatMap((g) =>
        personRows(g).map((p, i) => {
          const primary = p.role === "Primary";
          // Flatten this person's answers onto `q_<id>` fields for the per-question columns.
          const ans: Record<string, string> = {};
          for (const a of p.answers) ans[`q_${a.question_id}`] = formatAnswer(a.value);
          return {
            id: `${g.id}-${i}`,
            invitee: g.name,
            role: p.role,
            person: p.name,
            greeting: primary ? g.greeting_name ?? "" : "",
            contact: primary ? contactLine(g) : "",
            side: primary ? g.side ?? "" : "",
            relationship: primary ? g.relationship ?? "" : "",
            group: primary ? g.group_name ?? "" : "",
            batch: primary ? g.batch ?? "" : "",
            tier: primary ? TIER_LABEL[g.invite_tier] ?? g.invite_tier : "",
            status: g.rsvp_status,
            ...ans,
            _g: g,
            _companion: p.companion,
            _primary: primary,
          };
        }),
      ),
    [guests],
  );

  const questionColumns: GridColDef<(typeof rows)[number]>[] = orderedQuestions.map((q) => ({
    field: `q_${q.id}`,
    headerName: q.prompt,
    flex: 1,
    minWidth: 130,
  }));

  const columns: GridColDef<(typeof rows)[number]>[] = [
    {
      field: "actions",
      headerName: "Actions",
      width: 124,
      sortable: false,
      filterable: false,
      disableColumnMenu: true,
      renderCell: (p) =>
        p.row._primary
          ? primaryActions(p.row._g)
          : p.row._companion
            ? companionBtns(p.row._g.name, p.row._companion)
            : null,
    },
    {
      field: "invitee",
      headerName: "Invitee",
      flex: 1,
      minWidth: 130,
      renderCell: (p) => (
        <Box component="span" sx={{ color: p.row._primary ? "text.primary" : "text.secondary" }}>
          {p.value}
        </Box>
      ),
    },
    {
      field: "role",
      headerName: "Person",
      width: 100,
      renderCell: (p) => (
        <Chip size="small" variant={p.row._primary ? "filled" : "outlined"} label={p.value} />
      ),
    },
    { field: "person", headerName: "Name", flex: 1, minWidth: 120 },
    // Guest-specific answers, one column each (Dietary, Age, song choice, …).
    ...questionColumns,
    { field: "greeting", headerName: "Greeting", flex: 1, minWidth: 130 },
    { field: "contact", headerName: "Contact", flex: 1.2, minWidth: 150 },
    { field: "side", headerName: "Side", width: 110 },
    { field: "relationship", headerName: "Relationship", width: 140 },
    { field: "group", headerName: "Group", width: 140 },
    { field: "batch", headerName: "Batch", width: 110 },
    {
      field: "tier",
      headerName: "Tier",
      width: 100,
      renderCell: (p) => (p.value ? <Chip size="small" label={p.value} /> : null),
    },
    {
      field: "status",
      headerName: "Status",
      width: 120,
      renderCell: (p) => (
        <Chip
          size="small"
          variant={p.row._primary ? "filled" : "outlined"}
          color={STATUS_COLOR[p.value as string] ?? "default"}
          label={STATUS_LABEL[p.value as string] ?? p.value}
        />
      ),
    },
  ];

  const prefs = useColumnPrefs("guestcols:person", columns);
  const sort = useMultiSort("guestcols:person");
  const sortedRows = useMemo(() => applyMultiSort(rows, sort.model), [rows, sort.model]);

  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 2, mb: 0.5 }}>
        <SortBar sort={sort} columns={columns} />
        <ColumnSettings prefs={prefs} />
      </Box>
      <DataGrid
        rows={sortedRows}
        columns={prefs.orderedColumns}
        columnVisibilityModel={prefs.visibilityModel}
        onColumnVisibilityModelChange={prefs.setVisibilityModel}
        disableColumnSorting
        onColumnHeaderClick={(p, e) => {
          if (p.field === "actions") return;
          sort.toggle(p.field, e.shiftKey);
        }}
        showToolbar
        slots={{ toolbar: GridToolbarNoSearch }}
        density="compact"
        // Primary rows carry the two-line action stack (edit/delete · link/message);
        // companion rows are single-line, so give them the compact height.
        getRowHeight={(p) => (p.model._primary ? 62 : 40)}
        pageSizeOptions={[25, 50, 100]}
        initialState={{
          pagination: { paginationModel: { pageSize: 25, page: 0 } },
        }}
        sx={{
          border: 0,
          maxHeight: "calc(100vh - 220px)",
          // Native sort is off (we drive a custom multi-sort), so cue clickable headers.
          "& .MuiDataGrid-columnHeader--sortable, & .MuiDataGrid-columnHeaderTitleContainer": { cursor: "pointer" },
        }}
      />
    </Box>
  );
}

// --- Card view: one card per invitee, with the full party + answers inside -
function GuestCards({
  guests,
  copyBtn,
  copyMsgBtn,
  editDeleteBtns,
  invitedToggleBtn,
  companionBtns,
}: {
  guests: GuestAdmin[];
  copyBtn: (g: GuestAdmin) => React.ReactNode;
  copyMsgBtn: (g: GuestAdmin) => React.ReactNode;
  editDeleteBtns: (g: GuestAdmin) => React.ReactNode;
  invitedToggleBtn: (g: GuestAdmin) => React.ReactNode;
  companionBtns: (invitee: string, c: CompanionAdmin) => React.ReactNode;
}) {
  return (
    <Box
      sx={{
        display: "grid",
        gap: 2,
        gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(3, 1fr)" },
      }}
    >
      {guests.map((g) => {
        const rows = personRows(g);
        return (
          <Card key={g.id} variant="outlined">
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                <Box>
                  <Typography sx={{ fontWeight: 700 }}>{g.name}</Typography>
                  {contactLine(g) && (
                    <Typography variant="caption" color="text.secondary">
                      {contactLine(g)}
                    </Typography>
                  )}
                </Box>
                <Box sx={{ flexShrink: 0 }}>
                  {copyBtn(g)}
                  {copyMsgBtn(g)}
                  {editDeleteBtns(g)}
                  {invitedToggleBtn(g)}
                </Box>
              </Stack>

              <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                <Chip size="small" label={TIER_LABEL[g.invite_tier] ?? g.invite_tier} />
                <Chip size="small" color={STATUS_COLOR[g.rsvp_status] ?? "default"} label={STATUS_LABEL[g.rsvp_status] ?? g.rsvp_status} />
                {g.expected_party_size != null && (
                  <Chip size="small" variant="outlined" label={`Est. ${g.expected_party_size}`} />
                )}
                {g.party_size > 0 && <Chip size="small" variant="outlined" label={`Party of ${g.party_size}`} />}
              </Stack>

              {g.rsvp_status === "attending" && (
                <>
                  <Divider sx={{ my: 1.5 }} />
                  <Stack spacing={1}>
                    {rows.map((p, i) => {
                      const detail = answersText(p.answers);
                      return (
                        <Box key={i}>
                          <Stack direction="row" spacing={1} alignItems="center" useFlexGap sx={{ flexWrap: "wrap" }}>
                            <Typography variant="body2" sx={{ fontWeight: p.role === "Primary" ? 600 : 400 }}>
                              {p.name}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {p.role}
                            </Typography>
                            {p.companion && (
                              <Box sx={{ ml: "auto" }}>{companionBtns(g.name, p.companion)}</Box>
                            )}
                          </Stack>
                          {detail && (
                            <Typography variant="caption" color="text.secondary">
                              {detail}
                            </Typography>
                          )}
                        </Box>
                      );
                    })}
                  </Stack>
                </>
              )}
            </CardContent>
          </Card>
        );
      })}
    </Box>
  );
}
