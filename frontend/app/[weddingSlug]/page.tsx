import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { notFound } from "next/navigation";

import InviteThemeProvider from "@/components/invite/InviteThemeProvider";
import { fetchWeddingLanding } from "@/lib/api";
import { parseLanding } from "@/lib/content";
import type { ThemeTokensOverride } from "@/theme/types";

/**
 * The public `/{weddingSlug}` page — a wedding's own "no link" landing. Only
 * active AND published weddings resolve; everything else (draft, suspended,
 * archived, never existed) is the same neutral 404. Static platform routes
 * (/dashboard, /create, /platform, …) win over this dynamic segment.
 */
export const dynamic = "force-dynamic";

export default async function WeddingLandingPage({
  params,
}: {
  params: Promise<{ weddingSlug: string }>;
}) {
  const { weddingSlug } = await params;
  const data = await fetchWeddingLanding(weddingSlug);
  if (!data) notFound();

  const landing = parseLanding(data.landing);
  const tokens = (data.theme_tokens ?? null) as ThemeTokensOverride | null;

  return (
    <InviteThemeProvider tokens={tokens}>
      <Box sx={{ bgcolor: "background.default", color: "text.primary", minHeight: "100dvh" }}>
        <Container maxWidth="sm">
          <Stack spacing={3} sx={{ minHeight: "100dvh", justifyContent: "center", py: 8 }}>
            <Box
              aria-hidden
              sx={{ width: 56, height: 56, borderRadius: "50%", bgcolor: "primary.main" }}
            />
            {landing.visible && (
              <>
                {landing.heading && (
                  <Typography variant="h2" component="h1" color="text.primary">
                    {landing.heading}
                  </Typography>
                )}
                {landing.tagline && (
                  <Typography variant="subtitle1" color="text.primary">
                    {landing.tagline}
                  </Typography>
                )}
                {landing.body && (
                  <Typography variant="body1" color="text.primary">
                    {landing.body}
                  </Typography>
                )}
              </>
            )}
          </Stack>
        </Container>
      </Box>
    </InviteThemeProvider>
  );
}
