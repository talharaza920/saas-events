"use client";

import { useState } from "react";

import AddIcon from "@mui/icons-material/Add";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import DeleteIcon from "@mui/icons-material/Delete";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import dayjs, { type Dayjs } from "dayjs";

import { type ContentAdmin } from "@/lib/adminApi";
import { DEFAULT_INVITE_MESSAGE, defaultDayCells, LANDING_DEFAULTS } from "@/lib/content";
import type { BrandIconMode, DayCell } from "@/lib/content";
import { defaultThemeConfig } from "@/theme/defaultThemeConfig";
import type { ThemeColors } from "@/theme/types";

import Ico, { ICO_NAMES } from "../invite/brand/Ico";
import ImageUpload from "./ImageUpload";
import RichTextField from "./RichTextField";
import { rec, s, strList, SectionCard } from "./sectionKit";

// Loose-object helpers (`rec`/`s`/`strList`) and `SectionCard` live in
// ./sectionKit — shared with RsvpPanel. The RSVP sections (and their
// RSVP-only helpers: fillMap / humanize / StringMapEditor / button fields)
// now live in RsvpPanel.

/** Editor for the day-card detail cells: a reorderable list, each row an icon
 * picker + label/value/sub fields + on-off and a "links to Maps" toggle. */
function DayCellsEditor({
  cells,
  onUpdate,
  onMove,
  onRemove,
  onAdd,
}: {
  cells: DayCell[];
  onUpdate: (i: number, patch: Partial<DayCell>) => void;
  onMove: (i: number, dir: number) => void;
  onRemove: (i: number) => void;
  onAdd: () => void;
}) {
  return (
    <>
      <Box>
        <Typography variant="subtitle2" color="text.secondary">Detail cells</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
          Shown under the banner — up to 4 across on desktop, 2×2 on phones. Switch any off to hide it.
        </Typography>
      </Box>
      <Stack spacing={2}>
        {cells.map((cell, i) => (
          <Box key={i} sx={{ border: "1.5px solid", borderColor: "divider", borderRadius: 2, p: 2, opacity: cell.enabled ? 1 : 0.6 }}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.5 }}>
              <Switch checked={cell.enabled} onChange={(e) => onUpdate(i, { enabled: e.target.checked })} />
              <TextField
                select
                size="small"
                label="Icon"
                value={(ICO_NAMES as string[]).includes(cell.icon) ? cell.icon : "info"}
                onChange={(e) => onUpdate(i, { icon: e.target.value })}
                sx={{ minWidth: 132 }}
              >
                {ICO_NAMES.map((n) => (
                  <MenuItem key={n} value={n}>
                    <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                      <Box sx={{ color: "primary.dark", display: "flex" }}>
                        <Ico name={n} size={18} />
                      </Box>
                      <span>{n}</span>
                    </Stack>
                  </MenuItem>
                ))}
              </TextField>
              <Box sx={{ flex: 1 }} />
              <IconButton size="small" onClick={() => onMove(i, -1)} disabled={i === 0} aria-label="Move up">
                <ArrowUpwardIcon fontSize="small" />
              </IconButton>
              <IconButton size="small" onClick={() => onMove(i, 1)} disabled={i === cells.length - 1} aria-label="Move down">
                <ArrowDownwardIcon fontSize="small" />
              </IconButton>
              <IconButton size="small" color="error" onClick={() => onRemove(i)} aria-label="Remove cell">
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Stack>
            <Stack spacing={1.5}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                <TextField label="Label" size="small" value={cell.label} onChange={(e) => onUpdate(i, { label: e.target.value })} fullWidth />
                <TextField label="Value" size="small" value={cell.value} onChange={(e) => onUpdate(i, { value: e.target.value })} fullWidth />
              </Stack>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ alignItems: { sm: "center" } }}>
                <TextField label="Sub-line (optional)" size="small" value={cell.sub ?? ""} onChange={(e) => onUpdate(i, { sub: e.target.value })} fullWidth />
                <FormControlLabel
                  sx={{ whiteSpace: "nowrap", m: 0 }}
                  control={<Switch checked={!!cell.map_link} onChange={(e) => onUpdate(i, { map_link: e.target.checked })} />}
                  label="Links to Maps"
                />
              </Stack>
            </Stack>
          </Box>
        ))}
      </Stack>
      <Box>
        <Button startIcon={<AddIcon />} onClick={onAdd} variant="outlined" size="small">
          Add cell
        </Button>
      </Box>
    </>
  );
}

/** All themeable color token names + their default hex (for swatch previews). */
const COLOR_TOKENS = Object.keys(defaultThemeConfig.colors) as (keyof ThemeColors)[];

