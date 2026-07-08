import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { FooterContent } from "@/lib/content";

import MascotBadge from "./brand/MascotBadge";
import RichText from "./RichText";

/** Closing dark band — the mascot, sign-off, and the hashtag. */
export default function Footer({ footer }: { footer: FooterContent }) {
  return (
    <Box
      component="footer"
      sx={{
        py: { xs: 8, md: 13 },
        px: 3,
        textAlign: "center",
        bgcolor: "text.primary",
        color: "background.default",
      }}
    >
      <Stack spacing={2} sx={{ alignItems: "center" }}>
        <MascotBadge size={86} invert />
        {footer.signoff && (
          <Typography variant="subtitle1" sx={{ fontSize: { xs: "1.3rem", md: "1.85rem" }, color: "background.default" }}>
            <RichText text={footer.signoff} variant="inline" />
          </Typography>
        )}
        {footer.hashtag && (
          <Typography sx={{ letterSpacing: "0.2em", fontWeight: 700, color: "primary.main" }}>
            {footer.hashtag}
          </Typography>
        )}
      </Stack>
    </Box>
  );
}
