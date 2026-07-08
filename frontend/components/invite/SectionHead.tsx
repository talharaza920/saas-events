import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import RichText from "./RichText";

/** The eyebrow "kicker" with flanking rules, used above each section heading. */
export function Kicker({ children }: { children: React.ReactNode }) {
  const rule = {
    content: '""',
    width: 26,
    height: "1.5px",
    bgcolor: "currentColor",
    opacity: 0.55,
    display: "inline-block",
  };
  return (
    <Box
      component="span"
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 1.25,
        color: "primary.dark",
        fontWeight: 600,
        fontSize: 13,
        letterSpacing: "0.18em",
        textTransform: "uppercase",
        "&::before": rule,
        "&::after": rule,
      }}
    >
      {children}
    </Box>
  );
}

/** Centered section header: kicker + h2 + intro paragraph. */
export default function SectionHead({
  kicker,
  heading,
  intro,
}: {
  kicker?: string;
  heading?: string;
  intro?: string;
}) {
  return (
    <Stack spacing={2} sx={{ textAlign: "center", maxWidth: 680, mx: "auto", mb: { xs: 5, md: 8 }, alignItems: "center" }}>
      {kicker && (
        <Kicker>
          <RichText text={kicker} variant="inline" />
        </Kicker>
      )}
      {heading && (
        <Typography variant="h2" component="h2" sx={{ fontSize: { xs: "2.1rem", sm: "3rem", md: "3.5rem" } }}>
          <RichText text={heading} variant="inline" />
        </Typography>
      )}
      {intro && (
        <Typography sx={{ color: "text.secondary", fontSize: { xs: "1rem", md: "1.125rem" } }}>
          <RichText text={intro} />
        </Typography>
      )}
    </Stack>
  );
}
