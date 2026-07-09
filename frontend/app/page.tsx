import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import InviteThemeProvider from "@/components/invite/InviteThemeProvider";

/**
 * Platform root — a static landing for the product itself. It deliberately
 * fetches nothing: serving any one wedding's copy here was a single-tenant
 * leftover (review backlog #5). Couples land on /dashboard and /create; each
 * wedding's own public page lives at /{weddingSlug}, and the real guest
 * experience at /i/[guestSlug].
 */
export default function Home() {
  return (
    <InviteThemeProvider tokens={null}>
      <Box sx={{ bgcolor: "background.default", color: "text.primary", minHeight: "100dvh" }}>
        <Container maxWidth="sm">
          <Stack spacing={3} sx={{ minHeight: "100dvh", justifyContent: "center", py: 8 }}>
            <Box
              aria-hidden
              sx={{ width: 56, height: 56, borderRadius: "50%", bgcolor: "primary.main" }}
            />
            <Typography variant="h2" component="h1" color="text.primary">
              Ever after
            </Typography>
            <Typography variant="subtitle1" color="text.primary">
              Beautiful wedding invitations, RSVPs, and guest lists — in one place.
            </Typography>
            <Typography variant="body1" color="text.primary">
              Create your wedding site, send each guest a personal link, and watch the
              replies roll in. Looking for an invitation? It lives at the personal link
              you were sent.
            </Typography>
            <Stack direction="row" spacing={2}>
              {/* Plain hrefs (not next/link): this stays a Server Component, and a
                  component prop can't cross into the client-rendered MUI Button. */}
              <Button href="/create" variant="contained">
                Create your wedding
              </Button>
              <Button href="/dashboard" variant="outlined">
                Sign in
              </Button>
            </Stack>
          </Stack>
        </Container>
      </Box>
    </InviteThemeProvider>
  );
}
