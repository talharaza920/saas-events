import Box from "@mui/material/Box";
import type { SxProps, Theme } from "@mui/material/styles";

/**
 * The cat-head glyph — ellipse head + two triangular ears, ink fill. Composed
 * from basic shapes so it stays crisp at any size. Inherits `currentColor`, so
 * set the colour on the parent (`sx={{ color: 'text.primary' }}`).
 */
export default function CatGlyph({ size = 40, sx }: { size?: number; sx?: SxProps<Theme> }) {
  return (
    <Box
      component="svg"
      viewBox="0 0 100 100"
      aria-hidden="true"
      sx={[{ width: size, height: size, color: "text.primary", display: "block" }, ...(Array.isArray(sx) ? sx : [sx])]}
    >
      <g fill="currentColor">
        <polygon points="23,44 25,9 50,36" />
        <polygon points="77,44 75,9 50,36" />
        <ellipse cx="50" cy="60" rx="35" ry="31" />
      </g>
    </Box>
  );
}
