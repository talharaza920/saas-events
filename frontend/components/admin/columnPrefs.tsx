"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ViewColumnIcon from "@mui/icons-material/ViewColumn";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Popover from "@mui/material/Popover";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { GridColDef, GridColumnVisibilityModel } from "@mui/x-data-grid";

/**
 * Owner column preferences (order + visibility) for a DataGrid, persisted to
 * localStorage per view. The free (Community) DataGrid can't drag-reorder
 * columns, so we own the order ourselves: the hook returns the column list
 * re-sorted to the stored order, plus a controlled visibility model, and
 * {@link ColumnSettings} is the up/down + show/hide control that drives it.
 */
type Prefs = { order: string[]; hidden: string[] };

function loadPrefs(key: string): Prefs {
  if (typeof window === "undefined") return { order: [], hidden: [] };
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return { order: [], hidden: [] };
    const p = JSON.parse(raw) as Partial<Prefs>;
    return {
      order: Array.isArray(p.order) ? p.order.filter((x) => typeof x === "string") : [],
      hidden: Array.isArray(p.hidden) ? p.hidden.filter((x) => typeof x === "string") : [],
    };
  } catch {
    return { order: [], hidden: [] };
  }
}

export interface ColumnPrefs {
  orderedColumns: GridColDef[];
  orderedFields: string[];
  visibilityModel: GridColumnVisibilityModel;
  hidden: string[];
  columns: GridColDef[];
  move: (field: string, dir: -1 | 1) => void;
  toggleHidden: (field: string) => void;
  setVisibilityModel: (model: GridColumnVisibilityModel) => void;
  reset: () => void;
}

export function useColumnPrefs(storageKey: string, columns: GridColDef[]): ColumnPrefs {
  const [prefs, setPrefs] = useState<Prefs>(() => loadPrefs(storageKey));

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(storageKey, JSON.stringify(prefs));
    }
  }, [storageKey, prefs]);

  const fields = useMemo(() => columns.map((c) => c.field), [columns]);

  // Reconcile the stored order with the live column set: keep the known order,
  // then append any columns that are new (or weren't reordered yet).
  const orderedFields = useMemo(() => {
    const known = prefs.order.filter((f) => fields.includes(f));
    const missing = fields.filter((f) => !known.includes(f));
    return [...known, ...missing];
  }, [prefs.order, fields]);

  const orderedColumns = useMemo(
    () =>
      orderedFields
        .map((f) => columns.find((c) => c.field === f))
        .filter((c): c is GridColDef => Boolean(c)),
    [orderedFields, columns],
  );

  const visibilityModel = useMemo<GridColumnVisibilityModel>(
    () => Object.fromEntries(prefs.hidden.map((f) => [f, false])),
    [prefs.hidden],
  );

  const move = useCallback(
    (field: string, dir: -1 | 1) =>
      setPrefs((p) => {
        const cur = [...orderedFields];
        const i = cur.indexOf(field);
        const j = i + dir;
        if (i < 0 || j < 0 || j >= cur.length) return p;
        [cur[i], cur[j]] = [cur[j], cur[i]];
        return { ...p, order: cur };
      }),
    [orderedFields],
  );

  const toggleHidden = useCallback(
    (field: string) =>
      setPrefs((p) => ({
        ...p,
        hidden: p.hidden.includes(field)
          ? p.hidden.filter((f) => f !== field)
          : [...p.hidden, field],
      })),
    [],
  );

  // Keep in sync if visibility is changed via the grid's own Columns button.
  const setVisibilityModel = useCallback(
    (model: GridColumnVisibilityModel) =>
      setPrefs((p) => ({ ...p, hidden: fields.filter((f) => model[f] === false) })),
    [fields],
  );

  const reset = useCallback(() => setPrefs({ order: [], hidden: [] }), []);

  return {
    orderedColumns,
    orderedFields,
    visibilityModel,
    hidden: prefs.hidden,
    columns,
    move,
    toggleHidden,
    setVisibilityModel,
    reset,
  };
}

/**
 * Custom MULTI-column sort for the Community DataGrid, persisted to localStorage per
 * view. Multi-sort is a Pro-only feature (Community forcibly truncates the sort model
 * to one column), so we do it ourselves: the grid's own sorting is disabled and we
 * sort the rows in JS by an ordered list of {field, sort} levels. Header click sets a
 * single level; **Shift-click adds/cycles a level**. {@link applyMultiSort} sorts the
 * rows; {@link SortBar} shows + edits the active levels.
 */
export type SortLevel = { field: string; sort: "asc" | "desc" };

function loadSortModel(key: string): SortLevel[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(key) || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (s): s is SortLevel =>
        s && typeof s.field === "string" && (s.sort === "asc" || s.sort === "desc"),
    );
  } catch {
    return [];
  }
}

export interface MultiSort {
  model: SortLevel[];
  /** Header click on `field`: replace with a single level (asc→desc→off). With
   * `additive` (Shift-click) append the field, or cycle/remove it if already present. */
  toggle: (field: string, additive: boolean) => void;
  remove: (field: string) => void;
  clear: () => void;
}

