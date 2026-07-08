import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import type { SxProps, Theme } from "@mui/material/styles";

import SectionHead from "./SectionHead";

/**
 * Shared section shell: the design's generous vertical rhythm + an optional
 * centered head (kicker / heading / intro). Background and max width are tokens;
 * copy comes from the wedding's stored content.
 */
export default function Section({
  id,
  kicker,
  heading,
  intro,
  maxWidth = "md",
  bg,
  children,
  sx,
}: {
  id?: string;
  kicker?: string;
  heading?: string;
  intro?: string;
  maxWidth?: "xs" | "sm" | "md" | "lg";
  /** Background color token (e.g. "background.default" | "background.paper"). */
  bg?: string;
  children?: React.ReactNode;
  sx?: SxProps<Theme>;
}) {
  return (
    <Box
      component="section"
      id={id}
      sx={[
        {
          py: { xs: 9, sm: 14, md: 16 },
          position: "relative",
          ...(bg ? { bgcolor: bg } : {}),
          scrollMarginTop: "72px",
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      <Container maxWidth={maxWidth}>
        {(kicker || heading || intro) && <SectionHead kicker={kicker} heading={heading} intro={intro} />}
        {children}
      </Container>
    </Box>
  );
}