/** True for our named theme tokens; anything else (e.g. "#ff7a00") is a custom colour. */
function isColorToken(v: string): v is keyof ThemeColors {
  return (COLOR_TOKENS as string[]).includes(v);
}

/** A small round colour preview shown inside the picker chips. */
function Swatch({ color }: { color: string }) {
  return (
    <Box
      component="span"
      sx={{
        width: 18,
        height: 18,
        borderRadius: "50%",
        bgcolor: color,
        border: "1px solid rgba(0,0,0,0.2)",
      }}
    />
  );
}

/** Pick theme color tokens (toggle chips) and/or add custom hex colours. */
function TokenSwatchPicker({
  selected,
  onChange,
}: {
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const [custom, setCustom] = useState("#d8c4ff");
  const toggle = (token: string) =>
    onChange(selected.includes(token) ? selected.filter((t) => t !== token) : [...selected, token]);
  const remove = (value: string) => onChange(selected.filter((t) => t !== value));
  const addCustom = () => {
    const hex = custom.trim().toLowerCase();
    if (/^#([0-9a-f]{3}|[0-9a-f]{6})$/.test(hex) && !selected.includes(hex)) {
      onChange([...selected, hex]);
    }
  };
  // Custom (non-token) colours already chosen, rendered as removable chips.
  const customSelected = selected.filter((v) => !isColorToken(v));
  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, alignItems: "center" }}>
      {COLOR_TOKENS.map((token) => {
        const active = selected.includes(token);
        return (
          <Chip
            key={token}
            label={token}
            onClick={() => toggle(token)}
            variant={active ? "filled" : "outlined"}
            color={active ? "primary" : "default"}
            avatar={<Swatch color={defaultThemeConfig.colors[token]} />}
          />
        );
      })}
      {customSelected.map((hex) => (
        <Chip
          key={hex}
          label={hex}
          onDelete={() => remove(hex)}
          variant="filled"
          color="primary"
          avatar={<Swatch color={hex} />}
        />
      ))}
      {/* Add a custom colour: native picker → hex (also editable), then "Add colour". */}
      <Stack direction="row" spacing={1} alignItems="center" sx={{ width: "100%", mt: 1 }}>
        <Box
          component="input"
          type="color"
          aria-label="Pick a custom colour"
          value={/^#[0-9a-f]{6}$/i.test(custom) ? custom : "#d8c4ff"}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCustom(e.target.value)}
          sx={{
            width: 38,
            height: 38,
            p: 0,
            borderRadius: 1,
            border: "1px solid rgba(0,0,0,0.2)",
            bgcolor: "transparent",
            cursor: "pointer",
          }}
        />
        <TextField
          size="small"
          label="Hex"
          placeholder="#rrggbb"
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addCustom();
            }
          }}
          sx={{ width: 130 }}
        />
        <Button size="small" startIcon={<AddIcon />} onClick={addCustom}>
          Add colour
        </Button>
      </Stack>
    </Box>
  );
}

