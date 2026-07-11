"use client";

import Box from "@mui/material/Box";
import type { SxProps, Theme } from "@mui/material/styles";

/**
 * Renders an AI-designed mark: SVG children for a 100×100 viewBox, drawn in
 * currentColor. ONLY ever fed the server-sanitised form (the pipeline runs the
 * allowlist-rebuild sanitiser before anything is stored — app/ai/svg.py), which
 * is what makes the innerHTML safe to set. Never pass raw model output here.
 */
export default function GlyphMark({
  svg,
  size = 64,
  sx,
}: {
  svg: string;
  size?: number;
  sx?: SxProps<Theme>;
}) {
  return (
    <Box
      component="svg"
      viewBox="0 0 100 100"
      aria-hidden
      sx={{ width: size, height: size, color: "text.primary", display: "block", ...sx }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
