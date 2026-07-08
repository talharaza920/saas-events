"use client";

import { useEffect, useState } from "react";

import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import LinearProgress from "@mui/material/LinearProgress";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useTheme, type Theme } from "@mui/material/styles";
import { ChartsReferenceLine } from "@mui/x-charts/ChartsReferenceLine";
import { LineChart } from "@mui/x-charts/LineChart";
import { PieChart } from "@mui/x-charts/PieChart";

import {
  adminApi,
  type AdminSummary,
  type GroupBreakdown,
  type PivotSummary,
  type QuestionBreakdown,
  type TimelineSummary,
} from "@/lib/adminApi";

type Seg = { label: string; value: number; color: string };
type Measure = "people" | "invitations";

/** Human labels for the pivot dimensions the backend exposes. */
const DIM_LABELS: Record<string, string> = {
  status: "Status",
  side: "Side",
  batch: "Batch",
  tier: "Invite tier",
  relationship: "Relationship",
  group: "Group",
};

/** Fixed colors + funnel order for the four invitation statuses, so a status split
 *  reads identically everywhere (hero bars, pivot stacks, legends). */
function statusColors(theme: Theme): Record<string, string> {
  return {
    Attending: theme.palette.success.main,
    Declined: theme.palette.error.main,
    Invited: theme.palette.info.main,
    Pending: theme.palette.warning.main,
  };
}
const STATUS_ORDER = ["Attending", "Declined", "Invited", "Pending"];

/** A neutral categorical palette for non-status stacks (tier/side/batch/…). */
function catPalette(theme: Theme): string[] {
  const x = theme.extra.colors;
  return [
    theme.palette.primary.main,
    theme.palette.secondary.main,
    x.accentSage,
    theme.palette.info.main,
    x.accentLav ?? theme.palette.warning.main,
    theme.palette.primary.light,
    theme.palette.secondary.light,
  ];
}

/** The four invitation statuses as colored segments (invitation counts). */
function statusSegs(g: { attending: number; declined: number; invited: number; pending: number }, theme: Theme): Seg[] {
  const c = statusColors(theme);
  return [
    { label: "Attending", value: g.attending, color: c.Attending },
    { label: "Declined", value: g.declined, color: c.Declined },
    { label: "Invited", value: g.invited, color: c.Invited },
    { label: "Pending", value: g.pending, color: c.Pending },
  ];
}

/** A thin horizontal stacked bar (status / head-count composition) + a dot legend.
 *  Each segment carries its count inside (white reads on every status/composition
 *  colour) when wide enough to hold it; thinner slices show nothing inline and rely on
 *  the hover tooltip. The count lives in the bar, so the legend is just colour + label. */
