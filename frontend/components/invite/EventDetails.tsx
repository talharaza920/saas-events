"use client";

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { defaultDayCells, type DayCell, type DayContent, type EventDetails as EventDetailsData } from "@/lib/content";

import Ico, { ICO_NAMES, type IcoName } from "./brand/Ico";
import Section from "./Section";

const cellSx = { p: { xs: 2.5, md: 4 }, bgcolor: "background.default" } as const;

/** Coerce a stored icon name to a known one (fallback keeps render safe). */
function icoName(name: string): IcoName {
  return (ICO_NAMES as string[]).includes(name) ? (name as IcoName) : "info";
}

/** One detail cell: icon + UPPERCASE label + value (+ optional muted sub-line).
 * When `map_link` and a map URL exist the whole cell is a tappable link to Maps. */
function DetailCell({ cell, mapUrl }: { cell: DayCell; mapUrl?: string }) {
  const linked = !!cell.map_link && !!mapUrl;
  const body = (
    <Stack spacing={1} sx={cellSx}>
      <Box sx={{ color: "primary.dark" }}>
        <Ico name={icoName(cell.icon)} />
      </Box>
      <Typography sx={{ fontSize: 12, letterSpacing: "0.16em", textTransform: "uppercase", color: "text.secondary", fontWeight: 700 }}>
        {cell.label}
      </Typography>
      {cell.value && (
        <Typography
          sx={{
            fontWeight: 600,
            fontSize: 16,
            whiteSpace: "pre-line",
            display: "inline-flex",
            alignItems: "center",
            gap: 0.5,
            color: linked ? "primary.dark" : "text.primary",
            textDecoration: linked ? "underline" : "none",
            textUnderlineOffset: 3,
          }}
        >
          {cell.value}
          {linked && <Ico name="pin" size={14} />}
        </Typography>
      )}
      {cell.sub && (
        <Typography sx={{ fontSize: 13, color: "text.secondary" }}>{cell.sub}</Typography>
      )}
    </Stack>
  );
  if (!linked) return body;
  return (
    <Box
      component="a"
      href={mapUrl}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`Open ${cell.value} in Google Maps`}
      sx={{
        color: "inherit",
        textDecoration: "none",
        display: "block",
        transition: "background-color .15s ease",
        "&:hover": { bgcolor: (t) => `${t.extra.colors.primary}14` },
      }}
    >
      {body}
    </Box>
  );
}

/**
 * "One evening by the sea" — the framed day card. A date + venue banner over a row
 * of owner-configurable detail cells (`content.day.cells`): each cell's icon, label,
 * value, sub-line and visibility are editable, and any cell can be flagged as the
 * tappable address → Google Maps link (so there's no separate map button). 4-up on
 * desktop, 2×2 on mobile.
 */
export default function EventDetails({ day, event }: { day: DayContent; event: EventDetailsData }) {
  const cells = (day.cells && day.cells.length ? day.cells : defaultDayCells(event)).filter(
    (c) => c.enabled && (c.value || c.label),
  );
  const venueLine = [event.venue, event.area].filter(Boolean).join(" · ");
  const cols = Math.min(Math.max(cells.length, 1), 4);

  return (
    <Section id="day" kicker={day.kicker} heading={day.heading} intro={day.intro} maxWidth="md">
      <Box
        sx={{
          border: "2px solid",
          borderColor: "text.primary",
          borderRadius: (t) => `${t.extra.radiusLg}px`,
          overflow: "hidden",
          boxShadow: (t) => t.extra.shadows.pop,
          bgcolor: "background.default",
        }}
      >
        {/* Banner: big date + venue · area (venue in accent). */}
        {(event.date_display || venueLine) && (
          <Box
            sx={{
              p: { xs: 4, md: 6 },
              textAlign: "center",
              borderBottom: cells.length ? "2px dashed" : "none",
              borderColor: "divider",
              background: (t) =>
                `radial-gradient(120% 120% at 50% -10%, ${t.extra.colors.primary}33, transparent 60%)`,
            }}
          >
            {event.date_display && (
              <Typography sx={{ fontFamily: (t) => t.extra.typography.display, fontWeight: 800, fontSize: { xs: "1.9rem", md: "3.25rem" }, lineHeight: 1.05 }}>
                {event.date_display}
              </Typography>
            )}
            {venueLine && (
              <Typography sx={{ fontSize: { xs: "1.1rem", md: "1.4rem" }, mt: 1 }}>
                <Box component="strong" sx={{ color: "primary.dark", fontWeight: 700 }}>
                  {event.venue}
                </Box>
                {event.area ? ` · ${event.area}` : ""}
              </Typography>
            )}
            {/* "Open in Maps" — a clean pill button right under the venue line. */}
            {event.map_url && event.map_button !== false && (
              <Box
                component="a"
                href={event.map_url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Open ${event.venue ?? "the venue"} in Google Maps`}
                sx={{
                  mt: 2,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 0.75,
                  px: 2,
                  py: 0.9,
                  borderRadius: 999,
                  border: "1.5px solid",
                  borderColor: "primary.dark",
                  color: "primary.dark",
                  fontWeight: 700,
                  fontSize: 14,
                  lineHeight: 1,
                  textDecoration: "none",
                  bgcolor: "background.default",
                  transition: "background-color .15s ease, color .15s ease",
                  "&:hover": { bgcolor: "primary.dark", color: "background.default" },
                }}
              >
                <Ico name="pin" size={16} />
                {event.map_cta || "Open in Maps"}
              </Box>
            )}
          </Box>
        )}

        {/* Detail cells — hairline separators via a divider-coloured gap. */}
        {cells.length > 0 && (
          <Box
            sx={{
              display: "grid",
              gap: "1.5px",
              bgcolor: "divider",
              gridTemplateColumns: {
                // Mobile: 2-up only for even counts; odd counts (1 or 3) stack
                // one-per-row so there's never a lonely greyed-out empty slot.
                xs: cells.length % 2 === 0 ? "1fr 1fr" : "1fr",
                md: `repeat(${cols}, 1fr)`,
              },
            }}
          >
            {cells.map((cell, i) => (
              <DetailCell key={i} cell={cell} mapUrl={event.map_url} />
            ))}
          </Box>
        )}
      </Box>
    </Section>
  );
}
