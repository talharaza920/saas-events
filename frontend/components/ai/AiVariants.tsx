"use client";

import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import type { AiVariantAdmin } from "@/lib/adminApi";

import GlyphMark from "./GlyphMark";

function rec(v: unknown): Record<string, unknown> {
  return typeof v === "object" && v !== null ? (v as Record<string, unknown>) : {};
}

/**
 * Every version of one artifact, side by side — nothing a regeneration
 * replaced is ever thrown away (app/ai/variants.py keeps the original as
 * variant 0), so the couple can always go back to the one they had.
 */
export function VariantStrip({
  variants,
  busyId,
  disabled,
  onSelect,
}: {
  variants: AiVariantAdmin[];
  /** Id of the variant currently being selected (spinner). */
  busyId?: string | null;
  disabled?: boolean;
  onSelect: (v: AiVariantAdmin) => void;
}) {
  if (variants.length < 2) return null;
  return (
    <Stack direction="row" spacing={1.5} sx={{ overflowX: "auto", pb: 1 }}>
      {variants.map((v, i) => {
        const c = rec(v.content);
        return (
          <Paper
            key={v.id}
            variant="outlined"
            onClick={() => !v.selected && !disabled && onSelect(v)}
            sx={{
              p: 1.5,
              minWidth: 180,
              maxWidth: 240,
              cursor: v.selected || disabled ? "default" : "pointer",
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
                {busyId === v.id && <CircularProgress size={14} />}
              </Stack>
              {v.image_url ? (
                <Box
                  component="img"
                  src={v.image_url}
                  alt="Illustration option"
                  sx={{ width: "100%", borderRadius: 1, display: "block" }}
                />
              ) : c.svg_children ? (
                <>
                  <GlyphMark svg={String(c.svg_children)} size={56} />
                  <Typography variant="caption" color="text.secondary">
                    {String(c.concept ?? "")}
                  </Typography>
                </>
              ) : (
                <Typography
                  variant="caption"
                  sx={{
                    display: "-webkit-box",
                    WebkitLineClamp: 4,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  {String(
                    rec(c.story_arc).intro ??
                      (Array.isArray(rec(c.story_arc).beats)
                        ? rec((rec(c.story_arc).beats as unknown[])[0]).text ?? ""
                        : ""),
                  )}
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
}

/**
 * The couple's one instruction channel to the model. Bounded here and again
 * server-side, and it only ever rides the USER turn (never a system prompt).
 */
export function SteerBox({
  value,
  onChange,
  onRegenerate,
  busy,
  disabled,
  label = "Want it different? Tell it how",
  placeholder = "e.g. less flowery — and don't mention the rain",
}: {
  value: string;
  onChange: (v: string) => void;
  onRegenerate: () => void;
  busy?: boolean;
  disabled?: boolean;
  label?: string;
  placeholder?: string;
}) {
  return (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ alignItems: { sm: "center" } }}>
      <TextField
        size="small"
        fullWidth
        label={label}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value.slice(0, 500))}
      />
      <Button
        variant="outlined"
        startIcon={busy ? <CircularProgress size={16} /> : <AutoAwesomeIcon />}
        disabled={disabled}
        onClick={onRegenerate}
        sx={{ whiteSpace: "nowrap" }}
      >
        Regenerate
      </Button>
    </Stack>
  );
}