function SegBar({ segments, showLegend = true }: { segments: Seg[]; showLegend?: boolean }) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  const fitsInside = (v: number) => v / total >= 0.07;
  return (
    <Box>
      <Box sx={{ display: "flex", height: 20, borderRadius: 1, overflow: "hidden", bgcolor: "action.hover" }}>
        {segments
          .filter((s) => s.value > 0)
          .map((s) => (
            <Tooltip key={s.label} arrow title={`${s.label}: ${s.value}`}>
              <Box
                sx={{
                  width: `${(s.value / total) * 100}%`,
                  bgcolor: s.color,
                  display: "grid",
                  placeItems: "center",
                  cursor: "default",
                }}
              >
                {fitsInside(s.value) && <SegCount n={s.value} />}
              </Box>
            </Tooltip>
          ))}
      </Box>
      {showLegend && (
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, mt: 1.5 }}>
          {segments.map((s) => (
            <Box key={s.label} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
              <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: s.color }} />
              <Typography variant="body2" color="text.secondary">
                {s.label}
              </Typography>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}

/** Label · bar · value rows (dietary, …). `color` lets a row use its own hue. */
function BarRows({ rows }: { rows: { label: string; value: number; color?: string }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <Stack spacing={1.1} sx={{ mt: 0.5 }}>
      {rows.map((r) => (
        <Box
          key={r.label}
          sx={{ display: "grid", gridTemplateColumns: "minmax(72px,96px) 1fr 28px", alignItems: "center", gap: 1.25 }}
        >
          <Typography variant="body2" noWrap>
            {r.label}
          </Typography>
          <LinearProgress
            variant="determinate"
            value={(r.value / max) * 100}
            sx={{
              height: 11,
              borderRadius: 6,
              bgcolor: "action.hover",
              "& .MuiLinearProgress-bar": { borderRadius: 6, bgcolor: r.color ?? "primary.main" },
            }}
          />
          <Typography variant="body2" color="text.secondary" align="right">
            {r.value}
          </Typography>
        </Box>
      ))}
    </Stack>
  );
}

/** Small bold count printed inside a wide-enough bar segment. */
function SegCount({ n }: { n: number }) {
  return (
    <Typography sx={{ fontSize: 11, fontWeight: 700, color: "#fff", textShadow: "0 1px 2px rgba(0,0,0,.35)" }}>
      {n}
    </Typography>
  );
}

// --- Capacity utilization --------------------------------------------------

/** Capacity-segment colors — aligned with the status palette so "confirmed" reads as
 *  Attending (green) and "invited" as Invited (blue), matching the rest of the page. */
function capacityColors(theme: Theme): { confirmed: string; invited: string } {
  return { confirmed: theme.palette.success.main, invited: theme.palette.info.main };
}

/** One horizontal capacity bar: confirmed (attending heads) + invited (awaiting reply)
 *  stacked against a capacity ceiling. Pending/declined are excluded — the empty
 *  remainder is "how many more you can invite". When over the ceiling, the bar grows
 *  past a red capacity marker; when no capacity is set it just sizes to the used count. */
function CapacityBar({
  confirmed,
  invited,
  capacity,
  theme,
}: {
  confirmed: number;
  invited: number;
  capacity?: number | null;
  theme: Theme;
}) {
  const c = capacityColors(theme);
  const used = confirmed + invited;
  const hasCap = capacity != null && capacity > 0;
  const cap = capacity ?? 0;
  const denom = Math.max(hasCap ? cap : 0, used, 1);
  const over = hasCap && used > cap;
  const remaining = hasCap ? cap - used : null;
  // Marker sits at the ceiling; only drawn when the bar overflows it (otherwise it's
  // exactly the right edge of the track, which already reads as "full = capacity").
  const markerPct = hasCap ? Math.min(100, (cap / denom) * 100) : 100;
  const seg = (v: number) => `${(v / denom) * 100}%`;
  const segments = [
    { key: "confirmed", label: "Confirmed", value: confirmed, color: c.confirmed },
    { key: "invited", label: "Invited (awaiting reply)", value: invited, color: c.invited },
  ].filter((srow) => srow.value > 0);
  // The count is printed inside its segment (white reads on both the green/blue fills)
  // only when the segment is wide enough to hold it; thinner stacks show nothing inline
  // and rely on the hover tooltip instead.
  const fitsInside = (v: number) => v / denom >= 0.06;
  return (
    <Box>
      <Box sx={{ position: "relative" }}>
        <Box sx={{ display: "flex", height: 22, borderRadius: 1, overflow: "hidden", bgcolor: "action.hover" }}>
          {segments.map((srow) => (
            <Tooltip
              key={srow.key}
              arrow
              title={`${srow.label}: ${srow.value} ${srow.value === 1 ? "person" : "people"}`}
            >
              <Box sx={{ width: seg(srow.value), bgcolor: srow.color, display: "grid", placeItems: "center", cursor: "default" }}>
                {fitsInside(srow.value) && <SegCount n={srow.value} />}
              </Box>
            </Tooltip>
          ))}
        </Box>
        {markerPct < 100 && (
          <Box
            title={`Capacity: ${cap}`}
            sx={{ position: "absolute", top: -3, bottom: -3, left: `${markerPct}%`, width: "2px", bgcolor: "error.main" }}
          />
        )}
      </Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", gap: 1, mt: 0.75 }}>
        <Typography variant="caption" color="text.secondary">
          {hasCap ? `${used} of ${cap} people` : `${used} people · no capacity set`}
        </Typography>
        {hasCap &&
          (over ? (
            <Typography variant="caption" sx={{ color: "error.main", fontWeight: 700 }}>
              over by {used - cap}
            </Typography>
          ) : (
            <Typography variant="caption" color="text.secondary">
              {remaining} {remaining === 1 ? "seat" : "seats"} left
            </Typography>
          ))}
      </Box>
    </Box>
  );
}

/** Shared dot legend for the capacity bars. */
function CapacityLegend({ theme }: { theme: Theme }) {
  const c = capacityColors(theme);
  const items = [
    { label: "Confirmed", color: c.confirmed },
    { label: "Invited (awaiting reply)", color: c.invited },
  ];
  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, mb: 2 }}>
      {items.map((i) => (
        <Box key={i.label} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
          <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: i.color }} />
          <Typography variant="body2" color="text.secondary">
            {i.label}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

/** Row-2 capacity lens: Overall (one bar against the venue ceiling) vs By side (one
 *  bar per side against its own ceiling). Confirmed + invited heads only — declined
 *  frees its room and pending isn't committed yet, so the gap is "who you can still
 *  invite". Capacity is owner-set in the Details tab and echoed on the summary. */
function CapacityPanel({ summary }: { summary: AdminSummary }) {
  const theme = useTheme();
  const [tab, setTab] = useState(0);
  const cap = summary.capacity;
  const sides = summary.by_side ?? [];
  const hasAnyCap = cap.total != null || Object.keys(cap.by_side ?? {}).length > 0;

  return (
    <Card variant="outlined">
      <CardContent>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2, minHeight: 40 }}>
          <Tab label="Overall" sx={{ minHeight: 40 }} />
          <Tab label="By side" sx={{ minHeight: 40 }} />
        </Tabs>
        <CapacityLegend theme={theme} />
        {tab === 0 ? (
          <CapacityBar
            confirmed={summary.head_count}
            invited={summary.invited_people}
            capacity={cap.total}
            theme={theme}
          />
        ) : sides.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
            Give your guests a side (Alex / Sam) to see capacity split by side.
          </Typography>
        ) : (
          <Stack spacing={2}>
            {sides.map((srow) => (
              <Box key={srow.key}>
                <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                  {srow.label}
                </Typography>
                <CapacityBar
                  confirmed={srow.head_count}
                  invited={srow.invited_people}
                  capacity={cap.by_side?.[srow.label]}
                  theme={theme}
                />
              </Box>
            ))}
          </Stack>
        )}
        {!hasAnyCap && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
            Set a capacity in the <b>Details</b> tab to track how much room is left.
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}

