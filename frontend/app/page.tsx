import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import InviteThemeProvider from "@/components/invite/InviteThemeProvider";
import { fetchLanding } from "@/lib/api";
import { LANDING_DEFAULTS, parseLanding } from "@/lib/content";
import type { ThemeTokensOverride } from "@/theme/types";

/**
 * Root landing — the public "no link" page shown when the site is visited without
 * a personal invite link. The copy is data-driven from the wedding's
 * `content.landing` block (editable in /admin → Details → "Landing page"), and
 * falls back to built-in defaults if the backend is unreachable. The real guest
 * experience lives at /i/[guestSlug].
 */
export const dynamic = "force-dynamic";

export default async function Home() {
  const data = await fetchLanding();
  const landing = data ? parseLanding(data.landing) : LANDING_DEFAULTS;
  const tokens = (data?.theme_tokens ?? null) as ThemeTokensOverride | null;

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