// ===========================================================================
// The panel. Each section owns its draft; the backend deep-merges partials.
// ===========================================================================
export default function DetailsPanel({
  content,
  sides,
  onChanged,
}: {
  content: ContentAdmin;
  // Distinct guest sides (e.g. ["Sam", "Alex"]) for the per-side capacity editor.
  sides: string[];
  onChanged: () => void | Promise<void>;
}) {
  const c = rec(content.content);
  const ev = rec(content.event_details);

  // --- Capacity (people) — venue ceiling + optional per-side ceilings -------
  const cap0 = rec(ev.capacity);
  const capBySide0 = rec(cap0.by_side);
  const [capTotal, setCapTotal] = useState(typeof cap0.total === "number" ? String(cap0.total) : "");
  const [capBySide, setCapBySide] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const side of sides) {
      const v = capBySide0[side];
      init[side] = typeof v === "number" ? String(v) : "";
    }
    return init;
  });
  // A blank/invalid/negative field clears that ceiling (→ null, which the backend drops
  // and the deep-merge overwrites). Otherwise it's a non-negative integer count.
  const capNum = (v: string): number | null => {
    const n = Number.parseInt(v.trim(), 10);
    return v.trim() !== "" && Number.isFinite(n) && n >= 0 ? n : null;
  };

  // --- Shareable invite message (copied per-guest from the Guests tab) ------
  const [inviteMessage, setInviteMessage] = useState(s(c.invite_message) || DEFAULT_INVITE_MESSAGE);

  // --- Names & cover -------------------------------------------------------
  const cover0 = rec(c.cover);
  const [couple, setCouple] = useState(content.couple_names);
  const [cover, setCover] = useState({
    kicker: s(cover0.kicker),
    greeting: s(cover0.greeting),
    invite_line: s(cover0.invite_line),
    tagline: s(cover0.tagline),
    story_cue: cover0.story_cue === undefined ? true : Boolean(cover0.story_cue),
    // Unset → seed the default so the field mirrors the live cue; an explicit
    // blank string is kept (badge shows alone, no text).
    story_cue_label: cover0.story_cue_label === undefined ? "The story" : s(cover0.story_cue_label),
  });

  // --- Brand mark (cover wordmark + center icon) ---------------------------
  const brand0 = rec(c.brand);
  const brandMode0 = s(brand0.icon_mode);
  const [brand, setBrand] = useState({
    wordmark_text: s(brand0.wordmark_text),
    icon_mode: (["default", "custom", "none"].includes(brandMode0)
      ? brandMode0
      : "default") as BrandIconMode,
    icon_url: s(brand0.icon_url),
    rsvp_icon_url: s(brand0.rsvp_icon_url),
  });

  // --- Landing page (the public "no link" site root) -----------------------
  const landing0 = rec(c.landing);
  const [landing, setLanding] = useState({
    visible: landing0.visible === undefined ? true : Boolean(landing0.visible),
    // Seed the defaults only when a field was NEVER set (wedding predates the
    // landing block), so the fields mirror the live page rather than showing
    // blank. Once a field exists — even as "" — keep it verbatim, so the owner
    // can deliberately clear a line (e.g. the body) and have it stick.
    heading: landing0.heading === undefined ? (LANDING_DEFAULTS.heading ?? "") : s(landing0.heading),
    tagline: landing0.tagline === undefined ? (LANDING_DEFAULTS.tagline ?? "") : s(landing0.tagline),
    body: landing0.body === undefined ? (LANDING_DEFAULTS.body ?? "") : s(landing0.body),
  });

  // --- Story section label ("Our story") -----------------------------------
  const storySection0 = rec(c.story_section);
  const [storySection, setStorySection] = useState({
    visible: storySection0.visible === undefined ? true : Boolean(storySection0.visible),
    label: s(storySection0.label),
  });

  // --- The day -------------------------------------------------------------
  const day0 = rec(c.day);
  const [event, setEvent] = useState({
    title: s(ev.title),
    venue: s(ev.venue),
    address: s(ev.address),
    area: s(ev.area),
    date_iso: s(ev.date_iso),
    date_display: s(ev.date_display),
    start_time: s(ev.start_time),
    end_time: s(ev.end_time),
    time_display: s(ev.time_display),
    map_url: s(ev.map_url),
    map_cta: s(ev.map_cta),
    map_button: ev.map_button !== false,
    dress_code: s(ev.dress_code),
    getting_there: s(ev.getting_there),
  });
  const [day, setDay] = useState({
    kicker: s(day0.kicker),
    heading: s(day0.heading),
    intro: s(day0.intro),
  });
  // Day-card detail cells — seed from event fields when none stored yet.
  const [cells, setCells] = useState<DayCell[]>(() => {
    const stored = Array.isArray(day0.cells) ? (day0.cells as DayCell[]) : [];
    return stored.length
      ? stored.map((x) => ({
          icon: s(x.icon) || "info",
          label: s(x.label),
          value: s(x.value),
          sub: s(x.sub),
          enabled: x.enabled !== false,
          map_link: Boolean(x.map_link),
        }))
      : defaultDayCells({
          time_display: s(ev.time_display),
          dress_code: s(ev.dress_code),
          address: s(ev.address),
          getting_there: s(ev.getting_there),
        });
  });
  const dateValue: Dayjs | null = event.date_iso ? dayjs(event.date_iso) : null;
  const onDate = (v: Dayjs | null) => {
    if (!v || !v.isValid()) return;
    setEvent((e) => ({
      ...e,
      date_iso: v.format("YYYY-MM-DD"),
      // Auto-fill the display string; it stays editable below.
      date_display: v.format("dddd, D MMMM YYYY"),
    }));
  };
  // Day-card cell mutators (edit / reorder / add / remove).
  const updateCell = (i: number, patch: Partial<DayCell>) =>
    setCells((cs) => cs.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  const moveCell = (i: number, dir: number) =>
    setCells((cs) => {
      const j = i + dir;
      if (j < 0 || j >= cs.length) return cs;
      const next = [...cs];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  const removeCell = (i: number) => setCells((cs) => cs.filter((_, idx) => idx !== i));
  const addCell = () =>
    setCells((cs) => [...cs, { icon: "sparkle", label: "New detail", value: "", enabled: true }]);

  // --- Dress code ----------------------------------------------------------
  const dress0 = rec(c.dress_code);
  const [dress, setDress] = useState({
    kicker: s(dress0.kicker),
    heading: s(dress0.heading),
    body: s(dress0.body),
    wear_label: s(dress0.wear_label),
    avoid_label: s(dress0.avoid_label),
  });
  const [swatches, setSwatches] = useState<string[]>(strList(dress0.swatches));
  const [swatchesAvoid, setSwatchesAvoid] = useState<string[]>(strList(dress0.swatches_avoid));

  // --- FAQ -----------------------------------------------------------------
  const faq0 = rec(c.faq);
  const [faqHead, setFaqHead] = useState({ kicker: s(faq0.kicker), heading: s(faq0.heading) });
  const [faqItems, setFaqItems] = useState<{ q: string; a: string }[]>(
    Array.isArray(faq0.items)
      ? faq0.items.map((x) => ({ q: s(rec(x).q), a: s(rec(x).a) }))
      : [],
  );
  const setFaqItem = (i: number, patch: Partial<{ q: string; a: string }>) =>
    setFaqItems((prev) => prev.map((it, j) => (j === i ? { ...it, ...patch } : it)));
  const moveFaq = (i: number, dir: -1 | 1) =>
    setFaqItems((prev) => {
      const j = i + dir;
      if (j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  // --- RSVP microcopy / steps / fields / party have moved to RsvpPanel -----

  // --- Footer & nav --------------------------------------------------------
  const footer0 = rec(c.footer);
  const nav0 = rec(c.nav);
  const [footer, setFooter] = useState({
    hashtag: s(footer0.hashtag),
    signoff: s(footer0.signoff),
  });
  const [nav, setNav] = useState({ brand: s(nav0.brand), cta: s(nav0.cta) });

  // --- Wishes / guestbook --------------------------------------------------
  const wishes0 = rec(c.wishes);
  const [wishes, setWishes] = useState({
    kicker: s(wishes0.kicker),
    heading: s(wishes0.heading),
    intro: s(wishes0.intro),
    name_label: s(wishes0.name_label),
    message_label: s(wishes0.message_label),
    button: s(wishes0.button),
    success: s(wishes0.success),
  });
  const [navLinks, setNavLinks] = useState<{ label: string; href: string }[]>(
    Array.isArray(nav0.links)
      ? nav0.links.map((x) => ({ label: s(rec(x).label), href: s(rec(x).href) }))
      : [],
  );
  const setNavLink = (i: number, patch: Partial<{ label: string; href: string }>) =>
    setNavLinks((prev) => prev.map((l, j) => (j === i ? { ...l, ...patch } : l)));

  return (
    <Paper sx={{ p: { xs: 1.5, sm: 2.5 } }}>
      <Typography variant="h6" sx={{ mb: 0.5 }}>
        Invite copy &amp; details
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Every word and detail on the invitation. Each section saves on its own.
      </Typography>

      {/* Names & cover ----------------------------------------------------- */}
      <SectionCard
        title="Names & cover"
        subtitle="Couple names and the opening greeting"
        defaultExpanded
        onChanged={onChanged}
        build={() => ({ couple_names: couple.trim(), content: { cover } })}
      >
        <TextField label="Couple names" value={couple} onChange={(e) => setCouple(e.target.value)} fullWidth />
        <TextField label="Kicker" value={cover.kicker}
          onChange={(e) => setCover({ ...cover, kicker: e.target.value })} fullWidth
          helperText="Sets the browser-tab title and link-preview heading (with the couple names)." />
        <TextField label="Greeting" value={cover.greeting}
          onChange={(e) => setCover({ ...cover, greeting: e.target.value })} fullWidth
          helperText="Use {name} for the guest's first name, e.g. “Dear {name},”" />
        <TextField label="Invite line" value={cover.invite_line}
          onChange={(e) => setCover({ ...cover, invite_line: e.target.value })} fullWidth />
        <TextField label="Tagline" value={cover.tagline}
          onChange={(e) => setCover({ ...cover, tagline: e.target.value })} fullWidth multiline minRows={2}
          helperText="Used as the link-preview / share description." />
        <FormControlLabel
          control={
            <Switch
              checked={cover.story_cue}
              onChange={(e) => setCover({ ...cover, story_cue: e.target.checked })}
            />
          }
          label={'Show the scroll cue'}
        />
        <TextField
          label="Scroll-cue text"
          value={cover.story_cue_label}
          onChange={(e) => setCover({ ...cover, story_cue_label: e.target.value })}
          fullWidth
          disabled={!cover.story_cue}
          helperText="The label under the cue badge at the bottom of the cover (desktop only). Leave blank to show just the icon."
        />
      </SectionCard>

      {/* Landing page (no link) ------------------------------------------- */}
      <SectionCard
        title="Landing page (no link)"
        subtitle="The public page shown when someone opens the site without their personal link"
        onChanged={onChanged}
        build={() => ({
          content: {
            landing: {
              visible: landing.visible,
              heading: landing.heading.trim(),
              tagline: landing.tagline.trim(),
              body: landing.body.trim(),
            },
          },
        })}
      >
        <FormControlLabel
          control={
            <Switch
              checked={landing.visible}
              onChange={(e) => setLanding({ ...landing, visible: e.target.checked })}
            />
          }
          label="Show the text"
        />
        <TextField
          label="Heading"
          value={landing.heading}
          onChange={(e) => setLanding({ ...landing, heading: e.target.value })}
          fullWidth
          disabled={!landing.visible}
          helperText="The big title (e.g. “Ever after”)."
        />
        <TextField
          label="Tagline"
          value={landing.tagline}
          onChange={(e) => setLanding({ ...landing, tagline: e.target.value })}
          fullWidth
          disabled={!landing.visible}
          multiline
          minRows={2}
        />
        <TextField
          label="Body"
          value={landing.body}
          onChange={(e) => setLanding({ ...landing, body: e.target.value })}
          fullWidth
          disabled={!landing.visible}
          multiline
          minRows={3}
          helperText="Names, date & venue line — and a hint that the real invite is at their personal link."
        />
      </SectionCard>

      {/* Invite message ---------------------------------------------------- */}
      <SectionCard
        title="Invite message"
        subtitle="The message you copy & send to each guest (WhatsApp, etc.)"
        onChanged={onChanged}
        build={() => ({ content: { invite_message: inviteMessage } })}
      >
        <TextField
          label="Message template"
          value={inviteMessage}
          onChange={(e) => setInviteMessage(e.target.value)}
          fullWidth
          multiline
          minRows={6}
          helperText="Copy this per guest from the Guests tab — placeholders fill in automatically."
        />
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
            Placeholders you can use:
          </Typography>
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
            {["{greeting}", "{name}", "{link}", "{couple}", "{venue}", "{date}", "{time}"].map(
              (p) => (
                <Chip key={p} label={p} size="small" variant="outlined" />
              ),
            )}
          </Stack>
        </Box>
      </SectionCard>

      {/* Brand mark -------------------------------------------------------- */}
      <SectionCard
        title="Brand mark"
        subtitle="The spinning cover wordmark and its center icon"
        onChanged={onChanged}
        build={() => ({ content: { brand } })}
      >
        <TextField
          label="Rotating wordmark text"
          value={brand.wordmark_text}
          onChange={(e) => setBrand({ ...brand, wordmark_text: e.target.value })}
          fullWidth
          helperText="The looping text on the ring around the cover icon (e.g. “Ever after”)."
        />
        <Divider flexItem />
        <Typography variant="subtitle2" color="text.secondary">Center icon</Typography>
        <ToggleButtonGroup
          exclusive
          size="small"
          color="primary"
          value={brand.icon_mode}
          onChange={(_, v: BrandIconMode | null) => v && setBrand({ ...brand, icon_mode: v })}
        >
          <ToggleButton value="default">Cat glyph</ToggleButton>
          <ToggleButton value="custom">Upload</ToggleButton>
          <ToggleButton value="none">No icon</ToggleButton>
        </ToggleButtonGroup>
        {brand.icon_mode === "custom" && (
          <Box sx={{ maxWidth: 200 }}>
            <ImageUpload
              label="icon"
              aspect="1 / 1"
              fit="contain"
              value={brand.icon_url}
              onChange={(url) => setBrand({ ...brand, icon_url: url })}
            />
            <Typography variant="caption" color="text.secondary">
              Square (1:1) works best — a transparent PNG is ideal. PNG, JPG or WebP, up to 15&nbsp;MB.
            </Typography>
          </Box>
        )}
        {brand.icon_mode === "custom" && !brand.icon_url && (
          <Alert severity="info">Upload an icon, or the cover keeps the cat glyph until you do.</Alert>
        )}
        <Divider flexItem />
        <Typography variant="subtitle2" color="text.secondary">RSVP guide circle</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ mt: -1 }}>
          A separate photo for the guide circle in the RSVP flow (beside the speech bubble and on
          the confirmation screen). Leave empty to keep the default icon. The cover, header and
          footer marks are unaffected.
        </Typography>
        <Box sx={{ maxWidth: 200 }}>
          <ImageUpload
            label="RSVP circle photo"
            aspect="1 / 1"
            fit="cover"
            value={brand.rsvp_icon_url}
            onChange={(url) => setBrand({ ...brand, rsvp_icon_url: url })}
          />
          <Typography variant="caption" color="text.secondary">
            Square (1:1) works best — it’s cropped to a circle. PNG, JPG or WebP, up to 15&nbsp;MB.
          </Typography>
        </Box>
      </SectionCard>

      {/* Story section label ----------------------------------------------- */}
      <SectionCard
        title="Story section label"
        subtitle="The small “Our story” label above the story"
        onChanged={onChanged}
        build={() => ({
          content: { story_section: { visible: storySection.visible, label: storySection.label.trim() } },
        })}
      >
        <FormControlLabel
          control={
            <Switch
              checked={storySection.visible}
              onChange={(e) => setStorySection({ ...storySection, visible: e.target.checked })}
            />
          }
          label="Show the label"
        />
        <TextField
          label="Label text"
          value={storySection.label}
          onChange={(e) => setStorySection({ ...storySection, label: e.target.value })}
          fullWidth
          helperText="Sits above your story (e.g. “Our story”). Leave blank or switch off to hide it."
        />
      </SectionCard>

      {/* The day ----------------------------------------------------------- */}
      <SectionCard
        title="The day"
        subtitle="Banner (date + venue) and the detail cells below it"
        onChanged={onChanged}
        build={() => ({ event_details: event, content: { day: { ...day, cells } } })}
      >
        <TextField label="Event title" value={event.title}
          onChange={(e) => setEvent({ ...event, title: e.target.value })} fullWidth />

        <Divider flexItem />
        <Typography variant="subtitle2" color="text.secondary">
          Banner — the big date and the “venue · area” line beneath it
        </Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="flex-start">
          <LocalizationProvider dateAdapter={AdapterDayjs}>
            <DatePicker
              label="Date"
              value={dateValue}
              onChange={onDate}
              slotProps={{ textField: { fullWidth: true } }}
            />
          </LocalizationProvider>
          <TextField label="Date (as shown)" value={event.date_display}
            onChange={(e) => setEvent({ ...event, date_display: e.target.value })} fullWidth
            helperText="Auto-filled from the picker; edit freely" />
        </Stack>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
          <TextField label="Venue name" value={event.venue}
            onChange={(e) => setEvent({ ...event, venue: e.target.value })} fullWidth
            helperText="Accent colour in the banner, e.g. Seaside Lounge" />
          <TextField label="Area (optional)" value={event.area}
            onChange={(e) => setEvent({ ...event, area: e.target.value })} fullWidth
            helperText="Shown after the venue · e.g. Singapore" />
        </Stack>
        <TextField label="Google Maps link" value={event.map_url}
          onChange={(e) => setEvent({ ...event, map_url: e.target.value })} fullWidth
          type="url" helperText="Opens from the “Open in Maps” button below the venue (and any cell with “Links to Maps” on)" />
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ alignItems: { sm: "center" } }}>
          <FormControlLabel
            sx={{ whiteSpace: "nowrap", m: 0 }}
            control={
              <Switch
                checked={event.map_button}
                onChange={(e) => setEvent({ ...event, map_button: e.target.checked })}
              />
            }
            label="Show “Open in Maps” button"
          />
          <TextField label="Button label" value={event.map_cta}
            onChange={(e) => setEvent({ ...event, map_cta: e.target.value })} fullWidth
            disabled={!event.map_button || !event.map_url}
            placeholder="Open in Maps"
            helperText="Shown on the pill button under the venue · needs a Maps link" />
        </Stack>

        <Divider flexItem />
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
          <TextField label="Start (HH:MM)" value={event.start_time}
            onChange={(e) => setEvent({ ...event, start_time: e.target.value })} fullWidth
            helperText="Drives the cover countdown" />
          <TextField label="End (HH:MM)" value={event.end_time}
            onChange={(e) => setEvent({ ...event, end_time: e.target.value })} fullWidth />
          <TextField label="Time (as shown)" value={event.time_display}
            onChange={(e) => setEvent({ ...event, time_display: e.target.value })} fullWidth
            helperText="Used in the shareable invite message ({time})" />
        </Stack>

        <Divider flexItem />
        <DayCellsEditor
          cells={cells}
          onUpdate={updateCell}
          onMove={moveCell}
          onRemove={removeCell}
          onAdd={addCell}
        />

        <Divider flexItem />
        <Typography variant="subtitle2" color="text.secondary">“The day” section copy</Typography>
        <RichTextField label="Kicker" value={day.kicker} variant="inline"
          onChange={(v) => setDay({ ...day, kicker: v })} />
        <RichTextField label="Heading" value={day.heading} variant="inline"
          onChange={(v) => setDay({ ...day, heading: v })} />
        <RichTextField label="Intro" value={day.intro}
          onChange={(v) => setDay({ ...day, intro: v })} />
      </SectionCard>

      {/* Capacity ---------------------------------------------------------- */}
      <SectionCard
        title="Capacity"
        subtitle="How many people the venue holds — drives the capacity chart on the Overview"
        onChanged={onChanged}
        build={() => ({
          event_details: {
            capacity: {
              total: capNum(capTotal),
              by_side: Object.fromEntries(sides.map((side) => [side, capNum(capBySide[side] ?? "")])),
            },
          },
        })}
      >
        <TextField
          label="Total capacity (people)"
          type="number"
          value={capTotal}
          onChange={(e) => setCapTotal(e.target.value)}
          slotProps={{ htmlInput: { min: 0 } }}
          sx={{ maxWidth: 260 }}
          helperText="The venue ceiling, counted in people (not invitations). Leave blank for no ceiling."
        />
        <Divider flexItem />
        <Typography variant="subtitle2" color="text.secondary">
          Per-side capacity (optional)
        </Typography>
        {sides.length === 0 ? (
          <Typography variant="caption" color="text.secondary">
            Give your guests a side (e.g. Alex / Sam) in the Guests tab to set a ceiling per side.
          </Typography>
        ) : (
          <>
            <Typography variant="caption" color="text.secondary" sx={{ mt: -1 }}>
              An agreed split per side — used by the “By side” tab of the capacity chart. Leave a
              side blank for no ceiling on that side.
            </Typography>
            <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap">
              {sides.map((side) => (
                <TextField
                  key={side}
                  label={side}
                  type="number"
                  value={capBySide[side] ?? ""}
                  onChange={(e) => setCapBySide((m) => ({ ...m, [side]: e.target.value }))}
                  slotProps={{ htmlInput: { min: 0 } }}
                  sx={{ maxWidth: 180 }}
                  size="small"
                />
              ))}
            </Stack>
          </>
        )}
      </SectionCard>

      {/* Dress code -------------------------------------------------------- */}
      <SectionCard
        title="Dress code"
        subtitle="Guidance plus colours to wear / avoid"
        onChanged={onChanged}
        build={() => ({
          content: {
            dress_code: {
              ...dress,
              swatches,
              swatches_avoid: swatchesAvoid,
            },
          },
        })}
      >
        <RichTextField label="Kicker" value={dress.kicker} variant="inline"
          onChange={(v) => setDress({ ...dress, kicker: v })} />
        <RichTextField label="Heading" value={dress.heading} variant="inline"
          onChange={(v) => setDress({ ...dress, heading: v })} />
        <RichTextField label="Guidance" value={dress.body}
          onChange={(v) => setDress({ ...dress, body: v })} />
        <Divider flexItem />
        <Typography variant="subtitle2" color="text.secondary">Colours to wear</Typography>
        <TextField label="“Wear” caption" value={dress.wear_label}
          onChange={(e) => setDress({ ...dress, wear_label: e.target.value })} fullWidth size="small" />
        <TokenSwatchPicker selected={swatches} onChange={setSwatches} />
        <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 1 }}>Colours to avoid</Typography>
        <TextField label="“Avoid” caption" value={dress.avoid_label}
          onChange={(e) => setDress({ ...dress, avoid_label: e.target.value })} fullWidth size="small" />
        <TokenSwatchPicker selected={swatchesAvoid} onChange={setSwatchesAvoid} />
      </SectionCard>

      {/* FAQ --------------------------------------------------------------- */}
      <SectionCard
        title="FAQ"
        subtitle="Questions & answers"
        onChanged={onChanged}
        build={() => ({
          content: {
            faq: {
              ...faqHead,
              items: faqItems.filter((it) => it.q.trim() || it.a.trim()),
            },
          },
        })}
      >
        <RichTextField label="Kicker" value={faqHead.kicker} variant="inline"
          onChange={(v) => setFaqHead({ ...faqHead, kicker: v })} />
        <RichTextField label="Heading" value={faqHead.heading} variant="inline"
          onChange={(v) => setFaqHead({ ...faqHead, heading: v })} />
        <Divider flexItem />
        {faqItems.map((it, i) => (
          <Paper key={i} variant="outlined" sx={{ p: 2 }}>
            <Stack direction="row" spacing={1} alignItems="flex-start">
              <Stack spacing={1.5} sx={{ flexGrow: 1 }}>
                <RichTextField label={`Question ${i + 1}`} value={it.q} variant="inline"
                  onChange={(v) => setFaqItem(i, { q: v })} />
                <RichTextField label="Answer" value={it.a}
                  onChange={(v) => setFaqItem(i, { a: v })} />
              </Stack>
              <Stack>
                <Tooltip title="Move up"><span>
                  <IconButton size="small" onClick={() => moveFaq(i, -1)} disabled={i === 0}>
                    <ArrowUpwardIcon fontSize="small" />
                  </IconButton></span>
                </Tooltip>
                <Tooltip title="Move down"><span>
                  <IconButton size="small" onClick={() => moveFaq(i, 1)} disabled={i === faqItems.length - 1}>
                    <ArrowDownwardIcon fontSize="small" />
                  </IconButton></span>
                </Tooltip>
                <Tooltip title="Remove">
                  <IconButton size="small" color="error" onClick={() => setFaqItems((p) => p.filter((_, j) => j !== i))}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>
            </Stack>
          </Paper>
        ))}
        <Box>
          <Button size="small" startIcon={<AddIcon />}
            onClick={() => setFaqItems((p) => [...p, { q: "", a: "" }])}>
            Add question
          </Button>
        </Box>
      </SectionCard>

      {/* Footer & nav ------------------------------------------------------ */}
      <SectionCard
        title="Navigation & footer"
        subtitle="Top-bar links and the sign-off"
        onChanged={onChanged}
        build={() => ({
          content: {
            nav: { ...nav, links: navLinks.filter((l) => l.label.trim() && l.href.trim()) },
            footer,
          },
        })}
      >
        <Typography variant="subtitle2" color="text.secondary">Navigation</Typography>
        <Typography variant="caption" color="text.secondary" component="div">
          Each link jumps to a section on the page. Available anchors:{" "}
          <Box component="span" sx={{ fontFamily: "monospace" }}>
            #cover
          </Box>{" "}
          (top),{" "}
          <Box component="span" sx={{ fontFamily: "monospace" }}>#story</Box> (our story),{" "}
          <Box component="span" sx={{ fontFamily: "monospace" }}>#day</Box> (the day),{" "}
          <Box component="span" sx={{ fontFamily: "monospace" }}>#dress</Box> (dress code),{" "}
          <Box component="span" sx={{ fontFamily: "monospace" }}>#faq</Box> (FAQ),{" "}
          <Box component="span" sx={{ fontFamily: "monospace" }}>#rsvp</Box> (RSVP),{" "}
          <Box component="span" sx={{ fontFamily: "monospace" }}>#wishes</Box> (leave a wish).
        </Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
          <TextField label="Brand text" value={nav.brand}
            onChange={(e) => setNav({ ...nav, brand: e.target.value })} fullWidth />
          <TextField label="RSVP button text" value={nav.cta}
            onChange={(e) => setNav({ ...nav, cta: e.target.value })} fullWidth />
        </Stack>
        {navLinks.map((l, i) => (
          <Stack key={i} direction="row" spacing={1} alignItems="center">
            <TextField label="Label" value={l.label}
              onChange={(e) => setNavLink(i, { label: e.target.value })} size="small" fullWidth />
            <TextField label="Anchor (e.g. #story)" value={l.href}
              onChange={(e) => setNavLink(i, { href: e.target.value })} size="small" fullWidth />
            <IconButton size="small" color="error"
              onClick={() => setNavLinks((p) => p.filter((_, j) => j !== i))}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Stack>
        ))}
        <Box>
          <Button size="small" startIcon={<AddIcon />}
            onClick={() => setNavLinks((p) => [...p, { label: "", href: "#" }])}>
            Add link
          </Button>
        </Box>
        <Divider flexItem />
        <Typography variant="subtitle2" color="text.secondary">Footer</Typography>
        <TextField label="Hashtag" value={footer.hashtag}
          onChange={(e) => setFooter({ ...footer, hashtag: e.target.value })} fullWidth />
        <RichTextField label="Sign-off" value={footer.signoff} variant="inline"
          onChange={(v) => setFooter({ ...footer, signoff: v })} />
      </SectionCard>

      {/* Wishes / guestbook ------------------------------------------------ */}
      <SectionCard
        title="Wishes / guestbook"
        subtitle="The “leave us a wish” section heading and labels"
        onChanged={onChanged}
        build={() => ({ content: { wishes } })}
      >
        <RichTextField label="Kicker" value={wishes.kicker} variant="inline"
          onChange={(v) => setWishes({ ...wishes, kicker: v })} />
        <RichTextField label="Heading" value={wishes.heading} variant="inline"
          onChange={(v) => setWishes({ ...wishes, heading: v })} />
        <RichTextField label="Intro" value={wishes.intro}
          onChange={(v) => setWishes({ ...wishes, intro: v })} />
        <Divider flexItem />
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
          <TextField label="Name field label" value={wishes.name_label}
            onChange={(e) => setWishes({ ...wishes, name_label: e.target.value })} fullWidth size="small" />
          <TextField label="Message field label" value={wishes.message_label}
            onChange={(e) => setWishes({ ...wishes, message_label: e.target.value })} fullWidth size="small" />
        </Stack>
        <TextField label="Button text" value={wishes.button}
          onChange={(e) => setWishes({ ...wishes, button: e.target.value })} fullWidth size="small" />
        <TextField label="Success message" value={wishes.success}
          onChange={(e) => setWishes({ ...wishes, success: e.target.value })} fullWidth size="small" />
      </SectionCard>
    </Paper>
  );
}
