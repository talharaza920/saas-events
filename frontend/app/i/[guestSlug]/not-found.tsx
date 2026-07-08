import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

/**
 * Shown for an unknown or inactive invite link. Deliberately vague — it must not
 * confirm whether a slug exists, and it never hints at tiers or guest data.
 */
export default function InviteNotFoundPage() {
  return (
    <Container maxWidth="sm">
      <Stack spacing={2} sx={{ minHeight: "100dvh", justifyContent: "center", textAlign: "center" }}>
        <Typography variant="h3" component="h1" color="text.primary">
          Hmm, we couldn&apos;t find that invitation
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Double-check the link from your invite — it may be incomplete. If it
          keeps happening, reach out to Alex &amp; Sam.
        </Typography>
      </Stack>
    </Container>
  );
}
