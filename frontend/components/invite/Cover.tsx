"use client";

import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { BrandContent, CoverContent, EventDetails } from "@/lib/content";
import { eventTargetISO, useCountdown } from "@/lib/useCountdown";

import MascotBadge from "./brand/MascotBadge";
import Wordmark from "./brand/Wordmark";

/** Renders "Alex & Sam" with the ampersand in the accent color. */
function CoupleNames({ names }: { names: string }) {
  const parts = names.split("&");
  if (parts.length !== 2) return <>{names}</>;
  return (
    <>
      {parts[0].trim()}{" "}
      <Box component="span" sx={{ color: "primary.main", fontStyle: "normal" }}>
        &amp;
      </Box>{" "}
      {parts[1].trim()}
    </>
  );
}

const CELLS: [keyof ReturnType<typeof useCountdown>, string][] = [
  ["d", "Days"],
  ["h", "Hours"],
  ["m", "Minutes"],
  ["s", "Seconds"],
];

/**
 * Hero / chapter opener. Greets the guest by their invitee greeting override when
 * set, else by first name (server-resolved — the URL never carries the name),
 * shows the rotating wordmark and a live countdown.
 * All colors/fonts are theme tokens; copy comes from the wedding's stored content.
 */
export default function Cover({
  firstName,
  greetingName,
  coupleNames,
  cover,
  brand,
  event,
}: {
  firstName: string;
  // Invitee-level greeting override (e.g. "John & Jane"); falls back to firstName.
  greetingName?: string | null;
  coupleNames: string;
  cover: CoverContent;
  brand: BrandContent;
  event: EventDetails;
}) {
  const t = useCountdown(eventTargetISO(event.date_iso, event.start_time));
  const who = greetingName?.trim() || firstName;
  const greeting = (cover.greeting ?? "Dear {name},").replace("{name}", who);
  const dateVenue = [event.date_display, [event.venue, event.area].filter(Boolean).join(", ")]
    .filter(Boolean);

  return (
    <Box
      component="header"
      id="cover"
      sx={{
        minHeight: "100svh",
        display: "grid",
        placeItems: "center",
        textAlign: "center",
        position: "relative",
        overflow: "hidden",
        px: 3,
        pt: { xs: 12, sm: 14 },
        pb: 8,
      }}
    >
      {/* dreamy pastel blobs */}
      <Box aria-hidden sx={{ position: "absolute", width: 420, height: 420, borderRadius: "50%", filter: "blur(60px)", opacity: 0.5, bgcolor: (th) => th.extra.colors.dream1, top: -80, left: -60 }} />
      <Box aria-hidden sx={{ position: "absolute", width: 380, height: 380, borderRadius: "50%", filter: "blur(60px)", opacity: 0.5, bgcolor: (th) => th.extra.colors.dream2, bottom: -60, right: -40 }} />

      <Container maxWidth="md" sx={{ position: "relative", zIndex: 1 }}>
        {/* width:100% on text so the flex `alignItems:center` doesn't let long
            lines take max-content width and overflow — they wrap instead. */}
        <Stack spacing={1.5} sx={{ alignItems: "center", width: "100%" }}>
          <Box sx={{ mb: 2 }}>
            <Wordmark
              size={150}
              text={brand.wordmark_text || undefined}
              icon={{ mode: brand.icon_mode, url: brand.icon_url }}
            />
          </Box>
          {greeting && (
            <Typography variant="subtitle1" sx={{ width: "100%", color: "text.secondary", fontSize: { xs: "1.25rem", sm: "1.5rem" } }}>
              {greeting}
            </Typography>
          )}
          <Typography
            variant="h1"
            component="h1"
            sx={{ width: "100%", fontWeight: 800, lineHeight: 0.94, fontSize: { xs: "3rem", sm: "5.5rem", md: "8rem" }, my: 0.5, overflowWrap: "break-word" }}
          >
            <CoupleNames names={coupleNames} />
          </Typography>
          {cover.invite_line && (
            <Typography sx={{ width: "100%", color: "text.secondary", fontSize: { xs: "1.05rem", sm: "1.2rem" }, letterSpacing: "0.02em" }}>
              {cover.invite_line}
            </Typography>
          )}

          {/* countdown */}
          {event.date_iso && (
            <Stack direction="row" spacing={{ xs: 0.5, sm: 3 }} sx={{ justifyContent: "center", alignItems: "flex-start", mt: 3, mb: 0.5, maxWidth: "100%" }}>
              {CELLS.map(([k, label], i) => (
                <Box key={k} sx={{ display: "flex", alignItems: "flex-start", gap: { xs: 0.5, sm: 3 } }}>
                  {i > 0 && (
                    <Box component="span" sx={{ fontFamily: (th) => th.extra.typography.display, fontWeight: 800, color: "divider", fontSize: { xs: "1.4rem", sm: "2.8rem" } }}>
                      :
                    </Box>
                  )}
                  <Box sx={{ minWidth: { xs: 42, sm: 64 } }}>
                    <Typography sx={{ fontFamily: (th) => th.extra.typography.display, fontWeight: 800, lineHeight: 1, fontVariantNumeric: "tabular-nums", fontSize: { xs: "1.7rem", sm: "3.25rem" } }}>
                      {String(t[k]).padStart(2, "0")}
                    </Typography>
                    <Typography sx={{ fontSize: { xs: 9, sm: 11 }, letterSpacing: { xs: "0.08em", sm: "0.22em" }, textTransform: "uppercase", color: "text.secondary", mt: 0.75 }}>
                      {label}
                    </Typography>
                  </Box>
                </Box>
              ))}
            </Stack>
          )}

          {dateVenue.length > 0 && (
            <Typography sx={{ width: "100%", color: "text.secondary", fontSize: { xs: "0.95rem", sm: "1.05rem" }, mt: 0.5 }}>
              {dateVenue.map((line, i) => (
                <Box component="span" key={i} sx={{ display: "block" }}>
                  {line}
                </Box>
              ))}
            </Typography>
          )}
        </Stack>
      </Container>

      {/* scroll cue — owner-toggleable (cover.story_cue, default on), and hidden on
          phones, where it would collide with the hero text on short viewports (and
          mobile users scroll naturally). */}
      {cover.story_cue !== false && (
      <Box
        component="a"
        href="#story"
        aria-label="Scroll to our story"
        sx={{
          position: "absolute",
          bottom: 26,
          left: "50%",
          transform: "translateX(-50%)",
          display: { xs: "none", sm: "grid" },
          placeItems: "center",
          gap: 1,
          color: "text.secondary",
          textDecoration: "none",
          // On short viewports (e.g. browser zoom) the centered hero text grows
          // tall enough to collide with this absolutely-positioned cue. Hide it
          // rather than let it overlap the date/venue. Keep last so it wins over
          // the responsive `display` above.
          "@media (max-height: 760px)": { display: "none" },
        }}
      >
        <MascotBadge size={46} mood="peek" />
        {(cover.story_cue_label ?? "The story").trim() && (
          <Box component="span" sx={{ fontSize: 12, letterSpacing: "0.2em", textTransform: "uppercase" }}>
            {cover.story_cue_label ?? "The story"}
          </Box>
        )}
      </Box>
      )}
    </Box>
  );
}