function PanelCard({
  title,
  subtitle,
  children,
  sx,
}: {
  title: string;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  sx?: object;
}) {
  return (
    <Card variant="outlined" sx={{ flex: "1 1 300px", minWidth: 280, ...sx }}>
      <CardContent>
        <Typography variant="h6" sx={{ fontFamily: (t) => t.extra.typography.story, fontWeight: 600 }}>
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            {subtitle}
          </Typography>
        )}
        {children}
      </CardContent>
    </Card>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <Typography
      variant="overline"
      color="text.secondary"
      sx={{ display: "block", letterSpacing: "0.16em", mb: 0.5 }}
    >
      {children}
    </Typography>
  );
}

function BreakdownCard({ b }: { b: QuestionBreakdown }) {
  const scopeNote = b.scope === "person" ? "per person" : "per invitee";
  return (
    <PanelCard title={b.prompt} subtitle={`${b.answered} of ${b.applicable} answered · ${scopeNote}`}>
      {b.counts.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
          No answers yet.
        </Typography>
      ) : (
        <BarRows rows={b.counts.map((c) => ({ label: c.label, value: c.count }))} />
      )}
    </PanelCard>
  );
}

// --- Configurable pivot ----------------------------------------------------

/** The numeric value of a cell under the chosen measure. */
function cellValue(g: GroupBreakdown, measure: Measure): number {
  return measure === "people" ? g.people : g.invitations;
}

/** Build the stacked segments for one group: its `then`-by children (or a single
 *  solid segment when there's no second pivot). Colors come from a shared map so the
 *  same series value is the same color in every bar + the legend. */
function segmentsOf(g: GroupBreakdown, then: string | null | undefined, measure: Measure, colors: Map<string, string>, fallback: string): Seg[] {
  if (then && g.children.length) {
    return g.children.map((c) => ({ label: c.label, value: cellValue(c, measure), color: colors.get(c.label) ?? fallback }));
  }
  return [{ label: g.label, value: cellValue(g, measure), color: fallback }];
}

/** Stable series-label → color map across all groups, for the stack + legend. */
function buildColorMap(pivot: PivotSummary, theme: Theme): { colors: Map<string, string>; legend: string[] } {
  const colors = new Map<string, string>();
  if (!pivot.then) return { colors, legend: [] };
  if (pivot.then === "status") {
    const sc = statusColors(theme);
    const present = STATUS_ORDER.filter((l) => pivot.groups.some((g) => g.children.some((c) => c.label === l)));
    present.forEach((l) => colors.set(l, sc[l]));
    return { colors, legend: present };
  }
  const cat = catPalette(theme);
  const legend: string[] = [];
  for (const g of pivot.groups) {
    for (const c of g.children) {
      if (!colors.has(c.label)) {
        colors.set(c.label, cat[colors.size % cat.length]);
        legend.push(c.label);
      }
    }
  }
  return { colors, legend };
}

