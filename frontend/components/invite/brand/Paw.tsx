import Box from "@mui/material/Box";
import type { SxProps, Theme } from "@mui/material/styles";

/**
 * Paw print — main pad + four toe beans. Inherits `currentColor`; reused across
 * the RSVP paw-trail, chips, and buttons.
 */
export default function Paw({ size = 22, sx }: { size?: number; sx?: SxProps<Theme> }) {
  return (
    <Box
      component="svg"
      viewBox="0 0 100 100"
      aria-hidden="true"
      sx={[{ width: size, height: size, color: "text.primary", display: "block" }, ...(Array.isArray(sx) ? sx : [sx])]}
    >
      <g fill="currentColor">
        <ellipse cx="50" cy="64" rx="24" ry="20" />
        <circle cx="24" cy="40" r="9" />
        <circle cx="42" cy="26" r="9.5" />
        <circle cx="58" cy="26" r="9.5" />
        <circle cx="76" cy="40" r="9" />
      </g>
    </Box>
  );
}