export function useMultiSort(storageKey: string): MultiSort {
  const key = `${storageKey}:sort`;
  const [model, setModelState] = useState<SortLevel[]>(() => loadSortModel(key));
  const setModel = useCallback(
    (next: SortLevel[]) => {
      setModelState(next);
      if (typeof window !== "undefined") window.localStorage.setItem(key, JSON.stringify(next));
    },
    [key],
  );
  const toggle = useCallback(
    (field: string, additive: boolean) => {
      const cur = model;
      const i = cur.findIndex((s) => s.field === field);
      if (!additive) {
        // Single-column: cycle the sole column asc→desc→off; otherwise start fresh.
        if (cur.length === 1 && i === 0) {
          setModel(cur[0].sort === "asc" ? [{ field, sort: "desc" }] : []);
        } else {
          setModel([{ field, sort: "asc" }]);
        }
        return;
      }
      // Shift-click: add the field, or cycle it within the existing levels (asc→desc→remove).
      if (i === -1) {
        setModel([...cur, { field, sort: "asc" }]);
      } else if (cur[i].sort === "asc") {
        setModel(cur.map((s, idx) => (idx === i ? { field, sort: "desc" } : s)));
      } else {
        setModel(cur.filter((_, idx) => idx !== i));
      }
    },
    [model, setModel],
  );
  const remove = useCallback((field: string) => setModel(model.filter((s) => s.field !== field)), [model, setModel]);
  const clear = useCallback(() => setModel([]), [setModel]);
  return { model, toggle, remove, clear };
}

/** Stable multi-key sort of grid rows by the active levels (numbers compared
 * numerically, everything else by locale string; blanks sort last). */
export function applyMultiSort<T extends Record<string, unknown>>(rows: T[], model: SortLevel[]): T[] {
  if (model.length === 0) return rows;
  const indexed = rows.map((row, i) => [row, i] as const);
  indexed.sort(([a, ai], [b, bi]) => {
    for (const { field, sort } of model) {
      const av = a[field];
      const bv = b[field];
      const aEmpty = av === null || av === undefined || av === "";
      const bEmpty = bv === null || bv === undefined || bv === "";
      let c = 0;
      if (aEmpty || bEmpty) c = aEmpty === bEmpty ? 0 : aEmpty ? 1 : -1; // blanks last (both directions)
      else if (typeof av === "number" && typeof bv === "number") c = av - bv;
      else c = String(av).localeCompare(String(bv));
      if (c !== 0) return sort === "asc" ? c : -c;
    }
    return ai - bi; // stable
  });
  return indexed.map(([row]) => row);
}

/** The up/down + show/hide popover that drives a {@link useColumnPrefs} instance. */
export function ColumnSettings({ prefs }: { prefs: ColumnPrefs }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const { columns, orderedFields, hidden, move, toggleHidden, reset } = prefs;
  const labelOf = (f: string) =>
    String(columns.find((c) => c.field === f)?.headerName ?? f) || "—";

  return (
    <>
      <Button size="small" startIcon={<ViewColumnIcon />} onClick={(e) => setAnchor(e.currentTarget)}>
        Columns
      </Button>
      <Popover
        open={Boolean(anchor)}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      >
        <Box sx={{ p: 1, width: 300 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ px: 1, py: 0.5 }}>
            <Typography variant="subtitle2">Reorder &amp; show columns</Typography>
            <Button size="small" color="inherit" onClick={reset}>
              Reset
            </Button>
          </Stack>
          <Divider />
          <Stack sx={{ maxHeight: 380, overflow: "auto", mt: 0.5 }}>
            {orderedFields.map((f, i) => {
              const isHidden = hidden.includes(f);
              return (
                <Stack
                  key={f}
                  direction="row"
                  alignItems="center"
                  spacing={0.25}
                  sx={{ px: 1, py: 0.25 }}
                >
                  <Typography
                    variant="body2"
                    noWrap
                    sx={{ flexGrow: 1, color: isHidden ? "text.disabled" : "text.primary" }}
                  >
                    {labelOf(f)}
                  </Typography>
                  <IconButton size="small" disabled={i === 0} onClick={() => move(f, -1)}>
                    <ArrowUpwardIcon fontSize="inherit" />
                  </IconButton>
                  <IconButton
                    size="small"
                    disabled={i === orderedFields.length - 1}
                    onClick={() => move(f, 1)}
                  >
                    <ArrowDownwardIcon fontSize="inherit" />
                  </IconButton>
                  <Tooltip title={isHidden ? "Show" : "Hide"}>
                    <IconButton size="small" onClick={() => toggleHidden(f)}>
                      {isHidden ? (
                        <VisibilityOffIcon fontSize="inherit" />
                      ) : (
                        <VisibilityIcon fontSize="inherit" />
                      )}
                    </IconButton>
                  </Tooltip>
                </Stack>
              );
            })}
          </Stack>
        </Box>
      </Popover>
    </>
  );
}

/** Shows the active multi-sort levels as ordered chips (click to flip ↑/↓, ✕ to
 * remove) + a hint. Pairs with {@link useMultiSort} + a grid using `disableColumnSorting`
 * and `onColumnHeaderClick` → `sort.toggle(field, e.shiftKey)`. */
export function SortBar({ sort, columns }: { sort: MultiSort; columns: GridColDef[] }) {
  const labelOf = (f: string) => String(columns.find((c) => c.field === f)?.headerName ?? f) || f;
  return (
    <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 0.75, mb: 0.5 }}>
      <Typography variant="caption" color="text.secondary">
        Sort:
      </Typography>
      {sort.model.length === 0 ? (
        <Typography variant="caption" color="text.secondary">
          click a header to sort · Shift-click to add columns
        </Typography>
      ) : (
        <>
          {sort.model.map((lvl, i) => (
            <Chip
              key={lvl.field}
              size="small"
              label={`${i + 1}. ${labelOf(lvl.field)} ${lvl.sort === "asc" ? "↑" : "↓"}`}
              onClick={() => sort.toggle(lvl.field, true)}
              onDelete={() => sort.remove(lvl.field)}
            />
          ))}
          <Button size="small" color="inherit" onClick={sort.clear} sx={{ minWidth: 0, px: 1 }}>
            Clear
          </Button>
        </>
      )}
    </Box>
  );
}