/** Vertical stacked columns — one per group, height ∝ its total under the measure,
 *  with the count printed inside each segment that's tall enough to hold it. */
function VerticalBars({ pivot, measure, theme }: { pivot: PivotSummary; measure: Measure; theme: Theme }) {
  const fallback = theme.palette.primary.main;
  const { colors } = buildColorMap(pivot, theme);
  const totals = pivot.groups.map((g) => cellValue(g, measure));
  const max = Math.max(1, ...totals);
  const H = 230;
  return (
    <Box sx={{ display: "flex", alignItems: "flex-end", gap: { xs: 1.5, sm: 3 }, height: H + 44, pt: 1 }}>
      {pivot.groups.map((g, i) => {
        const segs = segmentsOf(g, pivot.then, measure, colors, fallback).filter((s) => s.value > 0);
        const colHeight = (totals[i] / max) * H;
        return (
          <Box key={g.key} sx={{ flex: "1 1 0", minWidth: 48, display: "flex", flexDirection: "column", alignItems: "center" }}>
            <Box
              sx={{
                width: "100%",
                maxWidth: 96,
                height: colHeight,
                display: "flex",
                flexDirection: "column-reverse",
                borderRadius: 1.5,
                overflow: "hidden",
                bgcolor: "action.hover",
              }}
            >
              {segs.map((s) => {
                const h = (s.value / totals[i]) * colHeight;
                return (
                  <Box
                    key={s.label}
                    title={`${s.label}: ${s.value}`}
                    sx={{ height: h, bgcolor: s.color, display: "grid", placeItems: "center" }}
                  >
                    {h >= 18 && (
                      <Typography sx={{ fontSize: 12, fontWeight: 700, color: "#fff", textShadow: "0 1px 2px rgba(0,0,0,.35)" }}>
                        {s.value}
                      </Typography>
                    )}
                  </Box>
                );
              })}
            </Box>
            <Typography variant="body2" sx={{ fontWeight: 600, mt: 1, textAlign: "center", lineHeight: 1.15 }} noWrap>
              {g.label}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {totals[i]}
            </Typography>
          </Box>
        );
      })}
    </Box>
  );
}

/** A dot legend for the current stack series. */
function PivotLegend({ legend, colors }: { legend: string[]; colors: Map<string, string> }) {
  if (legend.length === 0) return null;
  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, mb: 2 }}>
      {legend.map((l) => (
        <Box key={l} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
          <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: colors.get(l) }} />
          <Typography variant="body2" color="text.secondary">
            {l}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

// The three lenses of the pivot. Invitee & Guests share data (all statuses), differing
// only in the measure plotted; Confirmed re-queries restricted to attending parties.
const PIVOT_TABS: { label: string; measure: Measure; status: string }[] = [
  { label: "Invitee", measure: "invitations", status: "" },
  { label: "Guests", measure: "people", status: "" },
  { label: "Confirmed", measure: "people", status: "attending" },
];

/** A small donut of the TOTAL split by status (fixed — independent of the Then-by
 *  selector), with each slice labelled by value and share. Caps at ~1/3 of the row. */
function StatusPie({ groups, measure, theme }: { groups: GroupBreakdown[]; measure: Measure; theme: Theme }) {
  const sc = statusColors(theme);
  const data = STATUS_ORDER.map((label) => {
    const g = groups.find((x) => x.label === label);
    return g ? { id: label, label, value: cellValue(g, measure), color: sc[label] } : null;
  }).filter((d): d is { id: string; label: string; value: number; color: string } => !!d && d.value > 0);
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  if (data.length === 0) return null;
  return (
    <Box>
      <PieChart
        height={200}
        series={[
          {
            data,
            innerRadius: 34,
            paddingAngle: 1,
            cornerRadius: 3,
            arcLabel: (item) => `${item.value} (${Math.round((item.value / total) * 100)}%)`,
            arcLabelMinAngle: 26,
            arcLabelRadius: "65%",
          },
        ]}
        hideLegend
        margin={{ top: 6, bottom: 6, left: 6, right: 6 }}
        sx={{ "& .MuiPieArcLabel-root": { fill: "#fff", fontWeight: 700, fontSize: 11 } }}
      />
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.25, justifyContent: "center", mt: 0.5 }}>
        {data.map((d) => (
          <Box key={d.id} sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <Box sx={{ width: 9, height: 9, borderRadius: "50%", bgcolor: d.color }} />
            <Typography variant="caption" color="text.secondary">
              {d.label}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

/** Row-2 pivot: Invitee / Guests / Confirmed tabs over one shared control bar
 *  (Side filter + Group by + Then by). Same vertical bar chart throughout — the tab
 *  only swaps the measure (invitations ↔ people) and, for Confirmed, scopes to
 *  attending. A fixed status donut of the total sits alongside (≤ 1/3 width). */
function PivotTabs({ summary }: { summary: AdminSummary }) {
  const theme = useTheme();
  const [tab, setTab] = useState(0);
  const [by, setBy] = useState("side");
  const [then, setThen] = useState("status");
  const [side, setSide] = useState(""); // "" = all sides
  const [pivot, setPivot] = useState<PivotSummary | null>(null);
  const [pie, setPie] = useState<PivotSummary | null>(null);
  const [pieErr, setPieErr] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(false);

  const { measure, status } = PIVOT_TABS[tab];

  // Main chart: re-fetch when a control or the status scope changes. Switching
  // Invitee↔Guests does NOT refetch (same query key) — only the measure differs.
  // Spinner on every refetch (not just first mount) so a control change gives
  // immediate feedback, and a .catch so a failed/timed-out request surfaces a
  // retry instead of silently leaving the previous chart on screen.
  useEffect(() => {
    let live = true;
    // Deliberate setState on refetch: the spinner must reset per refetch or a slow
    // backend reads as a frozen UI (see LEARNINGS "N+1 lazy-loads").
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
     
    setErr(false);
    adminApi
      .summaryPivot(by, then, { side: side || undefined, status: status || undefined })
      .then((p) => {
        if (!live) return;
        setPivot(p);
        setBy(p.by);
        setThen(p.then ?? "");
      })
      .catch(() => {
        if (live) setErr(true);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [by, then, side, status]);

  // The donut is always grouped by status (fixed), so it only depends on the scope
  // (the side filter). It's hidden on the Confirmed tab — that tab is already filtered
  // to one status, so a status split would be a single 100% slice. Skip the fetch too.
  useEffect(() => {
    if (status) return; // Confirmed tab: no donut
    let live = true;
    // Deliberate error reset per refetch (same rationale as the effect above).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPieErr(false);
    adminApi
      .summaryPivot("status", "", { side: side || undefined })
      .then((p) => {
        if (live) setPie(p);
      })
      .catch(() => {
        // Don't strand the donut on an infinite spinner if the request fails —
        // surface the error so the slot resolves (mirrors the main chart).
        if (live) setPieErr(true);
      });
    return () => {
      live = false;
    };
  }, [side, status]);

  const dims = pivot?.available_dims ?? [];
  const thenOptions = dims.filter((d) => d !== by);
  const sideOptions = (summary.by_side ?? []).map((s) => s.label);
  const { colors, legend } = pivot ? buildColorMap(pivot, theme) : { colors: new Map<string, string>(), legend: [] };

  const total = pivot?.total;
  const pieTitle = tab === 0 ? "Invitations by status" : tab === 1 ? "Guests by status" : "Confirmed by status";
  const headline = !total
    ? ""
    : tab === 0
      ? `${total.invitations} invitations · ${total.attending + total.declined} replied`
      : tab === 1
        ? `~${total.people} expected guests (confirmed heads + estimate)`
        : `${total.people} confirmed guests across ${total.attending} attending ${total.attending === 1 ? "party" : "parties"}`;

  return (
    <Card variant="outlined">
      <CardContent>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2, minHeight: 40 }}>
          {PIVOT_TABS.map((t) => (
            <Tab key={t.label} label={t.label} sx={{ minHeight: 40 }} />
          ))}
        </Tabs>

        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 1.5, mb: 2 }}>
          <Typography variant="body2" color="text.secondary" sx={{ alignSelf: "center" }}>
            {headline}
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
            {sideOptions.length > 0 && (
              <TextField select size="small" label="Side" value={side} onChange={(e) => setSide(e.target.value)} sx={{ minWidth: 116 }}>
                <MenuItem value="">All sides</MenuItem>
                {sideOptions.map((s) => (
                  <MenuItem key={s} value={s}>
                    {s}
                  </MenuItem>
                ))}
              </TextField>
            )}
            {dims.length > 0 && (
              <>
                <TextField select size="small" label="Group by" value={by} onChange={(e) => setBy(e.target.value)} sx={{ minWidth: 128 }}>
                  {dims.map((d) => (
                    <MenuItem key={d} value={d}>
                      {DIM_LABELS[d] ?? d}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField select size="small" label="then by" value={then} onChange={(e) => setThen(e.target.value)} sx={{ minWidth: 120 }}>
                  <MenuItem value="">None</MenuItem>
                  {thenOptions.map((d) => (
                    <MenuItem key={d} value={d}>
                      {DIM_LABELS[d] ?? d}
                    </MenuItem>
                  ))}
                </TextField>
              </>
            )}
          </Stack>
        </Box>

        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 3, alignItems: "flex-start" }}>
          {/* Left (~2/3): the configurable Group-by × Then-by bar chart. */}
          <Box sx={{ flex: "2 1 340px", minWidth: 300 }}>
            <PivotLegend legend={legend} colors={colors} />
            {loading ? (
              <Box sx={{ display: "flex", justifyContent: "center", py: 5 }}>
                <CircularProgress size={26} />
              </Box>
            ) : err || !pivot ? (
              <Typography variant="body2" color="error" sx={{ py: 2 }}>
                Couldn&apos;t load this view — change a control to retry.
              </Typography>
            ) : pivot.groups.length === 0 ? (
              <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                Nothing to show for this view{side ? ` on ${side}'s side` : ""} yet.
              </Typography>
            ) : (
              <VerticalBars pivot={pivot} measure={measure} theme={theme} />
            )}
          </Box>

          {/* Right (≤ 1/3): fixed status donut of the total. Hidden on Confirmed —
              that tab is already a single status, so the split adds nothing. */}
          {tab !== 2 && (
            <Box sx={{ flex: "1 1 220px", minWidth: 200, maxWidth: 340 }}>
              <Typography variant="overline" color="text.secondary" sx={{ display: "block", letterSpacing: "0.12em", textAlign: "center" }}>
                {pieTitle}
              </Typography>
              {pieErr ? (
                <Typography variant="body2" color="error" sx={{ py: 2, textAlign: "center" }}>
                  Couldn&apos;t load.
                </Typography>
              ) : pie ? (
                <StatusPie groups={pie.groups} measure={measure} theme={theme} />
              ) : (
                <Box sx={{ display: "flex", justifyContent: "center", py: 5 }}>
                  <CircularProgress size={22} />
                </Box>
              )}
            </Box>
          )}
        </Box>
      </CardContent>
    </Card>
  );
}

/** Expected-vs-confirmed people per side — each bar relative to that side's OWN
 *  estimate (so a small side filling up reads as full, not dwarfed by a big one). */
function HeadcountBySide({ sides, theme }: { sides: GroupBreakdown[]; theme: Theme }) {
  const sage = theme.extra.colors.accentSage;
  return (
    <Stack spacing={1.5} sx={{ mt: 0.5 }}>
      {sides.map((s, i) => {
        const color = i === 0 ? theme.palette.primary.main : i === 1 ? theme.palette.secondary.main : sage;
        const pct = s.expected_head_count > 0 ? Math.min(100, (s.head_count / s.expected_head_count) * 100) : 0;
        return (
          <Box key={s.key}>
            <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {s.label}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                <b>{s.head_count}</b> of ~{s.expected_head_count}
              </Typography>
            </Box>
            <LinearProgress
              variant="determinate"
              value={pct}
              sx={{ height: 11, borderRadius: 6, bgcolor: "action.hover", "& .MuiLinearProgress-bar": { borderRadius: 6, bgcolor: color } }}
            />
          </Box>
        );
      })}
    </Stack>
  );
}

/** Collapsible Trends section: lazy-loads the timeline on first open, then shows the
 *  cumulative replies chart (left) + this-week-vs-last-week momentum (right). */
function TrendsPanel({ summary }: { summary: AdminSummary }) {
  const theme = useTheme();
  const [timeline, setTimeline] = useState<TimelineSummary | null>(null);
  const [loading, setLoading] = useState(false);

  const loadTimeline = () => {
    if (timeline || loading) return;
    setLoading(true);
    adminApi
      .summaryTimeline()
      .then(setTimeline)
      .catch(() => setTimeline({ total_invitations: 0, total_replied: 0, points: [] }))
      .finally(() => setLoading(false));
  };

  const replied = summary.attending + summary.declined;
  const repliedPct = summary.total_guests > 0 ? Math.round((replied / summary.total_guests) * 100) : 0;
  const thisWeek = summary.replies_this_week ?? 0;
  const lastWeek = summary.replies_last_week ?? 0;
  const delta = thisWeek - lastWeek;
  const up = delta >= 0;
  const pct = lastWeek > 0 ? Math.round((delta / lastWeek) * 100) : null;

  const points = timeline?.points ?? [];
  const xLabels = points.map((p) =>
    new Date(p.week_start).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
  );
  const cumulative = points.map((p) => p.cumulative);
  const spark = points.slice(-6);
  const sparkMax = Math.max(1, ...spark.map((p) => p.new));

  return (
    <Accordion
      variant="outlined"
      disableGutters
      onChange={(_, isOpen) => isOpen && loadTimeline()}
      sx={{ borderRadius: 2, "&:before": { display: "none" }, bgcolor: "background.paper" }}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.5, flexWrap: "wrap" }}>
          <Typography sx={{ fontFamily: (t) => t.extra.typography.story, fontWeight: 600, fontSize: "1.05rem" }}>
            RSVPs over time
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {thisWeek > 0 ? `+${thisWeek} this week · ` : ""}
            {repliedPct}% replied
          </Typography>
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        {loading || !timeline ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 5 }}>
            <CircularProgress size={28} />
          </Box>
        ) : points.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ py: 3 }}>
            No replies yet — the curve appears once guests start responding.
          </Typography>
        ) : (
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
            <Card variant="outlined" sx={{ flex: "2 1 420px", minWidth: 320 }}>
              <CardContent>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Cumulative replies · {repliedPct}% of invitations
                </Typography>
                <LineChart
                  height={240}
                  xAxis={[{ data: xLabels, scaleType: "point" }]}
                  yAxis={[{ min: 0, max: Math.max(timeline.total_invitations, timeline.total_replied, 1) }]}
                  series={[
                    {
                      data: cumulative,
                      label: "Replies",
                      area: true,
                      showMark: false,
                      color: theme.palette.primary.dark,
                    },
                  ]}
                  margin={{ left: 0, right: 12, top: 10, bottom: 24 }}
                  hideLegend
                >
                  {timeline.total_invitations > 0 && (
                    <ChartsReferenceLine
                      y={timeline.total_invitations}
                      label={`${timeline.total_invitations} invited`}
                      labelAlign="start"
                      lineStyle={{ strokeDasharray: "5 5", stroke: theme.palette.divider }}
                      labelStyle={{ fontSize: 11, fill: theme.palette.text.secondary }}
                    />
                  )}
                </LineChart>
              </CardContent>
            </Card>

            <Card variant="outlined" sx={{ flex: "1 1 220px", minWidth: 220 }}>
              <CardContent>
                <SectionLabel>This week</SectionLabel>
                <Typography sx={{ fontFamily: (t) => t.extra.typography.story, fontWeight: 600, fontSize: "3rem", lineHeight: 1, color: "primary.dark" }}>
                  {thisWeek}
                </Typography>
                <Typography variant="body2" sx={{ mt: 0.5 }}>
                  new RSVPs
                </Typography>
                <Chip
                  size="small"
                  icon={up ? <ArrowUpwardIcon /> : <ArrowDownwardIcon />}
                  color={up ? "success" : "error"}
                  variant="outlined"
                  label={`${up ? "+" : ""}${delta}${pct !== null ? ` (${up ? "+" : ""}${pct}%)` : ""} vs last week`}
                  sx={{ mt: 1.5, fontWeight: 600 }}
                />
                {spark.length > 1 && (
                  <Box sx={{ display: "flex", alignItems: "flex-end", gap: 0.75, height: 40, mt: 2 }}>
                    {spark.map((p, i) => (
                      <Box
                        key={p.week_start}
                        title={`${p.new} on ${xLabels[xLabels.length - spark.length + i]}`}
                        sx={{
                          width: 14,
                          height: `${Math.max(8, (p.new / sparkMax) * 100)}%`,
                          borderRadius: "3px 3px 0 0",
                          bgcolor: "primary.main",
                          opacity: i === spark.length - 1 ? 1 : 0.45,
                        }}
                      />
                    ))}
                  </Box>
                )}
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                  Last week {lastWeek} · counted by first reply
                </Typography>
              </CardContent>
            </Card>
          </Box>
        )}
      </AccordionDetails>
    </Accordion>
  );
}

export default function SummaryPanel({ summary }: { summary: AdminSummary }) {
  const theme = useTheme();
  const sage = theme.extra.colors.accentSage;

  const primaries = Math.max(summary.head_count - summary.extra_adults - summary.extra_children, 0);
  const expectedPct =
    summary.expected_head_count > 0 ? Math.round((summary.head_count / summary.expected_head_count) * 100) : 0;
  // When the owner has set a capacity, the People hero measures confirmed heads against
  // it ("of N capacity · X% of capacity"); otherwise it falls back to the estimate.
  const totalCapacity = summary.capacity.total;
  const capacityPct =
    totalCapacity && totalCapacity > 0 ? Math.round((summary.head_count / totalCapacity) * 100) : 0;
  const repliedPct =
    summary.total_guests > 0 ? Math.round(((summary.attending + summary.declined) / summary.total_guests) * 100) : 0;

  const breakdowns = (summary.question_breakdowns ?? []).filter((b) => b.applicable > 0);
  const sides = summary.by_side ?? [];

  return (
    <Stack spacing={3}>
      {/* ===== SECTION 1 — PEOPLE (the venue headcount lens) ===== */}
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1.3fr" }, gap: 2 }}>
        <Card variant="outlined">
          <CardContent>
            <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: "0.14em" }}>
              People
            </Typography>
            <Box sx={{ display: "flex", alignItems: "baseline", gap: 1 }}>
              <Typography sx={{ fontFamily: (t) => t.extra.typography.story, fontWeight: 600, fontSize: "3.4rem", lineHeight: 1, color: "primary.dark" }}>
                {summary.head_count}
              </Typography>
              <Typography variant="h6" component="span">
                guests coming
              </Typography>
            </Box>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {totalCapacity && totalCapacity > 0 ? (
                <>of {totalCapacity} capacity · <b>{capacityPct}%</b> of capacity</>
              ) : summary.expected_head_count > 0 ? (
                <>of ~{summary.expected_head_count} expected · <b>{expectedPct}%</b> of your estimate</>
              ) : (
                "confirmed head count"
              )}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>
              Confirmed people across {summary.attending} attending{" "}
              {summary.attending === 1 ? "party" : "parties"} — the number to give the venue.
            </Typography>
          </CardContent>
        </Card>

        <Card variant="outlined">
          <CardContent>
            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: "0.14em" }}>
                Invitations
              </Typography>
              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                {repliedPct}% replied
              </Typography>
            </Box>
            <Typography variant="body2" sx={{ mb: 1 }}>
              <b>{summary.attending + summary.declined}</b> of {summary.total_guests} invitations have replied
            </Typography>
            <SegBar segments={statusSegs(summary, theme)} />
            {summary.pending + summary.invited > 0 && (
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>
                {summary.invited > 0 && `${summary.invited} invited & awaiting`}
                {summary.invited > 0 && summary.pending > 0 && " · "}
                {summary.pending > 0 && `${summary.pending} not yet contacted`}
              </Typography>
            )}
          </CardContent>
        </Card>
      </Box>

      {/* Row 2 — capacity utilization (confirmed + invited vs the venue ceiling). */}
      <Box>
        <SectionLabel>Capacity</SectionLabel>
        <CapacityPanel summary={summary} />
      </Box>

      {/* Row 3 — the Invitee / Person / Confirmed pivot. */}
      <Box>
        <SectionLabel>Breakdown</SectionLabel>
        <PivotTabs summary={summary} />
      </Box>

      {/* Headcount detail + catering (people lens). */}
      <Box>
        <SectionLabel>Headcount &amp; catering</SectionLabel>
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
          <PanelCard
            title="Who's coming"
            subtitle={`${summary.head_count} people across ${summary.attending} ${summary.attending === 1 ? "party" : "parties"}`}
          >
            <SegBar
              segments={[
                { label: "Primary", value: primaries, color: theme.palette.primary.main },
                { label: "Extra guests", value: summary.extra_adults, color: theme.palette.secondary.main },
                { label: "Children", value: summary.extra_children, color: sage },
              ]}
            />
            {summary.extra_children > 0 && (
              <>
                <Divider sx={{ my: 1.5 }} />
                <Chip label={`🪑 ${summary.extra_children} kids' chairs`} sx={{ fontWeight: 600 }} />
              </>
            )}
          </PanelCard>

          {sides.length > 0 && (
            <PanelCard title="By side" subtitle="Confirmed vs expected people">
              <HeadcountBySide sides={sides} theme={theme} />
            </PanelCard>
          )}

          {breakdowns.map((b) => (
            <BreakdownCard key={b.question_id} b={b} />
          ))}
        </Box>
      </Box>

      {/* Trends (collapsed by default). */}
      <Box>
        <SectionLabel>Trends</SectionLabel>
        <TrendsPanel summary={summary} />
      </Box>

      <Typography variant="body2" color="text.secondary">
        Numeric and free-text answers (specific ages, notes, …) are in the Responses tab and the
        guest export.
      </Typography>
    </Stack>
  );
}
